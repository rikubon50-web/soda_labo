#!/usr/bin/env python3
"""
リプライキーワード見直しスクリプト（毎週日曜21:00）
直近1週間のリプライ実績を分析し、config/reply_keywords.json を更新する。
使い方:
  python3 scripts/run_keyword_review.py
  python3 scripts/run_keyword_review.py --dry-run
"""

import os
from dotenv import load_dotenv
import json
import argparse
import subprocess
from pathlib import Path
from datetime import date, timedelta

SODA_DIR = Path(__file__).parent.parent
load_dotenv(SODA_DIR / ".env")
CLAUDE = os.path.expanduser("~/.local/bin/claude")
PYTHON = os.environ.get("PYTHON_PATH", "/Users/rikubon50/.pyenv/shims/python3")

PROMPT_TEMPLATE = """\
あなたはSODAのAnalystとCEOです。
直近1週間のX自動リプライ実績を分析し、検索キーワードを見直してください。

## 目的

検索キーワードの精度を上げる。
「承認率が低い（CEOにボツにされる）」「そもそも候補が少ない」キーワードは改善または入れ替える。

## 実行手順

1. config/reply_keywords.json を Read toolで読む（現在のキーワード確認）
2. 以下の直近ログを Read toolで読む（存在するもののみ）
{LOG_LIST}
3. 以下の分析を行う
4. config/reply_keywords.json を Edit toolで更新する

## 分析観点

- **承認率**: キーワードごとに「候補数 vs 承認数」を集計する（ログから読み取れる範囲で）
- **ツイートの質**: そのキーワードで引っかかったツイートがSODAの読者層（AIに関心がある20代）と合致しているか
- **競合性**: そのキーワードは他の大アカウントも使っていて埋もれていないか

## キーワード更新ルール

- キーワードは常に5個を維持する
- 承認率が0/3以下のキーワードは入れ替え候補
- 新キーワードは以下の条件を満たすこと
  - 日本語ツイートで実際に使われている自然な表現
  - SODAの想定読者（AIに関心がある20代）が書きそうな内容
  - 「-is:retweet -is:reply lang:ja」でそれなりに件数が取れそうな表現
- キーワードを変えない場合も必ずその理由を書く

## 出力フォーマット（config/reply_keywords.json の更新内容）

{{
  "keywords": ["キーワード1", "キーワード2", "キーワード3", "キーワード4", "キーワード5"],
  "updated_at": "{TODAY}",
  "updated_by": "keyword_review",
  "analysis": {{
    "変更あり": true または false,
    "変更理由": "1〜2文で説明",
    "廃止キーワード": ["廃止したもの"],
    "新規キーワード": ["追加したもの"]
  }}
}}

上記フォーマットで config/reply_keywords.json を Edit toolで上書き保存すること。
"""


def collect_recent_logs(days: int = 7) -> list[Path]:
    log_dir = SODA_DIR / "logs" / "daily"
    logs = []
    for i in range(days):
        ds = str(date.today() - timedelta(days=i))
        f = log_dir / f"{ds}_reply_candidates.md"
        if f.exists():
            logs.append(f)
    return logs


def build_prompt(today: date) -> str:
    logs = collect_recent_logs()
    if logs:
        log_list = "\n".join(f"- {p.relative_to(SODA_DIR)}" for p in logs)
    else:
        log_list = "- （直近1週間のリプライログなし — 初回実行の場合はキーワードの仮説ベース評価を行う）"

    return PROMPT_TEMPLATE.replace("{LOG_LIST}", log_list).replace("{TODAY}", str(today))


def main():
    parser = argparse.ArgumentParser(description="リプライキーワード見直しスクリプト")
    parser.add_argument("--dry-run", action="store_true", help="プロンプトだけ表示")
    args = parser.parse_args()

    today = date.today()
    prompt = build_prompt(today)

    if args.dry_run:
        print("=== PROMPT ===")
        print(prompt)
        return

    log_file = SODA_DIR / "logs" / "cron" / f"{today}_keyword_review.log"
    print(f"[{today}] キーワード見直しを開始...")

    result = subprocess.run(
        [CLAUDE, "-p", "--dangerously-skip-permissions", "--allowedTools", "Read,Edit"],
        input=prompt,
        cwd=str(SODA_DIR),
        capture_output=True,
        text=True,
        timeout=1800,
    )

    log_file.write_text(result.stdout + result.stderr)

    if result.returncode != 0:
        subprocess.run(
            [PYTHON, str(SODA_DIR / "scripts" / "notify_error.py"),
             "キーワード見直し", f"run_keyword_review.py が失敗しました（exit: {result.returncode}）"],
            cwd=str(SODA_DIR),
        )
        print(f"エラー: {result.stderr[-300:]}")
        return

    kw_file = SODA_DIR / "config" / "reply_keywords.json"
    if kw_file.exists():
        data = json.loads(kw_file.read_text())
        print(f"キーワード更新完了: {data['keywords']}")
        if data.get("analysis", {}).get("変更あり"):
            print(f"変更理由: {data['analysis'].get('変更理由', '')}")
    else:
        print("警告: キーワードファイルが更新されませんでした")


if __name__ == "__main__":
    main()
