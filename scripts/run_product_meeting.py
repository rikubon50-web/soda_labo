#!/usr/bin/env python3
"""
商品化会議スクリプト（毎週水曜20:00）
今週のデータから商品企画を1つ立案し、バックログに積む。
使い方:
  python3 scripts/run_product_meeting.py          # 実行
  python3 scripts/run_product_meeting.py --dry-run  # プロンプトだけ表示
"""

import os
from dotenv import load_dotenv
import argparse
import subprocess
from pathlib import Path
from datetime import date, timedelta

SODA_DIR = Path(__file__).parent.parent
load_dotenv(SODA_DIR / ".env")
CLAUDE = os.path.expanduser("~/.local/bin/claude")
PYTHON = os.environ.get("PYTHON_PATH", "/Users/rikubon50/.pyenv/shims/python3")

PRODUCT_BACKLOG = SODA_DIR / "products" / "product_backlog.md"

MEETING_PROMPT = """\
あなたはSODAの商品化会議の司会です。
今週のデータを基に、以下の4テーマで会議を進め、小商品を1つ企画してください。

## 会議の4テーマ（必ず順番に議論すること）

### テーマ1: 今週伸びたテーマは何か
- 投稿分析の「伸びた理由」を横断して共通パターンを探す
- インプレッション・ブックマーク・返信のどれが多かったか
- 感覚でなく数値・記録から判断する

### テーマ2: その中で金になる悩みは何か
- 「反応が多い = 読んでほしいだけ」ではない
- 「これ解決したくて困ってる人がいる」悩みを特定する
- 商品タネバンクの中から「すでにお金になりそう」なものを1つ選ぶ
- 基準: その悩みを持つ人が¥1,000を出すか？

### テーマ3: 100円〜1500円で売れる形は何か
- 価格帯ごとに何が売れるかを考える
  - ¥100〜300: チェックリスト・テンプレ1枚・プロンプト集
  - ¥500〜800: PDF数ページ・有料note・小冊子
  - ¥1,000〜1,500: まとめPDF・テンプレセット・有料note（詳細版）
- 今の発信ストックで「今週中に作れる」形を選ぶ

### テーマ4: 無料で出す部分 / 有料にする部分の線引き
- 「無料 = 問題提起・共感・手法の概要」
- 「有料 = 実装方法・テンプレ・チェックリスト・具体的な手順」
- 無料で出しすぎない。有料で出しすぎない。
- 読者が「無料読んだ。次は有料が欲しい」と思う線を引く

## 出力フォーマット（必ずこの形式で出力すること）

# 商品化会議 — {DATE}（第{WEEK_NUM}週）

## テーマ1: 今週伸びたテーマ
- 最も反応が多かったテーマ:
- 共通パターン（なぜ伸びたか）:
- 数値的根拠（あれば）:

## テーマ2: 金になる悩み
- 特定した悩み:
- 根拠（なぜこれが金になるか）:
- 商品タネバンクとの対応:

## テーマ3: 商品の形
- 価格帯: ¥（　）
- 形式: （有料note / PDF / テンプレ / チェックリスト / プロンプト集）
- 今週中に作れるか: （はい / いいえ、いつなら作れるか）

## テーマ4: 無料/有料の線引き
- 無料で出す部分:
- 有料にする部分:
- 線引きの根拠:

---

## 今週の商品企画

**タイトル**: 「（具体的なタイトル）」
**価格**: ¥（　）
**形式**: （　）
**内容概要**:
- （コンテンツ1）
- （コンテンツ2）
- （コンテンツ3）
- （コンテンツ4、あれば）

**無料との差別化**:
（有料にする理由・無料と何が違うか1文）

**制作見積もり**:
- 素材: （今週の発信ログ / 会議ログ / 新規制作）
- 時間: （　時間）
- 公開目標: （　週間後）

**成功判定**:
（何が起きれば成功か1文）
"""


