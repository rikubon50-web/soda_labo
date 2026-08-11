#!/usr/bin/env python3
"""
noteマガジン操作スクリプト
note.com のマガジン機能をPlaywright経由で操作する（作成・当日記事の追加・プロフィール更新）。
技術: launch_persistent_context + UI自動化（note_metrics.py / note_post.py のパターンを踏襲）。

背景（実エンドポイント調査の結果）:
  ブリーフの仮説エンドポイント（/api/v1/our/magazines 系）は実在しなかった。
  実際に手動相当のUI操作（/magazines/new でのフォーム入力→作成ボタン）をトレースした結果、
  以下の内部APIが実体として確認できた（詳細は
  .superpowers/sdd/2026-08-11-note-discovery/task-1-report.md を参照）:
    - 作成: POST https://note.com/api/v1/my/magazines
      body={"name","description","status":"public","price":0,"subscribe":false,
            "content":"","frequency":1,"is_free_subscribe":false,"management_name":"",
            "layout_type":"list","message":null,"categories":[]}  -> 201
    - 一覧（信頼できる。id/key/name/statusを含む、ページネーションあり）:
      GET https://note.com/api/v2/creators/{urlname}/contents?kind=magazine&page=1&per=50&disabled_pinned=false&with_notes=true&paid_only=false
      -> {"data":{"contents":[...], "isLastPage":bool, "totalCount":int}}
      注意: /api/v2/creators/{urlname} の tlMagazines は常に空配列を返す実装のようで
      既存マガジン判定には使えない（実測で確認）。一覧には本スクリプトが作らない
      システムマガジン「あとで読む」も含まれるため、名前でフィルタする。
  作成後の画面遷移は /soda_labo/m/{key} だが、**アカウント最初の1誌目の作成時は
  遷移が大きく遅延する（実測で15秒のURL待機+2秒待機の計17秒でも遷移せず失敗）**
  ことを実運用で確認した。そのため本スクリプトはURL遷移待機に失敗したら
  一覧APIを名前で引き直すフォールバックを持つ。
  UI操作でしか実現できない操作（フォームのVueリアクティブ状態を要するボタン活性化等）は
  page.fill/page.click によるUI自動化で実装している。

使い方:
  python3 scripts/note_magazine.py --discover        # UI操作のAPIトレースを記録（開発用）
  python3 scripts/note_magazine.py --create-all [--dry-run]
  python3 scripts/note_magazine.py --add-today  [--dry-run]
  python3 scripts/note_magazine.py --update-profile [--dry-run]
"""

import json
import os
import re
import sys
import subprocess
import argparse
from datetime import date, datetime
from pathlib import Path

SODA_DIR     = Path(__file__).parent.parent
PROFILE_DIR  = SODA_DIR / ".browser_profile" / "note"
ERRORS_DIR   = SODA_DIR / "logs" / "errors"
DAILY_DIR    = SODA_DIR / "logs" / "daily"
CONTENT_DIR  = SODA_DIR / "content" / "note"
CONFIG_PATH  = SODA_DIR / "config" / "magazines.json"

CREATOR_URLNAME = os.environ.get("NOTE_USERNAME", "soda_labo")
CREATOR_API      = f"https://note.com/api/v2/creators/{CREATOR_URLNAME}"
MAGAZINES_LIST_API_TEMPLATE = (
    f"https://note.com/api/v2/creators/{CREATOR_URLNAME}/contents"
    "?kind=magazine&page={page}&per=50&disabled_pinned=false&with_notes=true&paid_only=false"
)

MAGAZINES = {
    "AIとマネーの定点観測": "AIに流れるお金を毎朝定点観測。投資・M&A・資金調達を『なぜ』で読む。",
    "AIと雇用のゆくえ": "AIは誰の仕事をどう変えるのか。レイオフ・働き方・組織の変化を毎朝追う。",
    "AI業界の構造転換": "勝者が入れ替わる瞬間を見逃さない。AI企業の戦略・競争・規制を構造で解説。",
}

PROFILE_TEXT = "毎朝8時、AIニュースを1本だけ深掘り。「何が起きたか」ではなく「なぜ起きているか」まで構造解説します。企画・取材・執筆・公開まで全部AIが運営する実験メディア。"

FALLBACK_RULES = [  # (キーワード群, 誌名)。上から順に判定
    (["レイオフ", "雇用", "人員", "削減", "解雇", "働き方", "スキル"], "AIと雇用のゆくえ"),
    (["投資", "買収", "資金", "ドル", "億円", "M&A", "合弁", "ARR", "評価額"], "AIとマネーの定点観測"),
]
DEFAULT_MAGAZINE = "AI業界の構造転換"

