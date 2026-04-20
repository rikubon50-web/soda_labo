#!/usr/bin/env python3
"""
note.com 投稿スクリプト（下書き or 自動公開）
技術: Playwright + ClipboardEvent（text/plain → ProseMirrorが自動パース）

使い方:
  python3 scripts/note_post.py content/note/2026-04-20_タイトル.md
  python3 scripts/note_post.py --today
  python3 scripts/note_post.py content/note/... --dry-run

自動公開ロジック:
  logs/daily/YYYY-MM-DD_ceo_score.txt にCEOスコア（1〜5）が保存されていて、
  スコアが PUBLISH_THRESHOLD（デフォルト4）以上なら自動公開。それ以外は下書き保存。

初回実行: ブラウザが開くのでnote.comに手動ログインしてください。
2回目以降: セッションが保存されるので自動でログイン済み状態になります。
"""

import sys
import os
import base64
import argparse
from pathlib import Path
from datetime import date, datetime
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

SODA_DIR     = Path(__file__).parent.parent
PROFILE_DIR  = SODA_DIR / ".browser_profile" / "note"
PUBLISH_THRESHOLD = 4

PASTE_JS = """
(markdownText) => {
    const editor = document.querySelector('.ProseMirror');
    if (!editor) return { ok: false, reason: 'ProseMirror not found' };
    editor.focus();
    const clipboardData = new DataTransfer();
    clipboardData.setData('text/plain', markdownText);
    const event = new ClipboardEvent('paste', {
        bubbles: true, cancelable: true, clipboardData: clipboardData,
    });
    editor.dispatchEvent(event);
    return { ok: true, editorText: editor.innerText.slice(0, 100) };
}
"""

DEDUP_JS = """
() => {
    const editor = document.querySelector('.ProseMirror');
    if (!editor) return;
    const full = editor.innerText.trim();
    const half = Math.floor(full.length / 2);
    const a = full.slice(0, half).trim();
    const b = full.slice(half).trim();
    if (a.length > 50 && a === b) {
        const nodes = Array.from(editor.children);
        const mid = Math.floor(nodes.length / 2);
        nodes.slice(mid).forEach(n => n.remove());
    }
}
"""


def find_today_file() -> str | None:
    today = date.today().strftime("%Y-%m-%d")
    files = sorted((SODA_DIR / "content" / "note").glob(f"{today}_*.md"))
    return str(files[0]) if files else None


def load_ceo_score() -> int | None:
    today = date.today().strftime("%Y-%m-%d")
    score_file = SODA_DIR / "logs" / "daily" / f"{today}_ceo_score.txt"
    if not score_file.exists():
        return None
    try:
        return int(score_file.read_text().strip())
    except ValueError:
        return None


def parse_article(filepath: str) -> tuple[str, str]:
    content = Path(filepath).read_text(encoding="utf-8")
    lines = content.splitlines()
    title = next((l.lstrip("# ").strip() for l in lines if l.startswith("# ")), "無題")
    body_lines = [l for l in lines if l.strip() != f"# {title}"]
    return title, "\n".join(body_lines).strip()


