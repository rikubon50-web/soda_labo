#!/usr/bin/env python3
"""
noteメトリクス取得スクリプト（毎日22:30）
note.com のクリエイター統計API（要ログインセッション）から
記事別のビュー・スキ・コメント数を取得して logs/metrics/ に保存する。

取得範囲: 統計APIは sort=pv/like/comment のみ対応（公開日時順ソートは非対応、
sort=pub_date 等は400エラー）なので、上位N件だけの取得だと前日公開でまだ
PVが少ない記事が漏れる。そのため全ページを走査して記事を漏れなく取得する
（実測: 公開済み110記事・PV降順で前日公開記事が103位になるケースを確認済み）。

使い方:
  python3 scripts/note_metrics.py           # 実行
  python3 scripts/note_metrics.py --dry-run # 取得結果を表示するだけで保存しない
"""

import json
import sys
import time
import argparse
from datetime import date, datetime
from pathlib import Path

SODA_DIR    = Path(__file__).parent.parent
PROFILE_DIR = SODA_DIR / ".browser_profile" / "note"
METRICS_DIR = SODA_DIR / "logs" / "metrics"
ERRORS_DIR  = SODA_DIR / "logs" / "errors"

STATS_API_TEMPLATE = "https://note.com/api/v1/stats/pv?filter=all&page={page}&sort=pv"
MAX_PAGES = 50  # 安全装置（無限ループ防止。2026-08時点の公開記事は110件・約10ページ）


def fetch_stats() -> dict:
    """ログイン済みプロファイルで統計APIを叩き、全ページを結合した生JSONを返す。

    note.comの統計APIは日時順ソートに対応していないため、`last_page` が
    true になるまでページを進めて note_stats を連結する（key で重複除去）。
    """
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
            merged_stats: list = []
            seen_keys: set = set()
            first_raw: dict | None = None

            for page_num in range(1, MAX_PAGES + 1):
                if page_num > 1:
                    time.sleep(1)  # ページ間のレート制御

                url = STATS_API_TEMPLATE.format(page=page_num)
                resp = page.goto(url, wait_until="domcontentloaded", timeout=30000)
                if resp is None or resp.status != 200:
                    # 生レスポンス（あれば）をエラーメッセージに含める。
                    # ブリーフの設計意図（失敗時に生レスポンスを見てキー名を調整できる）が
                    # HTTPエラー経路でも機能するようにする。
                    status = resp.status if resp else "不明"
                    try:
                        err_body = page.evaluate("() => document.body.innerText") if resp else ""
                    except Exception:
                        err_body = ""
                    detail = f"url={url}"
                    if err_body:
                        detail += f" body={err_body[:1000]}"
                    raise RuntimeError(
                        f"統計APIがHTTP {status} を返しました（セッション切れの可能性）（{detail}）"
                    )
                body = page.evaluate("() => document.body.innerText")
                raw = json.loads(body)
                if first_raw is None:
                    first_raw = raw

                stats = raw.get("data", {}).get("note_stats", [])
                for s in stats:
                    key = s.get("key", "")
                    if key and key in seen_keys:
                        continue
                    seen_keys.add(key)
                    merged_stats.append(s)

                if raw.get("data", {}).get("last_page", True) or not stats:
                    break

            if first_raw is None:
                raise RuntimeError("統計APIから何も取得できませんでした")
            first_raw["data"]["note_stats"] = merged_stats
            return first_raw
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
