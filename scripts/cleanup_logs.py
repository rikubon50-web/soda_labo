#!/usr/bin/env python3
"""
ログ掃除スクリプト（毎週日曜 23:00）
90日以上古いログファイルを削除し、product_seeds.md の肥大化を防ぐ。
使い方:
  python3 scripts/cleanup_logs.py          # 実行
  python3 scripts/cleanup_logs.py --dry-run  # 削除対象を表示するだけ
"""

import argparse
from pathlib import Path
from datetime import date, timedelta

SODA_DIR = Path(__file__).parent.parent
KEEP_DAYS = 90


def cleanup_dir(directory: Path, pattern: str, cutoff: date, dry_run: bool) -> int:
    if not directory.exists():
        return 0
    removed = 0
    for f in sorted(directory.glob(pattern)):
        date_str = f.name[:10]
        try:
            file_date = date.fromisoformat(date_str)
        except ValueError:
            continue
        if file_date < cutoff:
            if dry_run:
                print(f"[DRY] 削除対象: {f.relative_to(SODA_DIR)}")
            else:
                f.unlink()
                print(f"削除: {f.relative_to(SODA_DIR)}")
            removed += 1
    return removed


def trim_product_seeds(dry_run: bool) -> None:
    """product_seeds.md が500KB超なら古いエントリを削除"""
    seeds_file = SODA_DIR / "products" / "product_seeds.md"
    if not seeds_file.exists():
        return
    size_kb = seeds_file.stat().st_size / 1024
    if size_kb < 500:
        return

    content = seeds_file.read_text()
    entries = content.split("\n# 商品メモ — ")
    header = entries[0]
    memos = entries[1:]

    cutoff = date.today() - timedelta(days=KEEP_DAYS)
    keep = [m for m in memos if m[:10] >= str(cutoff)]
    removed = len(memos) - len(keep)

    if removed == 0:
        return

    new_content = header + "\n# 商品メモ — ".join([""] + keep).lstrip("\n# 商品メモ — ")
    new_content = "# SODA 商品タネバンク\n\n" + "\n# 商品メモ — ".join(keep)

    if dry_run:
        print(f"[DRY] product_seeds.md: {removed}件の古いエントリを削除予定（現在{size_kb:.0f}KB）")
    else:
        seeds_file.write_text(new_content)
        print(f"product_seeds.md: {removed}件削除（{size_kb:.0f}KB → {len(new_content)/1024:.0f}KB）")


def main():
    parser = argparse.ArgumentParser(description="SODAログ掃除スクリプト")
    parser.add_argument("--dry-run", action="store_true", help="削除対象を表示するだけ")
    args = parser.parse_args()

    today = date.today()
    cutoff = today - timedelta(days=KEEP_DAYS)
    total = 0

    print(f"掃除開始: {today} / {KEEP_DAYS}日以前（{cutoff}以前）を削除")

    targets = [
        (SODA_DIR / "logs" / "daily",   "????-??-??_*.md"),
        (SODA_DIR / "logs" / "daily",   "????-??-??.md"),
        (SODA_DIR / "logs" / "ideas",   "????-??-??_*.md"),
        (SODA_DIR / "logs" / "metrics", "????-??-??.json"),
        (SODA_DIR / "logs" / "weekly",  "????-??-??.md"),
        (SODA_DIR / "logs" / "cron",    "????-??-??_*.log"),
    ]

    for directory, pattern in targets:
        n = cleanup_dir(directory, pattern, cutoff, args.dry_run)
        total += n

    trim_product_seeds(args.dry_run)

    print(f"完了: {total}ファイル{'（DRY RUN）' if args.dry_run else '削除'}")


if __name__ == "__main__":
    main()