def post_to_note(filepath: str, dry_run: bool = False) -> None:
    title, body = parse_article(filepath)
    ceo_score   = load_ceo_score()
    should_publish = ceo_score is not None and ceo_score >= PUBLISH_THRESHOLD

    if dry_run:
        print(f"タイトル: {title}")
        print(f"CEOスコア: {ceo_score if ceo_score else '未取得'}")
        print(f"動作: {'公開' if should_publish else '下書き保存'}")
        print(f"サムネイル: {'生成します' if os.environ.get('GEMINI_API_KEY') else 'GEMINI_API_KEY未設定のためスキップ'}")
        print(f"本文（先頭200字）:\n{body[:200]}...")
        return

    # サムネイル生成（Playwright起動前に行う）
    thumbnail_path = generate_thumbnail(title)

    if ceo_score is not None:
        print(f"CEOスコア: {ceo_score} → {'公開します' if should_publish else '下書き保存します（スコア不足）'}")
    else:
        print("CEOスコアファイルなし → 下書き保存します")

    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    for lock_file in ["SingletonLock", "SingletonCookie", "SingletonSocket"]:
        lock_path = PROFILE_DIR / lock_file
        if lock_path.exists():
            lock_path.unlink()
    note_email    = os.environ.get("NOTE_EMAIL", "")
    note_password = os.environ.get("NOTE_PASSWORD", "")

    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            str(PROFILE_DIR),
            headless=False,
            locale="ja-JP",
            timezone_id="Asia/Tokyo",
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        page = ctx.new_page()

        # ─── ログイン確認（/notes/newへ飛んでリダイレクト有無で判断） ──
        page.goto("https://note.com/notes/new", wait_until="networkidle")
        page.wait_for_timeout(3000)
        current_url = page.url
        print(f"[DEBUG] notes/new 後のURL: {current_url}")

        # ログインページへのリダイレクトで判断（"login"か"signin"が含まれる）
        login_keywords = ["login", "signin", "sign_in", "auth"]
        logged_in = not any(kw in current_url for kw in login_keywords)

        if not logged_in:
            print("ログインセッションなし → ログイン処理を開始します")
            page.goto("https://note.com/login", wait_until="domcontentloaded")
            page.wait_for_timeout(1500)

            if note_email and note_password:
                page.goto("https://note.com/login", wait_until="networkidle")
                page.wait_for_timeout(2000)
                # デバッグ: ログインページのinput一覧
                debug_dir = SODA_DIR / "logs" / "debug"
                debug_dir.mkdir(parents=True, exist_ok=True)
                login_shot = debug_dir / f"{date.today()}_login.png"
                page.screenshot(path=str(login_shot))
                inputs_info = page.evaluate("""() => Array.from(document.querySelectorAll('input')).map(el => ({
                    type: el.type, name: el.name, id: el.id,
                    placeholder: el.placeholder, autocomplete: el.autocomplete,
                    class: el.className.slice(0, 60)
                }))""")
                print(f"[DEBUG] ログインページ screenshot: {login_shot}")
                print(f"[DEBUG] input要素一覧: {inputs_info}")
                try:
                    page.wait_for_selector("input", timeout=10000)
                except PWTimeout:
                    pass
                # すべてのinputを取得して最初の2つをemail/passwordとして使う
                all_inputs = page.query_selector_all("input:not([type='hidden'])")
                email_input = None
                pass_input = None
                for inp in all_inputs:
                    t = inp.get_attribute("type") or ""
                    if t == "password":
                        pass_input = inp
                    elif t in ("email", "text", "") and email_input is None:
                        email_input = inp
                if email_input and pass_input:
                    email_input.fill(note_email)
                    pass_input.fill(note_password)
                    page.keyboard.press("Enter")
                    try:
                        page.wait_for_url(lambda u: "login" not in u, timeout=20000)
                        print("自動ログイン完了")
                    except PWTimeout:
                        print("エラー: ログインタイムアウト")
                        ctx.close()
                        sys.exit(1)
                else:
                    # フォールバック: 手動ログイン
                    print("ログインフォームが自動検出できません。ブラウザで手動ログインしてください。")
                    print("ログイン完了後、Enterを押してください...")
                    input()
            else:
                print("ブラウザが開きました。note.comに手動でログインしてください。")
                print("ログイン完了後、Enterを押してください...")
                input()

        # ─── 新規記事作成ページへ（まだそこにいない場合のみ遷移） ───
        # editor.note.com/notes/.../edit/ へリダイレクト済みの場合はスキップ
        if "notes/new" not in page.url and "/edit/" not in page.url:
            page.goto("https://note.com/notes/new", wait_until="networkidle")
            page.wait_for_timeout(3000)

        # ─── タイトル入力 ──────────────────────────────────────────
        title_selectors = [
            'textarea[placeholder*="タイトル"]',
            '[data-placeholder*="タイトル"]',
            'input[placeholder*="タイトル"]',
            'textarea[placeholder*="記事タイトル"]',
            '[contenteditable="true"][class*="title"]',
        ]
        for sel in title_selectors:
            el = page.query_selector(sel)
            if el:
                el.click()
                el.fill(title)
                print(f"タイトル入力完了: {title}")
                break

        page.wait_for_timeout(1000)

        # ─── 本文ペースト（ClipboardEvent + text/plain） ──────────
        result = page.evaluate(PASTE_JS, body)
        if not result.get("ok"):
            print(f"エラー: 本文ペースト失敗 → {result.get('reason')}")
            ctx.close()
            sys.exit(1)

        print(f"本文ペースト完了（先頭: {result.get('editorText', '')[:40]}...）")
        page.wait_for_timeout(2000)

        page.evaluate(DEDUP_JS)
        page.wait_for_timeout(500)

        # ─── サムネイルアップロード ────────────────────────────────
        if thumbnail_path:
            upload_thumbnail(page, thumbnail_path)
            page.wait_for_timeout(10000)  # サムネイル反映待ち

        # ─── 公開 or 下書き保存 ────────────────────────────────────
        if should_publish:
            published = _publish(page, title)
            if published:
                _save_note_url(page)
            else:
                # 公開失敗時は下書き保存にフォールバック
                btn = page.query_selector('button:has-text("下書き保存")')
                if btn:
                    btn.click()
                    page.wait_for_timeout(2000)
                print("警告: 公開失敗 → 下書き保存しました")
        else:
            btn = page.query_selector('button:has-text("下書き保存")')
            if btn:
                btn.click()
                page.wait_for_timeout(2000)
            print(f"下書きとして保存しました: {title}")

        ctx.close()


