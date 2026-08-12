#!/usr/bin/env python3
"""
週次分析スクリプト（Opus使用）
使い方:
  python3 scripts/weekly_analysis.py        # 今週分を分析
  python3 scripts/weekly_analysis.py --dry-run  # プロンプトだけ表示
"""

import argparse
import json
from datetime import date, timedelta

from soda_utils import SODA_DIR, run_claude, notify_error


def collect_follower_log(limit: int = 8) -> list:
    """follower_log.jsonl の直近N行を収集（ファイル欠如・空・壊れた行は安全にスキップ）"""
    log_file = SODA_DIR / "logs" / "ops" / "follower_log.jsonl"
    if not log_file.exists():
        return []

    entries = []
    try:
        for line in log_file.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                j = json.loads(line)
                if isinstance(j, dict) and "date" in j and "followers" in j:
                    entries.append(j)
            except json.JSONDecodeError:
                continue
    except OSError:
        return []

    return entries[-limit:]


def collect_week_data(days: int = 7) -> dict:
    """過去N日分のコンテンツとメトリクスを収集"""
    data = {"metrics": [], "note_files": [], "meeting_files": [], "analysis_files": []}
    today = date.today()

    for i in range(days):
        target = today - timedelta(days=i)
        ds = str(target)

        # noteメトリクス
        mf = SODA_DIR / "logs" / "metrics" / f"{ds}.json"
        if mf.exists():
            try:
                j = json.loads(mf.read_text())
                if isinstance(j, dict) and j.get("source") == "note":
                    data["metrics"].append(j)
            except (json.JSONDecodeError, KeyError):
                pass

        # noteファイル
        for f in sorted((SODA_DIR / "content" / "note").glob(f"{ds}_*.md")):
            data["note_files"].append({"date": ds, "path": str(f), "content": f.read_text()})

        # 全Agent会議ログ
        mf = SODA_DIR / "logs" / "meeting" / f"{ds}_meeting.md"
        if mf.exists():
            data["meeting_files"].append({"date": ds, "content": mf.read_text()})

        # 日次投稿分析ログ
        af = SODA_DIR / "logs" / "daily" / f"{ds}_post_analysis.md"
        if af.exists():
            data["analysis_files"].append({"date": ds, "content": af.read_text()})

    # 商品バックログ（全件）
    backlog = SODA_DIR / "products" / "product_backlog.md"
    data["product_backlog"] = backlog.read_text() if backlog.exists() else ""

    # フォロワー推移（直近8行）
    data["followers"] = collect_follower_log()

    return data