def collect_week_data() -> dict:
    today = date.today()
    data: dict = {"week_start": str(today - timedelta(days=today.weekday()))}

    # 今週の投稿分析（「伸びた理由」抽出）
    analyses = []
    for i in range(7):
        ds = str(today - timedelta(days=i))
        f = SODA_DIR / "logs" / "daily" / f"{ds}_post_analysis.md"
        if f.exists():
            content = f.read_text()
            start = content.find("## 結論")
            if start != -1:
                analyses.append(f"【{ds}】\n{content[start:start+200].strip()}")
    data["analyses"] = analyses

    # 今週の商品タネ
    seeds_entries = []
    seeds_file = SODA_DIR / "products" / "product_seeds.md"
    if seeds_file.exists():
        content = seeds_file.read_text()
        for i in range(7):
            ds = str(today - timedelta(days=i))
            marker = f"# 商品メモ — {ds}"
            if marker in content:
                start = content.find(marker)
                end = content.find("\n# 商品メモ — ", start + 1)
                chunk = content[start:end].strip() if end != -1 else content[start:].strip()
                seeds_entries.append(chunk)
    data["seeds"] = seeds_entries

    # 今週のアイデアバンク（有料商品候補のみ抽出）
    idea_entries = []
    idea_file = SODA_DIR / "products" / "idea_bank.md"
    if idea_file.exists():
        content = idea_file.read_text()
        for i in range(7):
            ds = str(today - timedelta(days=i))
            marker = f"# アイデア資産 — {ds}"
            if marker in content:
                start = content.find(marker)
                end = content.find("\n# アイデア資産 — ", start + 1)
                chunk = content[start:end].strip() if end != -1 else content[start:].strip()
                # 有料商品候補セクションだけ抜粋
                prod_start = chunk.find("### 有料商品候補")
                idea_entries.append(chunk[prod_start:prod_start + 400] if prod_start != -1 else chunk[:300])
    data["ideas"] = idea_entries

    # 直近の週次レポート（weekly_analysisの結果を引き継ぐ）
    weekly_files = sorted((SODA_DIR / "logs" / "weekly").glob("*.md"))
    if weekly_files:
        weekly = weekly_files[-1].read_text()
        # 6項目レビューセクションだけ抽出
        start = weekly.find("## 今週の6項目レビュー")
        data["weekly_report"] = weekly[start:start + 2000].strip() if start != -1 else weekly[:1500]
    else:
        data["weekly_report"] = ""

    # 既存のバックログ（重複防止）
    backlog_tail = ""
    if PRODUCT_BACKLOG.exists():
        backlog_tail = PRODUCT_BACKLOG.read_text()[-1500:]
    data["backlog_tail"] = backlog_tail

    # 週番号
    data["week_num"] = today.isocalendar()[1]

    return data


def build_prompt(data: dict, today: date) -> str:
    ds = str(today)
    lines = [
        MEETING_PROMPT.replace("{DATE}", ds).replace("{WEEK_NUM}", str(data["week_num"])),
        "",
        "---",
        "## 今週のデータ（会議の入力情報）",
        f"集計期間: {data['week_start']} 〜 {ds}",
        "",
    ]

    # 直近の週次レポート
    if data.get("weekly_report"):
        lines.append("### 直近の週次レポート（6項目レビュー）— 商品化判断の最優先参照")
        lines.append(data["weekly_report"])
        lines.append("")

    # 投稿分析
    if data["analyses"]:
        lines.append("### 今週の投稿分析（伸びた/弱かった理由）")
        lines.extend(data["analyses"])
        lines.append("")
    else:
        lines.append("### 今週の投稿分析\n（データなし）\n")

    # 商品タネ
    if data["seeds"]:
        lines.append("### 今週の商品タネバンク")
        lines.extend(data["seeds"])
        lines.append("")
    else:
        lines.append("### 今週の商品タネバンク\n（データなし — アイデアバンクから推定する）\n")

    # アイデアバンクの有料商品候補
    if data["ideas"]:
        lines.append("### 今週のアイデアバンク（有料商品候補）")
        lines.extend(data["ideas"])
        lines.append("")

    # 既存バックログ（重複防止）
    if data["backlog_tail"]:
        lines.append("### 既存の商品バックログ（直近）※重複しないこと")
        lines.append(data["backlog_tail"])
        lines.append("")

    lines.append(
        f"上記データを基に会議を進め、出力フォーマットに従って "
        f"products/product_plans/{today}_product_plan.md に Write toolで保存せよ。\n"
        f"次に、以下の形式で products/product_backlog.md の末尾に追記せよ（上書き不可）。\n"
        f"product_backlog.md が存在しない場合は '# SODA 商品バックログ\\n\\n' で始めて作成する。\n"
        f"追記形式: '## {ds} | [タイトル] | ¥[価格] | [形式] | 公開目標: [N週間後]'\n"
        f"保存完了後は「商品化会議完了: [企画タイトル]」と出力して終了すること。"
    )

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="SODA商品化会議スクリプト")
    parser.add_argument("--dry-run", action="store_true", help="プロンプトだけ表示")
    args = parser.parse_args()

    today = date.today()
    data = collect_week_data()
    prompt = build_prompt(data, today)

    if args.dry_run:
        print(f"[週次データ] 投稿分析: {len(data['analyses'])}件 / 商品タネ: {len(data['seeds'])}件 / アイデア: {len(data['ideas'])}件")
        print()
        print("=== PROMPT ===")
        print(prompt)
        return

    log_file = SODA_DIR / "logs" / "cron" / f"{today}_product_meeting.log"
    print(f"[{today}] 商品化会議を開始...")

    result = subprocess.run(
        [
            CLAUDE, "-p",
            "--dangerously-skip-permissions",
            "--allowedTools", "Read,Write,Glob",
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
                "商品化会議", f"run_product_meeting.py が失敗しました（exit: {result.returncode}）",
            ],
            cwd=str(SODA_DIR),
        )
        print(f"エラー: {result.stderr[-300:]}")
        return

    plan_file = SODA_DIR / "products" / "product_plans" / f"{today}_product_plan.md"
    if plan_file.exists():
        print(f"商品企画保存完了: {plan_file}")
        # タイトルと価格だけコンソール表示
        content = plan_file.read_text()
        start = content.find("## 今週の商品企画")
        if start != -1:
            print(content[start:start + 300])
    else:
        print("警告: 商品企画ファイルが作成されませんでした")
        print(result.stdout[-500:])


if __name__ == "__main__":
    main()