def generate_thumbnail(title: str) -> Path | None:
    """Geminiでnoteサムネイル画像を生成してファイルに保存する"""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        print("GEMINI_API_KEY未設定 → サムネイル生成をスキップ")
        return None

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)

        prompt = f"""以下のブログ記事のサムネイル画像（横長16:9）を生成してください。

タイトル: 「{title}」

要件:
- タイトルの核心キーワードを画像内に大きな日本語テキストとして表示する
- モダンでクリーンなデザイン（深みのある背景色）
- テキストと背景のコントラストを高く保つ
- YouTubeサムネイルのように視認性が高く、クリックしたくなるデザイン
- プロフェッショナルなブログ向け
"""

        # 画像生成対応モデルを順番に試す（Proモデルは日本語テキスト描画に対応）
        image_gen_models = [
            "models/gemini-3-pro-image-preview",
            "models/gemini-3.1-flash-image-preview",
            "models/gemini-2.5-flash-image",
        ]
        response = None
        for model_name in image_gen_models:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_modalities=["IMAGE", "TEXT"]
                    )
                )
                print(f"モデル使用: {model_name}")
                break
            except Exception as e:
                print(f"モデル {model_name} 失敗: {e}")
                continue

        if response is None:
            print("警告: 全モデルで画像生成失敗")
            return None

        # レスポンスから画像データを取得（Gemini/Imagen両対応）
        image_bytes = None
        if hasattr(response, "generated_images"):
            # Imagen APIのレスポンス形式
            image_bytes = response.generated_images[0].image.image_bytes
        else:
            # Gemini generate_content のレスポンス形式
            for part in response.candidates[0].content.parts:
                if part.inline_data is not None:
                    raw = part.inline_data.data
                    image_bytes = raw if isinstance(raw, bytes) else base64.b64decode(raw)
                    break

        if not image_bytes:
            print("警告: Geminiから画像データが返されませんでした")
            return None

        thumb_dir = SODA_DIR / "content" / "thumbnails"
        thumb_dir.mkdir(parents=True, exist_ok=True)
        today = date.today().strftime("%Y-%m-%d")
        # タイトルから安全なファイル名を生成
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in title[:30])
        out_path = thumb_dir / f"{today}_{safe_name}.png"
        out_path.write_bytes(image_bytes)
        print(f"サムネイル生成完了: {out_path}")
        return out_path

    except Exception as e:
        print(f"警告: サムネイル生成失敗 → {e}")
        return None


