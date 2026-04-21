#!/usr/bin/env python3
"""
商品メモスクリプト（毎日21:00）
今日の反応から悩み・商品案・タイトル・内容を1つずつ掘り出して蓄積する。
使い方:
  python3 scripts/run_product_memo.py          # 実行
  python3 scripts/run_product_memo.py --dry-run  # プロンプトだけ表示
"""

import os
import argparse
import subprocess
from pathlib import Path
from datetime import date

SODA_DIR = Path(__file__).parent.parent
CLAUDE = os.path.expanduser("~/.local/bin/claude")
PYTHON = "/Users/rikubon50/.pyenv/shims/python3"

PRODUCT_SEEDS = SODA_DIR / "products" / "product_seeds.md"

MEMO_PROMPT = """\
あなたはSODAの商品開発担当です。
今日の反応データから、低単価商品のタネを1つ掘り出してください。

## ルール

- 昨日の投稿データ（今日08:45に完了した分析）から「最も反応のあった悩み」を1つ特定する
- その悩みを解決する商品を1つだけ考える
- 有料noteかPDFで¥1,000以下で売れるスケールで考える
- 気合で作るものではなく「今日の反応の延長線上にあるもの」を選ぶ
- 反応データがない日は、今日の記事テーマから推定する

## 判断基準

「この悩みを持つ人が¥1,000を出すか？」だけを問う。
完成度より具体性。「〇〇をまとめたPDF」より「〇〇の失敗を避けるチェックリスト20項目」の方が売れる。

## 出力フォーマット（必ずこの形式で出力すること）

# 商品メモ — {DATE}

## 今日よく反応した悩み
（1文で。「〜という悩み」の形で書く）

## それを解決する小商品案
（1文で。何を作るか）

## 売るならタイトル
「（タイトル。具体的な数字や状況を入れると強い）」

## ¥1,000で売るなら何を入れるか
- （具体的なコンテンツ1）
- （具体的なコンテンツ2）
- （具体的なコンテンツ3）
- （具体的なコンテンツ4、あれば）

## 作るとしたらいつか
（すぐ / 1週間以内 / 1ヶ月以内 / 将来）＋理由1文
"""


def collect_today_data() -> dict:
    today = date.today()
    ds = str(today)
    data: dict = {"date": ds}

    # 今日の投稿分析（反応データの主ソース）
    analysis_file = SODA_DIR / "logs" / "daily" / f"{ds}_post_analysis.md"
    data["analysis"] = analysis_file.read_text() if analysis_file.exists() else ""

    # 今日のCTA記録
    cta_file = SODA_DIR / "logs" / "daily" / f"{ds}_cta.md"
    data["cta"] = cta_file.read_text() if cta_file.exists() else ""

    # 今日のアイデア資産（会議から掘り出したもの）
    ideas_file = SODA_DIR / "logs" / "ideas" / f"{ds}_ideas.md"
    data["ideas"] = ideas_file.read_text() if ideas_file.exists() else ""

    # 今日のnote記事（テーマ確認）
    note_files = sorted((SODA_DIR / "content" / "note").glob(f"{ds}_*.md"))
    data["note_content"] = note_files[0].read_text()[:500] if note_files else ""

    # 既存の商品タネ（重複を避けるため）
    data["existing_seeds"] = PRODUCT_SEEDS.read_text()[-2000:] if PRODUCT_SEEDS.exists() else ""

    return data


def build_prompt(data: dict, today: date) -> str:
    ds = str(today)
    lines = [
        MEMO_PROMPT.replace("{DATE}", ds),
        "",
        "---",
        f"## 本日（{ds}）のデータ",
        "",
    ]

    if data["analysis"]:
        lines.append("### 昨日の投稿分析（反応データ）※昨日の投稿に対する分析結果")
        lines.append(data["analysis"])
        lines.append("")

    if data["cta"]:
        lines.append("### CTA記録")
        # 決定したCTAと評価だけ抜粋
        content = data["cta"]
        start = content.find("## 今日のCTA決定")
        end = content.find("## 明日のCTA仮説")
        excerpt = content[start:end].strip() if start != -1 and end != -1 else content[:400]
        lines.append(excerpt)
        lines.append("")

    if data["ideas"]:
        lines.append("### 今日のアイデア資産（商品候補の参考）")
        # 有料商品候補セクションだけ抜粋
        content = data["ideas"]
        lines.append(content[:1200])
        lines.append("")

    if data["note_content"]:
        lines.append("### 今日のnote記事（先頭500字）")
        lines.append(data["note_content"])
        lines.append("")

    if data["existing_seeds"]:
        lines.append("### 既存の商品タネ（直近）※重複しないこと")
        lines.append(data["existing_seeds"])
        lines.append("")

    lines.append(
        f"上記データを分析し、出力フォーマットに従って "
        f"logs/daily/{today}_product_memo.md に Write toolで保存せよ。\n"
        f"次に、同じ内容を products/product_seeds.md の末尾に追記せよ（上書きでなく追記）。\n"
        f"product_seeds.md が存在しない場合は '# SODA 商品タネバンク\\n\\n' で始めて作成する。\n"
        f"保存完了後は「商品メモ完了: [タイトル]」と出力して終了すること。"
    )

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="SODA商品メモスクリプト")
    parser.add_argument("--dry-run", action="store_true", help="プロンプトだけ表示")
    args = parser.parse_args()

    today = date.today()
    data = collect_today_data()
    prompt = build_prompt(data, today)

    if args.dry_run:
        print("=== PROMPT ===")
        print(prompt)
        return

    log_file = SODA_DIR / "logs" / "cron" / f"{today}_product_memo.log"
    print(f"[{today}] 商品メモを開始...")

    result = subprocess.run(
        [
            CLAUDE, "-p",
            "--dangerously-skip-permissions",
            "--allowedTools", "Read,Write",
        ],
        input=prompt,
        cwd=str(SODA_DIR),
        capture_output=True,
        text=True,
        timeout=1800,
    )

    log_file.write_text(result.stdout + result.stderr)

    if result.returncode != 0:
        subprocess.run(
            [
                PYTHON, str(SODA_DIR / "scripts" / "notify_error.py"),
                "商品メモ", f"run_product_memo.py が失敗しました（exit: {result.returncode}）",
            ],
            cwd=str(SODA_DIR),
        )
        print(f"エラー: {result.stderr[-300:]}")
        return

    memo_file = SODA_DIR / "logs" / "daily" / f"{today}_product_memo.md"
    if memo_file.exists():
        print(f"商品メモ保存完了: {memo_file}")
        print(memo_file.read_text())
    else:
        print("警告: 商品メモファイルが作成されませんでした")
        print(result.stdout[-500:])


if __name__ == "__main__":
    main()
