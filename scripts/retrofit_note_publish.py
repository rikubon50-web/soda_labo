#!/usr/bin/env python3
"""
note.com 公開記事の本文を一括再ペーストして CTA を更新する。

前提：
  scripts/retrofit_note_cta.py を先に実行して
  ローカル content/note/*.md を新 CTA に書換済みであること。

このスクリプトは：
  1. logs/daily/YYYY-MM-DD_note_url.txt から各記事の公開URLを取得
  2. 各 URL をエディタモードで開く
  3. ProseMirror エディタに対して全選択→ローカル .md の本文をペースト
  4. 「更新する」ボタンで公開反映
  5. 進行状況を logs/daily/cta_retrofit_progress.json に記録

使い方：
  python3 scripts/retrofit_note_publish.py --dry-run        # 何をするかだけ確認
  python3 scripts/retrofit_note_publish.py --limit 1        # 1件だけ処理（テスト用）
  python3 scripts/retrofit_note_publish.py --skip-done      # 既処理を飛ばして残りを処理
  python3 scripts/retrofit_note_publish.py                  # 全件処理（確認プロンプトあり）

注意：
  - 初回実行時はブラウザが開くので note.com にログイン済セッションを使う
  - 失敗した記事は progress.json に "failed" として記録、--skip-done で再試行可能
  - 各記事間に5秒のウェイトを入れて rate limit 回避
"""

import argparse
import json
import re
import sys
import time
from datetime import date, datetime
from pathlib import Path

SODA_DIR = Path(__file__).parent.parent
PROFILE_DIR = SODA_DIR / ".browser_profile" / "note"
NOTE_DIR = SODA_DIR / "content" / "note"
URL_DIR = SODA_DIR / "logs" / "daily"
PROGRESS_FILE = URL_DIR / "cta_retrofit_progress.json"

PASTE_REPLACE_JS = """
(markdownText) => {
    const editor = document.querySelector('.ProseMirror');
    if (!editor) return { ok: false, reason: 'ProseMirror not found' };
    editor.focus();
    // 全選択（document.execCommand は廃止予定だが ProseMirror で動作する）
    document.execCommand('selectAll');
    // 削除してから貼り付け（ProseMirror は paste で置換するが念のため）
    const clipboardData = new DataTransfer();
    clipboardData.setData('text/plain', markdownText);
    const event = new ClipboardEvent('paste', {
        bubbles: true, cancelable: true, clipboardData: clipboardData,
    });
    editor.dispatchEvent(event);
    return { ok: true, editorText: editor.innerText.slice(0, 80) };
}
"""


def parse_article(filepath: Path) -> tuple[str, str]:
    """ローカル .md からタイトルと本文（タイトル行を除いた本文）を取り出す"""
    content = filepath.read_text(encoding="utf-8")
    lines = content.splitlines()
    title = next((l.lstrip("# ").strip() for l in lines if l.startswith("# ")), "無題")
    body_lines = [l for l in lines if l.strip() != f"# {title}"]
    return title, "\n".join(body_lines).strip()


def derive_editor_url(public_url: str) -> str | None:
    """公開URL（note.com/foo/n/<id>）→ editor.note.com/notes/<id>/edit/ に変換"""
    m = re.search(r"/n/([0-9a-f]+)", public_url)
    if not m:
        return None
    return f"https://editor.note.com/notes/{m.group(1)}/edit/"


def collect_targets() -> list[tuple[Path, str]]:
    """ローカル .md と公開URLをペアリングして対象リストを返す"""
    targets: list[tuple[Path, str]] = []
    for f in sorted(NOTE_DIR.glob("*.md")):
        m = re.match(r"(\d{4}-\d{2}-\d{2})_", f.name)
        if not m:
            continue
        url_file = URL_DIR / f"{m.group(1)}_note_url.txt"
        if not url_file.exists():
            continue
        url = url_file.read_text(encoding="utf-8").strip()
        if not url:
            continue
        if "/info/" in url:
            # 別アカウント（note.com/info/）の URL は対象外
            continue
        targets.append((f, url))
    return targets