def _debug_dump(page) -> None:
    """ページのボタン情報とスクリーンショットをdebug/に保存する"""
    debug_dir = SODA_DIR / "logs" / "debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%H%M%S")
    shot_path = debug_dir / f"{date.today()}_{ts}_editor.png"
    page.screenshot(path=str(shot_path), full_page=True)
    buttons = page.evaluate("""() => {
        return Array.from(document.querySelectorAll('button, [role="button"]')).map(el => {
            const r = el.getBoundingClientRect();
            return {
                text: el.innerText.trim().slice(0, 50),
                class: String(el.className).slice(0, 80),
                testid: el.getAttribute('data-testid') || '',
                hasSvg: !!el.querySelector('svg'),
                top: Math.round(r.top), left: Math.round(r.left),
                w: Math.round(r.width), h: Math.round(r.height),
            };
        }).filter(b => b.w > 5 && b.h > 5);
    }""")
    eyecatch = page.evaluate("""() => {
        const kws = ['eyecatch','eye-catch','EyeCatch','header-image','headerImage','thumbnail','cover'];
        return Array.from(document.querySelectorAll('*')).filter(el => {
            const cls = String(el.className || ''); const id = String(el.id || '');
            return kws.some(k => cls.includes(k) || id.includes(k));
        }).slice(0, 10).map(el => ({tag: el.tagName, class: String(el.className||'').slice(0,80), id: String(el.id||'')}));
    }""")
    print(f"[DEBUG] スクリーンショット: {shot_path}")
    print("[DEBUG] ボタン一覧（全て）:")
    for b in buttons[:40]:
        print(f"  text={b['text']!r}  svg={b['hasSvg']}  pos=({b['left']},{b['top']})  size={b['w']}x{b['h']}  class={b['class'][:50]!r}")
    print("[DEBUG] eyecatch要素:")
    for e in eyecatch:
        print(f"  tag={e['tag']}  id={e['id']!r}  class={e['class']!r}")
    # エディタ上部200px以内にある全要素
    top_els = page.evaluate("""() => {
        return Array.from(document.querySelectorAll('*')).filter(el => {
            const r = el.getBoundingClientRect();
            return r.top >= 0 && r.top < 200 && r.width > 20 && r.height > 20;
        }).slice(0, 20).map(el => ({
            tag: el.tagName, class: String(el.className||'').slice(0,60),
            top: Math.round(el.getBoundingClientRect().top),
            left: Math.round(el.getBoundingClientRect().left),
        }));
    }""")
    print("[DEBUG] 上部200px内の要素:")
    for e in top_els:
        print(f"  tag={e['tag']}  top={e['top']}  left={e['left']}  class={e['class']!r}")


def upload_thumbnail(page, image_path: Path) -> bool:
    """Playwrightでnote.comのヘッダー画像エリアにサムネイルをアップロードする"""
    try:
        # ヘッダー画像エリアのボタン/クリック可能な要素を探す
        header_selectors = [
            '[class*="eyecatch"]',
            '[class*="EyeCatch"]',
            '[class*="eye-catch"]',
            '[class*="header-image"]',
            '[class*="headerImage"]',
            '[data-testid="eyecatch-upload"]',
            'button:has-text("見出し画像")',
            'button:has-text("ヘッダー")',
            'button:has-text("カバー")',
            # エディタ上部の丸いアイコン（サムネイル追加ボタン）
            'figure button',
            '[class*="cover"] button',
            '[class*="Cover"] button',
        ]

        for sel in header_selectors:
            el = page.query_selector(sel)
            if el:
                # ファイルチューザーが開くのを待ってクリック
                with page.expect_file_chooser(timeout=5000) as fc_info:
                    el.click()
                fc_info.value.set_files(str(image_path))
                page.wait_for_timeout(2000)
                print(f"サムネイルアップロード完了")
                return True

        # フォールバック: eyecatchアイコンボタン → ドロップダウン「画像をアップロード」の2ステップ
        all_btns = page.query_selector_all("button")
        for handle in all_btns:
            try:
                box = handle.bounding_box()
                if not box or box["x"] <= 100 or box["y"] < 50 or box["width"] < 20:
                    continue
                svg = handle.query_selector("svg")
                text = handle.inner_text().strip()
                if not svg or text:
                    continue
                print(f"[DEBUG] eyecatch候補ボタン: x={box['x']:.0f} y={box['y']:.0f}")
                handle.click()
                page.wait_for_timeout(1000)
                # ドロップダウンから「画像をアップロード」を選ぶ
                upload_option = (
                    page.query_selector('text="画像をアップロード"') or
                    page.query_selector('button:has-text("画像をアップロード")') or
                    page.query_selector('[role="menuitem"]:has-text("画像をアップロード")')
                )
                if not upload_option:
                    continue
                with page.expect_file_chooser(timeout=5000) as fc_info:
                    upload_option.click()
                fc_info.value.set_files(str(image_path))
                page.wait_for_timeout(2000)
                # 画像クロップモーダルの「保存」をクリック（exact match）
                try:
                    save_btn = page.get_by_role("button", name="保存", exact=True)
                    save_btn.wait_for(timeout=5000)
                    save_btn.click()
                    page.wait_for_timeout(1500)
                    print("サムネイル保存完了")
                except Exception as e:
                    print(f"警告: 保存ボタン未検出 → {e}")
                print("サムネイルアップロード完了")
                return True
            except Exception:
                continue

        # 最終フォールバック: input[type="file"] を直接操作
        file_input = page.query_selector('input[type="file"][accept*="image"]')
        if file_input:
            file_input.set_input_files(str(image_path))
            page.wait_for_timeout(2000)
            print("サムネイルアップロード完了（直接input）")
            return True

        print("警告: サムネイルアップロード先が見つかりませんでした")
        return False

    except Exception as e:
        print(f"警告: サムネイルアップロード失敗 → {e}")
        return False