# ─── UI自動化セレクタ ──────────────────────────────────────────────────
# 検証済み（3誌作成の本番実行で実測・動作確認済み。2026-08-11時点）
SEL_MAGAZINE_NAME_INPUT     = "#name"
SEL_MAGAZINE_DESC_TEXTAREA  = "#description"
SEL_MAGAZINE_CREATE_BUTTON  = 'button:has-text("作成")'

# 検証済み（2026-08-11 本番実測: バックフィル110件成功+プロフィール更新成功で実証。
# UIが変わって失敗するようになったらここを実物に合わせて更新すること）
SEL_PROFILE_BIO_TEXTAREA    = 'textarea[name="editBiography"]'
SEL_PROFILE_SAVE_BUTTON     = 'button:has-text("保存")'
SEL_NOTE_MAGAZINE_ADD_ICON  = '[aria-label="記事を追加"]'
SEL_MAGAZINE_MODAL_CONTAINER = '[role="dialog"]'  # マガジン選択モーダルのコンテナ（実測済み）


# ─── 共通ヘルパー ──────────────────────────────────────────────────────

def _launch_ctx(headless: bool = True):
    """note_metrics.py / note_post.py と同じパターンでログイン済みプロファイルを起動する"""
    from playwright.sync_api import sync_playwright

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    for lock_file in ["SingletonLock", "SingletonCookie", "SingletonSocket"]:
        lock_path = PROFILE_DIR / lock_file
        if lock_path.exists():
            lock_path.unlink()

    pw = sync_playwright().start()
    ctx = pw.chromium.launch_persistent_context(
        str(PROFILE_DIR),
        headless=headless,
        locale="ja-JP",
        timezone_id="Asia/Tokyo",
    )
    return pw, ctx


def _dump_failure(page, tag: str) -> None:
    """失敗時に生DOM・スクリーンショットを logs/errors/ にダンプする"""
    ERRORS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    try:
        page.screenshot(path=str(ERRORS_DIR / f"{tag}_{ts}.png"), full_page=True)
    except Exception:
        pass
    try:
        (ERRORS_DIR / f"{tag}_{ts}.html").write_text(page.content(), encoding="utf-8")
    except Exception:
        pass


def fetch_creator(page) -> dict:
    """クリエイター情報API（読み取り専用）から magazineCount / tlMagazines / profile を取得する"""
    resp = page.goto(CREATOR_API, wait_until="domcontentloaded", timeout=30000)
    if resp is None or resp.status != 200:
        status = resp.status if resp else "不明"
        raise RuntimeError(f"クリエイターAPI取得失敗: status={status} url={CREATOR_API}")
    body = page.evaluate("() => document.body.innerText")
    raw = json.loads(body)
    return raw.get("data", {})


def fetch_magazines(page) -> list[dict]:
    """信頼できる一覧API（/contents?kind=magazine）から全マガジンを取得する。

    /api/v2/creators/{urlname} の tlMagazines は常に空配列を返すため使わない
    （実測で確認済み。詳細はファイル冒頭のコメント参照）。
    「あとで読む」等のシステムマガジンも含まれる点に注意。
    """
    results: list[dict] = []
    page_num = 1
    while True:
        url = MAGAZINES_LIST_API_TEMPLATE.format(page=page_num)
        resp = page.goto(url, wait_until="domcontentloaded", timeout=30000)
        if resp is None or resp.status != 200:
            status = resp.status if resp else "不明"
            raise RuntimeError(f"マガジン一覧API取得失敗: status={status} url={url}")
        body = page.evaluate("() => document.body.innerText")
        raw = json.loads(body)
        data = raw.get("data", {})
        results.extend(data.get("contents", []))
        if data.get("isLastPage", True):
            break
        page_num += 1
    return results


