#!/usr/bin/env python3
"""
沈黙検知スクリプト（毎日9:00 cron想定）。
前日（date.today() - timedelta(days=1)）について、期待される産出物が揃っているか確認する。
欠損があれば notify_error.py（Gmail通知）を呼ぶ。全部OKなら .env の HEALTHCHECK_URL へ
外形監視ping（未設定ならスキップ、失敗しても無視）。Claude不使用の純Pythonスクリプト。

使い方:
  python3 scripts/health_check.py                     # 通常実行（前日を判定）
  python3 scripts/health_check.py --date 2026-08-12    # 対象日を指定（テスト用）
  python3 scripts/health_check.py --dry-run            # 通知・pingを行わず判定表示のみ
"""

import argparse
import json
import os
import sys
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

SODA_DIR = Path(__file__).parent.parent
load_dotenv(SODA_DIR / ".env")

WEEKEND_WEEKDAYS = (5, 6)  # 土, 日
SUNDAY = 6


def parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def check_metrics(ds: str) -> tuple[bool, str]:
    """logs/metrics/{ds}.json の存在確認（毎日必須）"""
    path = SODA_DIR / "logs" / "metrics" / f"{ds}.json"
    if path.exists():
        return True, f"logs/metrics/{ds}.json"
    return False, f"logs/metrics/{ds}.json が存在しない"


def check_content(target: date, ds: str) -> tuple[bool, str]:
    """content/note/{ds}_*.md または content/news/{ds}_memo.md の存在確認（毎日どちらか必須）。
    土日は記事のみ有効（メモでは合格にしない）。"""
    note_files = sorted((SODA_DIR / "content" / "note").glob(f"{ds}_*.md"))
    if note_files:
        return True, f"content/note/{note_files[0].name}"

    if target.weekday() in WEEKEND_WEEKDAYS:
        return False, f"content/note/{ds}_*.md が存在しない（土日はメモ不可）"

    memo_path = SODA_DIR / "content" / "news" / f"{ds}_memo.md"
    if memo_path.exists():
        return True, f"content/news/{ds}_memo.md"

    return False, f"content/note/{ds}_*.md も content/news/{ds}_memo.md も存在しない"


def check_weekly(target: date, ds: str):
    """対象日が日曜のときだけ logs/weekly/{ds}*.md の存在確認。対象外なら None を返す。"""
    if target.weekday() != SUNDAY:
        return None
    weekly_files = sorted((SODA_DIR / "logs" / "weekly").glob(f"{ds}*.md"))
    if weekly_files:
        return True, f"logs/weekly/{weekly_files[0].name}"
    return False, f"logs/weekly/{ds}*.md が存在しない（日曜必須）"


def check_follower_log(ds: str) -> tuple[bool, str]:
    """logs/ops/follower_log.jsonl に対象日の行があるか確認。"""
    path = SODA_DIR / "logs" / "ops" / "follower_log.jsonl"
    if not path.exists():
        return False, "logs/ops/follower_log.jsonl が存在しない"
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("date") == ds:
            return True, f"follower_log.jsonl に{ds}の行あり"
    return False, f"logs/ops/follower_log.jsonl に{ds}の行がない"


def ping_healthcheck(url: str) -> None:
    """外形監視へGET ping。失敗しても無視する。"""
    try:
        urllib.request.urlopen(url, timeout=10)
    except Exception:
        pass


def main() -> int:
    parser = argparse.ArgumentParser(description="SODA 沈黙検知（前日産出物の存在確認+外形監視ping）")
    parser.add_argument("--date", type=str, default=None, help="対象日 YYYY-MM-DD（省略時は前日、テスト用）")
    parser.add_argument("--dry-run", action="store_true", help="通知・pingを行わず判定表示のみ")
    args = parser.parse_args()

    target = parse_date(args.date) if args.date else date.today() - timedelta(days=1)
    ds = target.strftime("%Y-%m-%d")

    checks: list[tuple[str, bool, str]] = []

    checks.append(("メトリクス", *check_metrics(ds)))
    checks.append(("note記事/ニュースメモ", *check_content(target, ds)))

    weekly_result = check_weekly(target, ds)
    if weekly_result is not None:
        checks.append(("週次まとめ（日曜）", *weekly_result))

    checks.append(("フォロワーログ", *check_follower_log(ds)))

    missing = [(name, detail) for name, ok, detail in checks if not ok]

    print(f"=== 沈黙検知: {ds} ===")
    for name, ok, detail in checks:
        mark = "✅" if ok else "❌"
        print(f"{mark} {name}: {detail}")

    if missing:
        summary = "、".join(name for name, _ in missing)
        detail_text = "\n".join(f"- {name}: {detail}" for name, detail in missing)
        print(f"\n判定: NG（欠損 {len(missing)}件: {summary}）")

        if args.dry_run:
            print("（--dry-run のため通知はスキップ）")
        else:
            from soda_utils import notify_error
            notify_error("沈黙検知", f"{ds}の産出物に欠損があります。\n{detail_text}")

        return 1

    print("\n判定: OK（欠損なし）")

    healthcheck_url = os.environ.get("HEALTHCHECK_URL")
    if not healthcheck_url:
        print("HEALTHCHECK_URL未設定のため外形監視pingはスキップ")
    elif args.dry_run:
        print("（--dry-run のため外形監視pingはスキップ）")
    else:
        ping_healthcheck(healthcheck_url)
        print("外形監視pingを送信しました")

    return 0


if __name__ == "__main__":
    sys.exit(main())