def _save_note_url(page) -> None:
    """公開後のnote記事URLを保存する（夜投稿のCTAに使用）"""
    from playwright.sync_api import TimeoutError as PWTimeout
    import re

    # 公開後のURLに遷移するまで待機（最大10秒）
    try:
        page.wait_for_url(
            lambda u: "/n/" in u and "editor.note.com" not in u,
            timeout=10000
        )
    except PWTimeout:
        pass

    url = page.url

    # editor.note.com/notes/nXXXX/publish/ → ページ内リンクから公開URLを探す
    if "editor.note.com" in url or "/publish" in url:
        links = page.evaluate("""() =>
            Array.from(document.querySelectorAll('a[href*="/n/"]')).map(a => a.href)
        """)
        public = [l for l in links if "/n/" in l and "editor.note.com" not in l]
        if public:
            url = public[0]

    if "note.com" in url and "/n/" in url and "editor.note.com" not in url:
        url_file = SODA_DIR / "logs" / "daily" / f"{date.today()}_note_url.txt"
        url_file.parent.mkdir(parents=True, exist_ok=True)
        url_file.write_text(url)
        print(f"note URL保存: {url}")
    else:
        # editor URLからnote IDを抽出してURLを構築（ユーザー名不明のため記録）
        m = re.search(r'/notes/(n[0-9a-f]+)/', page.url)
        if m:
            note_id = m.group(1)
            print(f"note ID: {note_id} （公開URL未取得 - 手動で確認してください）")
        else:
            print(f"警告: note記事URLの取得失敗（現在URL: {url}）")


def _publish(page, title: str) -> bool:
    """公開設定ボタン → 投稿するボタン の順でクリックして公開"""
    from playwright.sync_api import TimeoutError as PWTimeout

    # 公開設定パネルを開く
    open_selectors = [
        'button:has-text("公開に進む")',
        'button:has-text("公開設定")',
        'button:has-text("公開する")',
        '[data-testid="publish-button"]',
    ]
    opened = False
    for sel in open_selectors:
        btn = page.query_selector(sel)
        if btn:
            btn.click()
            page.wait_for_timeout(2000)
            opened = True
            break

    if not opened:
        return False

    # モーダル内の最終「投稿する」ボタン
    confirm_selectors = [
        'button:has-text("投稿する")',
        'button:has-text("公開する")',
        '[data-testid="publish-confirm-button"]',
        'button:has-text("今すぐ公開")',
    ]
    for sel in confirm_selectors:
        try:
            page.wait_for_selector(sel, timeout=5000)
            btn = page.query_selector(sel)
            if btn:
                btn.click()
                page.wait_for_timeout(3000)
                print(f"公開完了: {title}")
                return True
        except PWTimeout:
            continue

    return False


def main():
    parser = argparse.ArgumentParser(description="note.com 投稿スクリプト")
    parser.add_argument("filepath", nargs="?")
    parser.add_argument("--today", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.today:
        filepath = find_today_file()
        if not filepath:
            print("今日のnote記事が見つかりません")
            sys.exit(1)
    elif args.filepath:
        filepath = args.filepath
    else:
        parser.print_help()
        sys.exit(1)

    post_to_note(filepath, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