def build_prompt(data: dict, days: int = 7) -> str:
    today = date.today()
    week_start = today - timedelta(days=6)

    sections = [
        f"agents/analyst.md を読み、Analystとして以下のデータを分析し、週次レポートを出力する。",
        f"対象期間：{week_start} 〜 {today}",
        "",
    ]

    if data["metrics"]:
        sections.append("## noteメトリクスデータ（日付降順、各日ビュー上位20件）")
        for m in sorted(data["metrics"], key=lambda x: x.get("date", ""), reverse=True):
            articles = m.get("articles") or []
            top = sorted(articles, key=lambda a: a.get("views", 0), reverse=True)[:20]
            sections.append(f"- {m.get('date')}（{len(articles)}記事中、ビュー上位20件）")
            for a in top:
                sections.append(
                    f"  - ビュー:{a.get('views', '?')} "
                    f"スキ:{a.get('likes', '?')} "
                    f"コメント:{a.get('comments', '?')} "
                    f"— {a.get('title', '')}"
                )
    else:
        sections.append("## noteメトリクスデータ\n（今週はメトリクス未取得。記事内容から定性分析する）")

    sections.append("")

    if data.get("followers"):
        sections.append("### フォロワー推移（直近8行）")
        for f in data["followers"]:
            sections.append(f"- {f.get('date')}: {f.get('followers')}人")
    else:
        sections.append("### フォロワー推移\n（follower_log.jsonl が未取得または空のためスキップ）")

    sections.append("")

    if data["note_files"]:
        sections.append("## 今週のnote記事")
        for f in data["note_files"]:
            title_line = next((l for l in f["content"].splitlines() if l.startswith("# ")), "無題")
            sections.append(f"- [{f['date']}] {title_line.lstrip('# ')}")
    else:
        sections.append("## 今週のnote記事\n（なし）")

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

    # 商品バックログ
    if data.get("product_backlog"):
        sections.append("## 商品バックログ（全件）")
        sections.append(data["product_backlog"])
        sections.append("")

    sections.append("")
    sections.append(
        "あなたはSODAの週次レビュー担当（Analyst兼CEO）です。"
        "上記データと、必要に応じてRead/Glob/Grep toolで参照する追加ファイルから週次レビューを行い、"
        "結果を保存してください。分析観点はagents/analyst.mdの分析ルール（数値根拠・7日推移比較・データ不足の明記）に従うこと。\n\n"
        f"## 出力1: 週次数字レビュー（logs/weekly/{today}.md に保存）\n"
        "- 冒頭に必ず「今週のフォロワー純増: +N（X人→Y人）」を書く（北極星KPI）\n"
        "- 記事別ビュー・スキ、土日記事vs平日記事の比較、商品化トリガー判定"
        "（フォロワー50以上 or 実録記事週300ビュー以上で「★商品化トリガー到達」）。"
        "日曜実録記事は logs/daily/{日付}_magazine.txt の中身が"
        "「SODA運営実録 — AI全自動メディアの数字と中身」であるかで識別できる\n"
        "- 導線チェック: 今週公開した各記事がマガジンに入っているか・フォローCTAがあるか"
        "（logs/daily/*_magazine.txt とcontent/note/の末尾で確認）\n\n"
        "## 出力2: 翌週方針（docs/weekly_direction.md に上書き保存）\n"
        "- 来週のテーマ方向1〜3個（今週数字の学びから。CEOが毎朝の即応ゲート判定・土日テーマ選定で参照する）\n"
        "- 今週の「出す/出さない」判断の振り返り"
        "（logs/daily/*_no_publish.txt をGlob/Readで確認したメモ日リストと公開記事の反応を突き合わせ、ゲート基準の調整提案）\n"
        "- WebSearchで note.com/contests と noteのお題企画を確認し、"
        "来週相乗りできるものがあれば記載（なければ「該当なし」）\n\n"
        "## 出力3: 資産ファイルの更新\n"
        "- audience/winning_topics.md: 今週の記事で**実測100ビュー以上**のものだけを勝ちパターンとして"
        "「## 暫定候補」セクションにEdit toolで追記する（100未満は絶対に「勝ち」と記録しない。"
        "過去の数字インフレの再発防止）。同じテーマが既に3回以上記載されていれば"
        "「## 確定勝ちパターン」に移動して太字にする。追記形式: "
        f"'- [{today}] [テーマ名] — [なぜ伸びたか仮説1文]（実測Nビュー）'\n"
        "- audience/personas.md: 実測データがターゲット仮説（27〜35歳の発信・副業・AI活用層）を"
        "支持/反証するかの検証メモを1〜3行追記"
    )

    return "\n".join(sections)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    data = collect_week_data(args.days)
    prompt = build_prompt(data, args.days)

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

    result = run_claude(
        prompt,
        tools=["Read", "Write", "Edit", "Glob", "Grep", "WebSearch"],
        model="claude-opus-4-7",
    )

    log_file.write_text(result.stdout + result.stderr)

    if result.returncode == 0:
        weekly_file = SODA_DIR / "logs" / "weekly" / f"{today}.md"
        if weekly_file.exists():
            print(f"週次レポート保存完了: {weekly_file}")
        else:
            msg = "週次レポートファイルが作成されませんでした"
            print(f"警告: {msg}")
            notify_error("週次分析", msg)
    else:
        msg = result.stderr[-300:]
        print(f"エラー: {msg}")
        notify_error("週次分析", msg)


if __name__ == "__main__":
    main()