def _select_magazine_in_modal(page, magazine_name: str, dump_tag: str) -> None:
    """「記事を追加」アイコンクリック後に開くマガジン選択モーダルで対象誌の「追加」ボタンを押す。

    実DOM（2026-08-11実測）: モーダル内の各マガジン行は `.o-magazineListItem` で、
    行の全面に `a[aria-label="誌名"]`（マガジンページへのリンク）が被さっており、
    行内に別途「追加」ボタン（.a-button、テキスト"追加"）がある。
    誌名テキストをクリックすると全面リンクに阻まれる（pointer events intercept）ため、
    「誌名のリンクを含む行」を特定し、その行の「追加」ボタンをクリックする。

    add_today() と note_backfill_magazines.py の両方から呼ばれる共通ロジック。
    見つからなければ失敗ダンプ後にRuntimeErrorを投げる（呼び出し側でハンドリングする）。
    """
    row_sel = f'.o-magazineListItem:has(a[aria-label="{magazine_name}"])'
    add_btn = page.query_selector(f'{row_sel} button:has-text("追加")')
    if not add_btn:
        # 行構造が変わった場合の保険: ダイアログ内で誌名リンクの近傍ボタンを探す
        modal = page.query_selector(SEL_MAGAZINE_MODAL_CONTAINER)
        if modal:
            link = modal.query_selector(f'a[aria-label="{magazine_name}"]')
            if link:
                add_btn = link.evaluate_handle(
                    'el => el.closest(".o-magazineListItem")?.querySelector("button")'
                ).as_element()
    if not add_btn:
        _dump_failure(page, dump_tag)
        raise RuntimeError(f"マガジン選択モーダルに '{magazine_name}' の追加ボタンが見つかりません")
    add_btn.click()


