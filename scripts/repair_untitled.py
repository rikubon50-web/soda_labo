#!/usr/bin/env python3
"""「無題」公開事故（2026-08-18/19）の修復: 公開済み記事のタイトル設定とサムネイル差し替え。
使い捨てスクリプト。note_post.py の実績あるセレクタ・関数を流用する。

使い方: python3 scripts/repair_untitled.py [--dry-run]
"""
import sys
import argparse
import importlib.util
from pathlib import Path

SODA_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SODA_DIR / "scripts"))

spec = importlib.util.spec_from_file_location("note_post", SODA_DIR / "scripts" / "note_post.py")
np = importlib.util.module_from_spec(spec)
spec.loader.exec_module(np)

TARGETS = [
    ("content/note/2026-08-18_AI店長解雇.md", "nd6812fdcf041"),
    ("content/note/2026-08-19_stripe-openrouter-oracle.md", "n8babf01b7e74"),
]

TITLE_SELECTORS = [
    'textarea[placeholder*="タイトル"]',
    'textarea[aria-label*="タイトル"]',
    '[contenteditable="true"][data-placeholder*="タイトル"]',
]


def repair(page, md_path: str, note_key: str, dry_run: bool) -> bool:
    title, body = np.parse_article(str(SODA_DIR / md_path))
    print(f"--- {note_key}: 「{title[:40]}」")
    if dry_run:
        return True

    page.goto(f"https://editor.note.com/notes/{note_key}/edit/", wait_until="networkidle", timeout=45000)
    page.wait_for_timeout(3000)

    # お知らせ等のモーダル（ReactModal/MessageModal）がクリックを阻むので先に閉じる
    for _ in range(3):
        overlay = page.query_selector('.ReactModal__Overlay')
        if not overlay:
            break
        close_btn = page.query_selector('.ReactModal__Overlay button[aria-label*="閉じる"], .ReactModal__Overlay button:has-text("閉じる"), .ReactModal__Overlay [class*="close"]')
        if close_btn:
            close_btn.click()
        else:
            page.keyboard.press("Escape")
        page.wait_for_timeout(1500)

    # タイトル設定（既存の「無題」をクリアして入力）
    tbox = None
    for sel in TITLE_SELECTORS:
        tbox = page.query_selector(sel)
        if tbox:
            break
    if not tbox:
        print("  NG: タイトル欄が見つからない")
        return False
    tbox.click()
    page.keyboard.press("Meta+A")
    page.keyboard.press("Backspace")
    tbox.type(title, delay=10)
    page.wait_for_timeout(1000)
    print("  タイトル設定完了")

    # サムネイル再生成→アップロード（note_post の実績フローを流用。失敗しても続行）
    try:
        thumb = np.generate_thumbnail(title, filepath=str(SODA_DIR / md_path), body=body)
        if thumb:
            np.upload_thumbnail(page, thumb)
            print("  サムネイル差し替え完了")
    except Exception as e:
        print(f"  WARN: サムネイル差し替え失敗（タイトル修正は続行）: {str(e)[:120]}")

    # 更新（再公開）: note_post の実績ある2段階フローを流用し、更新系ボタンも試す
    if np._publish(page, title):
        print("  更新完了（_publish経由）")
        return True
    for first_sel in ['button:has-text("更新")', 'button:has-text("公開に進む")']:
        btn = page.query_selector(first_sel)
        if btn:
            btn.click()
            page.wait_for_timeout(2500)
            for confirm_sel in ['button:has-text("投稿する")', 'button:has-text("更新する")', 'button:has-text("更新")']:
                btn2 = page.query_selector(confirm_sel)
                if btn2:
                    btn2.click()
                    page.wait_for_timeout(4000)
                    print("  更新完了")
                    return True
    print("  NG: 更新ボタンが見つからない（要手動確認）")
    from datetime import datetime
    page.screenshot(path=f"logs/errors/repair_untitled_{datetime.now():%H%M%S}.png")
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--key", help="このnote keyのみ修復")
    args = parser.parse_args()

    if args.dry_run:
        for md, key in TARGETS:
            repair(None, md, key, True)
        return 0

    pw, ctx = np.launch_ctx() if hasattr(np, "launch_ctx") else (None, None)
    if ctx is None:
        # note_post 内の起動関数名が違う場合に備えた直接起動（同一パターン）
        from playwright.sync_api import sync_playwright
        profile = SODA_DIR / ".browser_profile" / "note"
        for lock in ["SingletonLock", "SingletonCookie", "SingletonSocket"]:
            lp = profile / lock
            if lp.exists():
                lp.unlink()
        pw = sync_playwright().start()
        ctx = pw.chromium.launch_persistent_context(str(profile), headless=True, locale="ja-JP", timezone_id="Asia/Tokyo")
    try:
        page = ctx.new_page()
        targets = [(md, key) for md, key in TARGETS if not args.key or key == args.key]
        results = [repair(page, md, key, False) for md, key in targets]
        return 0 if all(results) else 1
    finally:
        ctx.close()
        pw.stop()


if __name__ == "__main__":
    sys.exit(main())
