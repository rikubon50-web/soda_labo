#!/usr/bin/env python3
"""
noteメトリクス取得スクリプト（毎日22:30）
note.com のクリエイター統計API（要ログインセッション）から
記事別のビュー・スキ・コメント数を取得して logs/metrics/ に保存する。

使い方:
  python3 scripts/note_metrics.py           # 実行
  python3 scripts/note_metrics.py --dry-run # 取得結果を表示するだけで保存しない
"""

import json
import sys
import argparse
from datetime import date, datetime
from pathlib import Path

SODA_DIR    = Path(__file__).parent.parent
PROFILE_DIR = SODA_DIR / ".browser_profile" / "note"
METRICS_DIR = SODA_DIR / "logs" / "metrics"
ERRORS_DIR  = SODA_DIR / "logs" / "errors"

STATS_API = "https://note.com/api/v1/stats/pv?filter=all&page=1&sort=pv"


def fetch_stats() -> dict:
    """ログイン済みプロファイルで統計APIを叩き、生JSONを返す"""
    from playwright.sync_api import sync_playwright

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    # note_post.py と同様、他プロセスの異常終了で残ったロックファイルを掃除する
    for lock_file in ["SingletonLock", "SingletonCookie", "SingletonSocket"]:
        lock_path = PROFILE_DIR / lock_file
        if lock_path.exists():
            lock_path.unlink()

    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            str(PROFILE_DIR),
            headless=True,
        )
        try:
            page = ctx.new_page()
            resp = page.goto(STATS_API, wait_until="domcontentloaded", timeout=30000)
            if resp is None or resp.status != 200:
                raise RuntimeError(f"統計APIがHTTP {resp.status if resp else '不明'} を返しました（セッション切れの可能性）")
            body = page.evaluate("() => document.body.innerText")
            return json.loads(body)
        finally:
            ctx.close()


def parse_articles(raw: dict) -> list[dict]:
    """APIレスポンスから記事別メトリクスを抽出する"""
    stats = raw.get("data", {}).get("note_stats", [])
    articles = []
    for s in stats:
        articles.append({
            "title":    s.get("name", ""),
            "key":      s.get("key", ""),
            "views":    int(s.get("read_count", 0)),
            "likes":    int(s.get("like_count", 0)),
            "comments": int(s.get("comment_count", 0)),
        })
    return articles


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    raw = None
    try:
        raw = fetch_stats()
        articles = parse_articles(raw)
        if not articles:
            raise ValueError("記事メトリクスが0件（APIレスポンス形式が想定と違う可能性）")
    except Exception as e:
        ERRORS_DIR.mkdir(parents=True, exist_ok=True)
        dump = ERRORS_DIR / f"note_metrics_{datetime.now():%Y%m%d_%H%M%S}.txt"
        detail = str(e)
        try:
            dump.write_text(json.dumps(raw, ensure_ascii=False, indent=2))
            detail += f"（生レスポンス: {dump}）"
        except Exception:
            pass
        print(f"noteメトリクス取得失敗: {detail}", file=sys.stderr)
        import subprocess
        subprocess.run(
            [sys.executable, str(SODA_DIR / "scripts" / "notify_error.py"),
             "noteメトリクス取得", detail[:300]],
            cwd=str(SODA_DIR),
        )
        return 1

    result = {"date": str(date.today()), "source": "note", "articles": articles}

    if args.dry_run:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    METRICS_DIR.mkdir(parents=True, exist_ok=True)
    out = METRICS_DIR / f"{date.today()}.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"保存: {out}（{len(articles)}記事）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