def _load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_config(config: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


# ─── --discover ────────────────────────────────────────────────────────

def discover(ctx) -> None:
    """マガジン管理UIを開いてネットワークトレースを記録する（開発用・読み取りのみ）"""
    page = ctx.new_page()
    trace: list[str] = []
    page.on(
        "request",
        lambda r: trace.append(f"{r.method} {r.url}\n  post={r.post_data}")
        if "/api/" in r.url and r.method in ("POST", "PUT", "PATCH", "DELETE") else None,
    )
    page.on(
        "response",
        lambda r: trace.append(f"  -> {r.status} {r.url}") if "/api/" in r.url else None,
    )
    page.goto("https://note.com/notes", wait_until="domcontentloaded")
    page.wait_for_timeout(3000)
    page.goto("https://note.com/magazines/new", wait_until="domcontentloaded")
    page.wait_for_timeout(3000)
    page.goto(f"https://note.com/{CREATOR_URLNAME}/magazines", wait_until="domcontentloaded")
    page.wait_for_timeout(3000)

    ERRORS_DIR.mkdir(parents=True, exist_ok=True)
    out = ERRORS_DIR / "magazine_api_trace.txt"
    out.write_text("\n".join(trace) if trace else "(POST/PUT/PATCH/DELETE の /api/ リクエストなし)", encoding="utf-8")
    print(f"トレース保存: {out}（{len(trace)}行）")


# ─── --create-all ──────────────────────────────────────────────────────

def _create_magazine_via_ui(page, name: str, description: str) -> dict:
    """/magazines/new フォームを埋めて作成し、{key, id} を返す。

    作成後は /{urlname}/m/{key} へ遷移するが、**アカウント最初の1誌目は
    この遷移が実測で17秒待っても発生しないことがある**（実運用で確認済み）。
    そのためURL遷移待機が失敗しても、一覧API（fetch_magazines）を名前で
    引き直すフォールバックで必ずkey/idを回収する。
    """
    page.goto("https://note.com/magazines/new", wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(1500)

    name_input = page.query_selector(SEL_MAGAZINE_NAME_INPUT)
    desc_input = page.query_selector(SEL_MAGAZINE_DESC_TEXTAREA)
    if not name_input or not desc_input:
        _dump_failure(page, f"magazine_create_form_not_found")
        raise RuntimeError(f"マガジン作成フォームが見つかりません（誌名: {name}）")

    name_input.fill(name)
    desc_input.fill(description)
    page.wait_for_timeout(500)  # Vueのリアクティブ状態更新（作成ボタンのdisabled解除）待ち

    btn = page.query_selector(SEL_MAGAZINE_CREATE_BUTTON)
    if not btn:
        _dump_failure(page, "magazine_create_button_not_found")
        raise RuntimeError(f"作成ボタンが見つかりません（誌名: {name}）")
    btn.click()

    key = None
    try:
        page.wait_for_url(re.compile(r"/m/[^/?]+"), timeout=20000)
        m = re.search(r"/m/([^/?]+)", page.url)
        if m:
            key = m.group(1)
    except Exception:
        pass

    if key is None:
        # フォールバック: 一覧APIを名前で引き直す（POST自体は成功している可能性が高い）
        page.wait_for_timeout(2000)
        magazines = fetch_magazines(page)
        matched = [m for m in magazines if m.get("name") == name]
        if not matched:
            _dump_failure(page, "magazine_key_extract_failed")
            raise RuntimeError(
                f"マガジン作成後のkey抽出に失敗（誌名: {name}, url={page.url}, "
                f"一覧APIにも未出現）"
            )
        return {"key": matched[0]["key"], "id": matched[0].get("id")}

    # URL経由で取れた場合もidは一覧APIから補完する
    magazines = fetch_magazines(page)
    matched = [m for m in magazines if m.get("key") == key]
    return {"key": key, "id": matched[0].get("id") if matched else None}


def create_all(ctx, dry_run: bool) -> None:
    """既存マガジン一覧を確認し、未作成の誌のみ1誌ずつ作成する（作成の都度APIで存在確認）"""
    page = ctx.new_page()
    creator = fetch_creator(page)
    existing_count = creator.get("magazineCount", 0)

    # 一覧API（信頼できる）で既存誌名を判定する。
    # /api/v2/creators/{urlname} の tlMagazines は常に空配列を返すため使わない（実測で確認）。
    existing_names: set[str] = {m.get("name", "") for m in fetch_magazines(page)}
    existing_names.discard("")
    # 念のためローカル設定も見る（一覧APIが一時的に不整合な場合の保険）
    existing_names |= set(_load_config().keys())

    to_create = [name for name in MAGAZINES if name not in existing_names]

    if dry_run:
        print(f"既存マガジン数（API）: {existing_count}")
        print(f"既存マガジン名（判明分）: {sorted(existing_names) or 'なし'}")
        print("作成予定:")
        if not to_create:
            print("  （作成対象なし。3誌とも既存）")
        for name in to_create:
            print(f"  - {name}: {MAGAZINES[name]}")
        return

    if not to_create:
        print("作成対象なし（3誌とも既存）")
        return

    config = _load_config()
    for name in to_create:
        created = _create_magazine_via_ui(page, name, MAGAZINES[name])
        config[name] = {"key": created["key"], "id": created["id"]}
        _save_config(config)
        print(f"作成完了: {name} → key={created['key']} id={created['id']}")

        # ブリーフの安全策: 1誌作成するごとにAPIで存在確認してから次に進む
        creator_check = fetch_creator(page)
        new_count = creator_check.get("magazineCount", 0)
        if new_count < existing_count + 1:
            _dump_failure(page, "magazine_create_verify_failed")
            raise RuntimeError(
                f"作成後の存在確認に失敗しました（誌名: {name}, magazineCount={new_count}）"
            )
        existing_count = new_count
        print(f"存在確認OK（magazineCount={new_count}）")

    creator_final = fetch_creator(page)
    print(f"最終確認: magazineCount={creator_final.get('magazineCount')}")


# ─── --add-today ───────────────────────────────────────────────────────

def _today_article_title(ds: str) -> str:
    files = sorted(CONTENT_DIR.glob(f"{ds}_*.md"))
    if not files:
        return ""
    for line in files[0].read_text(encoding="utf-8").splitlines():
        if line.startswith("# "):
            return line.lstrip("# ").strip()
    return ""


def determine_magazine_name(ds: str) -> str:
    mag_file = DAILY_DIR / f"{ds}_magazine.txt"
    if mag_file.exists():
        lines = mag_file.read_text(encoding="utf-8").splitlines()
        if lines and lines[0].strip() in MAGAZINES:
            return lines[0].strip()

    title = _today_article_title(ds)
    for keywords, name in FALLBACK_RULES:
        if any(kw in title for kw in keywords):
            return name
    return DEFAULT_MAGAZINE


def add_today(ctx, dry_run: bool) -> None:
    ds = str(date.today())
    magazine_name = determine_magazine_name(ds)

    url_file = DAILY_DIR / f"{ds}_note_url.txt"
    if not url_file.exists():
        raise RuntimeError(f"当日記事URLが見つかりません: {url_file}")
    note_url = url_file.read_text(encoding="utf-8").strip()

    m = re.search(r"/n/(n[0-9a-f]+)", note_url)
    if not m:
        raise RuntimeError(f"note keyの抽出に失敗しました: url={note_url}")
    note_key = m.group(1)

    if dry_run:
        print(f"判定誌名: {magazine_name}")
        print(f"note key: {note_key}")
        print(f"記事URL: {note_url}")
        return

    config = _load_config()
    if magazine_name not in config:
        raise RuntimeError(f"マガジン '{magazine_name}' が {CONFIG_PATH} に未登録です（先に --create-all を実行）")
    magazine_key = config[magazine_name]["key"]

    page = ctx.new_page()
    page.goto(note_url, wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(2000)

    add_icon = page.query_selector(SEL_NOTE_MAGAZINE_ADD_ICON)
    if not add_icon:
        _dump_failure(page, "magazine_add_icon_not_found")
        raise RuntimeError("「記事を追加」ボタンが見つかりません")
    add_icon.click()
    page.wait_for_timeout(1500)

    _select_magazine_in_modal(page, magazine_name, "magazine_modal_target_not_found")
    page.wait_for_timeout(2000)

    # 検証: 記事詳細APIの belonging_magazine_keys に対象keyが含まれるか確認する。
    # ★fail-soft: この検証API（GET /api/v3/notes/{key}）は未実測（仮説）であり、
    # レスポンス形式やフィールド名が違っていた場合に「追加自体は成功しているのに
    # 検証失敗でexit 1・notify_error誤発火」となるリスクが高い。そのため検証失敗は
    # 例外にせず警告ログに留め、exit codeは追加操作（クリックまで）の成否のみで決める。
    # 検証APIの実物確認結果は Task 7 の本番実行時にレポートへ追記する前提。
    try:
        resp = page.goto(f"https://note.com/api/v3/notes/{note_key}", wait_until="domcontentloaded", timeout=20000)
        if resp is None or resp.status != 200:
            print(f"WARN: 追加後の検証取得に失敗（追加自体は実行済み）: status={resp.status if resp else '不明'}")
        else:
            body = page.evaluate("() => document.body.innerText")
            raw = json.loads(body)
            belonging = raw.get("data", {}).get("belonging_magazine_keys", [])
            if magazine_key not in belonging:
                print(
                    f"WARN: 追加後の検証に失敗（追加自体は実行済み。要目視確認）: "
                    f"belonging_magazine_keys={belonging}, expected_key={magazine_key}"
                )
            else:
                print(f"検証OK: belonging_magazine_keysに{magazine_key}を確認")
    except Exception as e:
        print(f"WARN: 追加後の検証中に例外が発生（追加自体は実行済み。要目視確認）: {e}")

    print(f"追加完了: {note_key} → {magazine_name}（key={magazine_key}）")


# ─── --update-profile ──────────────────────────────────────────────────

def update_profile(ctx, dry_run: bool) -> None:
    if dry_run:
        print("更新予定プロフィール文:")
        print(PROFILE_TEXT)
        return

    page = ctx.new_page()
    page.goto("https://note.com/settings/profile", wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(1500)

    bio = page.query_selector(SEL_PROFILE_BIO_TEXTAREA)
    if not bio:
        _dump_failure(page, "profile_bio_textarea_not_found")
        raise RuntimeError("プロフィール入力欄が見つかりません")
    bio.fill(PROFILE_TEXT)
    page.wait_for_timeout(300)

    btn = page.query_selector(SEL_PROFILE_SAVE_BUTTON)
    if not btn:
        _dump_failure(page, "profile_save_button_not_found")
        raise RuntimeError("保存ボタンが見つかりません")
    btn.click()
    page.wait_for_timeout(2000)

    creator = fetch_creator(page)
    if creator.get("profile", "").strip() != PROFILE_TEXT.strip():
        _dump_failure(page, "profile_update_verify_failed")
        raise RuntimeError("プロフィール更新後の検証に失敗しました")
    print("プロフィール更新完了・検証OK")


# ─── main ───────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="noteマガジン操作スクリプト")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--discover", action="store_true", help="APIトレースを記録（開発用）")
    group.add_argument("--create-all", action="store_true", help="3誌を作成（既存はスキップ）")
    group.add_argument("--add-today", action="store_true", help="当日記事をマガジンに追加")
    group.add_argument("--update-profile", action="store_true", help="プロフィール文を更新")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.discover:
        pw, ctx = _launch_ctx(headless=True)
        try:
            discover(ctx)
        finally:
            ctx.close()
            pw.stop()
        return 0

    if args.create_all:
        action_key, step_name = "create_all", "noteマガジン作成"
    elif args.add_today:
        action_key, step_name = "add_today", "note当日記事マガジン追加"
    else:
        action_key, step_name = "update_profile", "noteプロフィール更新"

    pw = ctx = None
    try:
        pw, ctx = _launch_ctx(headless=True)
        if action_key == "create_all":
            create_all(ctx, dry_run=args.dry_run)
        elif action_key == "add_today":
            add_today(ctx, dry_run=args.dry_run)
        else:
            update_profile(ctx, dry_run=args.dry_run)
    except Exception as e:
        detail = str(e)
        print(f"{step_name}失敗: {detail}", file=sys.stderr)
        if not args.dry_run:
            subprocess.run(
                [sys.executable, str(SODA_DIR / "scripts" / "notify_error.py"), step_name, detail[:300]],
                cwd=str(SODA_DIR),
            )
        return 1
    finally:
        if ctx:
            ctx.close()
        if pw:
            pw.stop()

    return 0


if __name__ == "__main__":
    sys.exit(main())
