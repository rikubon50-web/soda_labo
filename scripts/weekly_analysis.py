#!/usr/bin/env python3
"""
週次分析スクリプト（Opus使用）
使い方:
  python3 scripts/weekly_analysis.py        # 今週分を分析
  python3 scripts/weekly_analysis.py --dry-run  # プロンプトだけ表示
"""

import os
import json
import argparse
import subprocess
from pathlib import Path
from datetime import date, timedelta

SODA_DIR = Path(__file__).parent.parent
CLAUDE = os.path.expanduser("~/.local/bin/claude")


def collect_week_data(days: int = 7) -> dict:
    """過去N日分のコンテンツとメトリクスを収集"""
    data = {"metrics": [], "note_files": [], "x_files": [], "meeting_files": [], "analysis_files": []}
    today = date.today()

    for i in range(days):
        target = today - timedelta(days=i)
        ds = str(target)

        # メトリクス
        mf = SODA_DIR / "logs" / "metrics" / f"{ds}.json"
        if mf.exists():
            data["metrics"].extend(json.loads(mf.read_text()))

        # noteファイル
        for f in sorted((SODA_DIR / "content" / "note").glob(f"{ds}_*.md")):
            data["note_files"].append({"date": ds, "path": str(f), "content": f.read_text()})

        # X投稿ファイル
        for f in sorted((SODA_DIR / "content" / "x_posts").glob(f"{ds}_*.md")):
            data["x_files"].append({"date": ds, "path": str(f), "content": f.read_text()})

        # 全Agent会議ログ
        mf = SODA_DIR / "logs" / "meeting" / f"{ds}_meeting.md"
        if mf.exists():
            data["meeting_files"].append({"date": ds, "content": mf.read_text()})

        # 日次投稿分析ログ
        af = SODA_DIR / "logs" / "daily" / f"{ds}_post_analysis.md"
        if af.exists():
            data["analysis_files"].append({"date": ds, "content": af.read_text()})

    # 今週の金曜リード導線チェック
    data["lead_funnel"] = ""
    for i in range(days):
        ds = str(today - timedelta(days=i))
        lf = SODA_DIR / "logs" / "weekly" / f"{ds}_lead_funnel.md"
        if lf.exists():
            data["lead_funnel"] = lf.read_text()
            break

    # 商品バックログ（全件）
    backlog = SODA_DIR / "products" / "product_backlog.md"
    data["product_backlog"] = backlog.read_text() if backlog.exists() else ""

    return data


