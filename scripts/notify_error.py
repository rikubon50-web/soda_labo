#!/usr/bin/env python3
"""
エラーログスクリプト
エラーを logs/errors/{today}_errors.log に追記する。
使い方: python3 scripts/notify_error.py "ステップ名" "詳細メッセージ"
"""
import sys
from datetime import date, datetime
from pathlib import Path


def log_error(step: str, detail: str) -> None:
    today = date.today().strftime("%Y-%m-%d")
    ts = datetime.now().strftime("%H:%M:%S")
    log_dir = Path(__file__).parent.parent / "logs" / "errors"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{today}_errors.log"
    with log_file.open("a", encoding="utf-8", errors="replace") as f:
        f.write(f"[{ts}] {step}: {detail}\n")
    print(f"エラー記録: {step}")


if __name__ == "__main__":
    step = sys.argv[1] if len(sys.argv) > 1 else "不明なステップ"
    detail = sys.argv[2] if len(sys.argv) > 2 else "詳細不明"
    log_error(step, detail)
