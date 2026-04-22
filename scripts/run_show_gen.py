#!/usr/bin/env python3
"""
ショーコンテンツ生成スクリプト（汎用）
run_pipeline.sh からショーID・テーマ付きで呼び出される。

使い方:
  python3 scripts/run_show_gen.py --show aitsm --theme "筋トレすると自己肯定感が上がる説"
  python3 scripts/run_show_gen.py --show aitsm --theme "..." --dry-run

新しいショーを追加するときは scripts/shows/ を参照。
"""

import argparse
from datetime import date
from pathlib import Path

from soda_utils import SODA_DIR, PYTHON, run_claude, notify_error, write_content_mode
from shows import get_show


def main() -> None:
    parser = argparse.ArgumentParser(description="ショーコンテンツ生成（汎用）")
    parser.add_argument("--show",  required=True, help="ショーID（例: aitsm）")
    parser.add_argument("--theme", required=True, help="今日のテーマ（会議ログから渡される）")
    parser.add_argument("--dry-run", action="store_true", help="プロンプトだけ表示")
    args = parser.parse_args()

    show = get_show(args.show)
    today = date.today()
    ds = str(today)
    prompt = show.build_prompt(args.theme, ds)

    if args.dry_run:
        print("=== PROMPT ===")
        print(prompt)
        return

    log_file = SODA_DIR / "logs" / "cron" / f"{ds}_{args.show}_gen.log"
    print(f"[{ds}] {show.SHOW_NAME} 生成開始: {args.theme}")

    result = run_claude(prompt, tools=["Read", "Write", "Edit", "Glob"])
    log_file.write_text(result.stdout + result.stderr)

    if result.returncode != 0:
        notify_error(
            f"{show.SHOW_NAME}生成",
            f"run_show_gen.py --show {args.show} が失敗しました（exit: {result.returncode}）",
        )
        print(f"エラー: {result.stderr[-300:]}")
        return

    # 生成ファイルの確認
    x_files   = sorted((SODA_DIR / "content" / "x_posts").glob(f"{ds}_{args.show}*.md"))
    note_files = sorted((SODA_DIR / "content" / "note").glob(f"{ds}_{args.show}*.md"))

    if x_files and note_files:
        print(f"X投稿: {x_files[0].name}")
        print(f"note記事: {note_files[0].name}")

        # note_post.py が自動公開できるよう CEO スコア 5 を書き込む
        score_file = SODA_DIR / "logs" / "daily" / f"{ds}_ceo_score.txt"
        score_file.parent.mkdir(parents=True, exist_ok=True)
        if not score_file.exists():
            score_file.write_text(f"5\n{show.SHOW_NAME}自動生成コンテンツ（スコア自動設定）\n")

        for line in result.stdout.splitlines():
            if "生成完了" in line:
                print(line)
                break
    else:
        print("警告: ファイルが生成されませんでした")
        print(result.stdout[-500:])


if __name__ == "__main__":
    main()