def build_prompt(data: dict) -> str:
    today = date.today()
    week_start = today - timedelta(days=6)

    sections = [
        f"agents/analyst.md を読み、Analystとして以下のデータを分析し、週次レポートを出力する。",
        f"対象期間：{week_start} 〜 {today}",
        "",
    ]

    if data["metrics"]:
        sections.append("## Xメトリクスデータ")
        for m in data["metrics"]:
            metrics = m.get("metrics") or {}
            sections.append(
                f"- [{m['posted_at'][:10]}] {m['theme']} {m['post_number']}本目 "
                f"| いいね:{metrics.get('likes','?')} "
                f"RT:{metrics.get('retweets','?')} "
                f"IMP:{metrics.get('impressions','?')} "
                f"| {m['text'][:40]}..."
            )
    else:
        sections.append("## Xメトリクスデータ\n（今週はメトリクス未取得。投稿内容から定性分析する）")

    sections.append("")

    if data["note_files"]:
        sections.append("## 今週のnote記事")
        for f in data["note_files"]:
            title_line = next((l for l in f["content"].splitlines() if l.startswith("# ")), "無題")
            sections.append(f"- [{f['date']}] {title_line.lstrip('# ')}")
    else:
        sections.append("## 今週のnote記事\n（なし）")

    sections.append("")

    if data["x_files"]:
        sections.append("## 今週のX投稿ファイル（抜粋）")
        for f in data["x_files"]:
            sections.append(f"### {f['date']} - {Path(f['path']).stem}")
            sections.append(f["content"][:300])
            sections.append("")

    if data["analysis_files"]:
        sections.append("## 今週の日次投稿分析（結論のみ）")
        for f in data["analysis_files"]:
            content = f["content"]
            start = content.find("## 結論")
            end = content.find("## 明日への仮説")
            if start != -1:
                excerpt = content[start:end].strip() if end != -1 else content[start:start + 200].strip()
            else:
                excerpt = content[:200]
            sections.append(f"### {f['date']}\n{excerpt}")
            sections.append("")
    else:
        sections.append("## 今週の日次投稿分析\n（分析ログなし）")

    sections.append("")

    if data["meeting_files"]:
        sections.append("## 今週の全Agent会議まとめ（改善アクション抜粋）")
        for f in data["meeting_files"]:
            # 改善アクションセクションだけ抜粋
            content = f["content"]
            start = content.find("## 改善アクション")
            if start != -1:
                excerpt = content[start:].strip()[:800]
            else:
                excerpt = content[:400]
            sections.append(f"### {f['date']}\n{excerpt}")
            sections.append("")
    else:
        sections.append("## 今週の全Agent会議まとめ\n（会議ログなし）")

    # 商品タネバンク（今週追加分）
    seeds = SODA_DIR / "products" / "product_seeds.md"
    if seeds.exists():
        seeds_content = seeds.read_text()
        week_seeds = []
        for i in range(days):
            ds = str(today - timedelta(days=i))
            marker = f"# 商品メモ — {ds}"
            if marker in seeds_content:
                start = seeds_content.find(marker)
                end = seeds_content.find("\n# 商品メモ — ", start + 1)
                chunk = seeds_content[start:end].strip() if end != -1 else seeds_content[start:].strip()
                week_seeds.append(chunk)
        if week_seeds:
            sections.append("## 今週の商品タネバンク")
            sections.extend(week_seeds)
            sections.append("")

    # アイデアバンク（今週追加分）
    idea_bank = SODA_DIR / "products" / "idea_bank.md"
    if idea_bank.exists():
        bank_content = idea_bank.read_text()
        # 今週追加分のエントリを週の日付で絞る
        week_excerpts = []
        for i in range(days):
            ds = str(today - timedelta(days=i))
            if ds in bank_content:
                start = bank_content.find(f"# アイデア資産 — {ds}")
                if start != -1:
                    end = bank_content.find("\n# アイデア資産 — ", start + 1)
                    chunk = bank_content[start:end].strip() if end != -1 else bank_content[start:].strip()
                    week_excerpts.append(chunk[:600])
        if week_excerpts:
            sections.append("## 今週のアイデア資産バンク（抜粋）")
            sections.extend(week_excerpts)
            sections.append("")

    # 金曜のリード導線チェック
    if data.get("lead_funnel"):
        sections.append("## 今週の金曜リード導線チェック")
        content = data["lead_funnel"]
        start = content.find("## 今週の認知→リスト転換の評価")
        excerpt = content[start:start + 800].strip() if start != -1 else content[:600]
        sections.append(excerpt)
        sections.append("")
    else:
        sections.append("## 今週の金曜リード導線チェック\n（なし）\n")

    # 商品バックログ
    if data.get("product_backlog"):
        sections.append("## 商品バックログ（全件）")
        sections.append(data["product_backlog"])
        sections.append("")

    sections.append("")
    sections.append(
        f"agents/analyst.md を Read toolで読み、Analystとして週次レポートを作成し "
        f"logs/weekly/{today}.md に Write toolで保存する。\n\n"
        f"レポート保存後、以下を必ず実行すること：\n"
        f"audience/winning_topics.md を Read toolで読み、"
        f"「### 1. 今週一番伸びたテーマ」で選んだテーマを以下の形式で「## 暫定候補」セクションに Edit toolで追記する。\n"
        f"追記形式: '- [{today}] [テーマ名] — [なぜ伸びたか仮説1文]'\n"
        f"同じテーマが既に3回以上記載されていれば「## 確定勝ちパターン」に移動して太字にする。\n\n"
        "週次レポートは通常の分析に加え、以下の6項目を必ず独立したセクションとして含めること。"
        "各項目は「検討する」「考える」で終わらせず、具体的な内容まで書くこと。\n\n"
        "---\n\n"
        "## 今週の6項目レビュー\n\n"
        "### 1. 今週一番伸びたテーマ\n"
        "（投稿分析・メトリクスから最も反応の多かったテーマを1つ。なぜ伸びたか仮説も1文で）\n\n"
        "### 2. 今週一番売れそうだった悩み\n"
        "（商品タネ・読者反応から「¥1,000を出す人がいる」と判断できる悩みを1つ。根拠も1文で）\n\n"
        "### 3. 来週無料で検証するテーマ\n"
        "（まだ反応が見えていないが試すべきテーマ。X or noteで来週出す具体的な案を1つ）\n\n"
        "### 4. 来週商品化するテーマ\n"
        "（商品バックログ・タネから来週制作に入るものを1つ。タイトル・形式・価格・制作時間を明記）\n\n"
        "### 5. メール登録導線の改善点\n"
        "（今週の導線チェックを踏まえ、来週1つだけ変えるアクションを具体的に。所要時間も添える）\n\n"
        "### 6. 継続収益に繋がる企画候補\n"
        "（週1・月1など定期的に届けられる形式の企画を1つ。"
        "メンバーシップ・ニュースレター・定期PDF等。今のコンテンツから派生できるものを選ぶ）"
    )

    return "\n".join(sections)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    data = collect_week_data(args.days)
    prompt = build_prompt(data)

    if args.dry_run:
        print("=== PROMPT ===")
        print(prompt)
        return

    # ログディレクトリを準備
    (SODA_DIR / "logs" / "weekly").mkdir(parents=True, exist_ok=True)

    today = date.today()
    log_file = SODA_DIR / "logs" / "cron" / f"{today}_weekly.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)

    print(f"Opus で週次分析を開始...")

    result = subprocess.run(
        [
            CLAUDE, "-p",
            "--dangerously-skip-permissions",
            "--model", "claude-opus-4-7",
            "--allowedTools", "Read,Write,Edit,Glob",
        ],
        input=prompt,
        cwd=str(SODA_DIR),
        capture_output=True,
        text=True,
        timeout=1800,
    )

    log_file.write_text(result.stdout + result.stderr)

    if result.returncode == 0:
        weekly_file = SODA_DIR / "logs" / "weekly" / f"{today}.md"
        if weekly_file.exists():
            print(f"週次レポート保存完了: {weekly_file}")
        else:
            msg = "週次レポートファイルが作成されませんでした"
            print(f"警告: {msg}")
            subprocess.run(
                ["python3", str(SODA_DIR / "scripts" / "notify_error.py"), "週次分析", msg],
                cwd=str(SODA_DIR),
            )
    else:
        msg = result.stderr[-300:]
        print(f"エラー: {msg}")
        subprocess.run(
            ["python3", str(SODA_DIR / "scripts" / "notify_error.py"), "週次分析", msg],
            cwd=str(SODA_DIR),
        )


if __name__ == "__main__":
    main()