def load_progress() -> dict:
    if PROGRESS_FILE.exists():
        try:
            return json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_progress(progress: dict) -> None:
    PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROGRESS_FILE.write_text(
        json.dumps(progress, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def update_one(page, md_path: Path, url: str) -> tuple[bool, str]:
    """1記事を更新。戻り値: (成功フラグ, メッセージ)"""
    title, body = parse_article(md_path)

    editor_url = derive_editor_url(url)
    if not editor_url:
        return False, f"editor URL 導出失敗（URL: {url}）"

    print(f"  → editor: {editor_url}")
    page.goto(editor_url, wait_until="networkidle")
    page.wait_for_timeout(3500)

    try:
        page.wait_for_selector(".ProseMirror", timeout=15000)
    except Exception:
        return False, "ProseMirror 未検出（ログイン or ページ読み込み失敗）"
    page.wait_for_timeout(2000)

    result = page.evaluate(PASTE_REPLACE_JS, body)
    if not result.get("ok"):
        return False, f"ペースト失敗: {result.get('reason')}"
    print(f"    ペースト完了（先頭: {result.get('editorText', '')[:30]}...）")
    page.wait_for_timeout(2500)

    # 「更新する」ボタンを探す（既公開記事の場合のラベル）
    update_btn = (
        page.query_selector('button:has-text("更新する")')
        or page.query_selector('button:has-text("公開する")')
        or page.query_selector('button:has-text("公開に進む")')
    )
    if not update_btn:
        return False, "更新ボタン未検出"

    update_btn.click()
    page.wait_for_timeout(2500)

    # 確認モーダル：もう一度「更新する」 or 「投稿する」が出る場合あり
    confirm = (
        page.query_selector('button:has-text("更新する"):not([disabled])')
        or page.query_selector('button:has-text("投稿する")')
        or page.query_selector('[data-testid="publish-confirm-button"]')
    )
    if confirm:
        try:
            confirm.click()
            page.wait_for_timeout(3500)
        except Exception:
            pass

    return True, "公開更新完了"


def list_targets(targets: list[tuple[Path, str]], progress: dict) -> None:
    print(f"\n対象 {len(targets)} 件:")
    for f, url in targets:
        status = progress.get(f.name, {}).get("status", "pending")
        marker = {"done": "✅", "failed": "⚠️ ", "pending": "  "}.get(status, "  ")
        print(f"  {marker} {f.name}  →  {url}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="リスト表示のみ")
    ap.add_argument("--limit", type=int, default=None, help="先頭N件だけ処理（テスト用）")
    ap.add_argument("--skip-done", action="store_true", help="progress.json で done になっている記事をスキップ")
    ap.add_argument("--delay", type=int, default=5, help="記事間の待機秒数")
    args = ap.parse_args()

    targets = collect_targets()
    progress = load_progress()

    if args.skip_done:
        targets = [
            (f, url)
            for f, url in targets
            if progress.get(f.name, {}).get("status") != "done"
        ]

    if args.limit:
        targets = targets[: args.limit]

    list_targets(targets, progress)

    if not targets:
        print("\n処理対象なし。終了。")
        return 0

    if args.dry_run:
        return 0

    print()
    confirm = input(f"{len(targets)} 件を note.com 上で更新します。続行？ (y/N): ")
    if confirm.lower() != "y":
        print("中止しました。")
        return 0

    from playwright.sync_api import sync_playwright

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    for lock_file in ["SingletonLock", "SingletonCookie", "SingletonSocket"]:
        lock_path = PROFILE_DIR / lock_file
        if lock_path.exists():
            lock_path.unlink()

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

        # ─ ログイン確認 ───────────────────────────────────────────
        page.goto("https://note.com/notes/new", wait_until="networkidle")
        page.wait_for_timeout(3000)
        if any(kw in page.url for kw in ["login", "signin", "auth"]):
            print("\nログインセッションなし。ブラウザでログインしてください。")
            print("ログイン完了後、Enter を押してください...")
            input()

        success_count = 0
        failed = []

        for i, (f, url) in enumerate(targets, 1):
            print(f"\n[{i}/{len(targets)}] {f.name}")
            try:
                ok, msg = update_one(page, f, url)
            except Exception as e:
                ok, msg = False, f"例外: {e}"

            progress[f.name] = {
                "status": "done" if ok else "failed",
                "url": url,
                "msg": msg,
                "updated_at": datetime.now().isoformat(),
            }
            save_progress(progress)

            if ok:
                print(f"  ✓ {msg}")
                success_count += 1
            else:
                print(f"  ✗ {msg}")
                failed.append((f.name, msg))

            if i < len(targets):
                print(f"  待機 {args.delay}s...")
                time.sleep(args.delay)

        ctx.close()

    print(f"\n=== 完了 ===")
    print(f"  成功: {success_count}/{len(targets)}")
    if failed:
        print(f"  失敗:")
        for name, msg in failed:
            print(f"    - {name}: {msg}")
    print(f"\n  進行ログ: {PROGRESS_FILE}")

    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
