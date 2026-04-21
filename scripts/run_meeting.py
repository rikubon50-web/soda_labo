#!/usr/bin/env python3
"""
SODA 全Agent会議スクリプト
毎朝7:30に自動実行。前日の結果を基に全Agent会議を進行し、ログに保存する。
使い方:
  python3 scripts/run_meeting.py          # 本日の会議を実行
  python3 scripts/run_meeting.py --dry-run  # プロンプトだけ表示
"""

import os
import json
import argparse
import subprocess
from pathlib import Path
from datetime import date, timedelta

SODA_DIR = Path(__file__).parent.parent
CLAUDE = os.path.expanduser("~/.local/bin/claude")

MEETING_FORMAT = """
# 会議の目的

今日のコンテンツ戦略において、最も成果につながるテーマと改善アクションを決定する。
前日のデータと実績を根拠にし、抽象論で終わらない。

# 参加Agent

- CEO
- Planner
- Writer
- Editor
- Secretary
- Analyst

# 共通ルール

- 目的から外れる雑談は禁止
- 全員が長文で話しすぎない
- 抽象論より具体案を優先
- 事実と意見を分ける
- 最終的にCEOが必ず1つに決める
- 「全部よいので全部採用」は禁止
- 昨日と同じ結論を出す場合は、その理由を明示する
- 反対意見がある場合は必ず1回はぶつける
- 会議の価値は、議論の長さではなく意思決定の質で測る

# Agent定義

## CEO
役割: 会議の焦点を保つ / 採否を判断する / 最終的な優先順位を決定する
禁止: 曖昧な結論 / 全案採用 / 議論を引き延ばすこと

## Planner
役割: 切り口の違う案を5本出す / タイトル案や構成の種を作る
禁止: 実現性ばかり気にして案数を減らすこと / 分析だけで終わること
必須: 5案のうち1本は必ずニュース解説案にすること。ニュース解説案には「取り上げるニュースの具体的なタイトルまたはトピック」を明記する。「ニュースが見つからない」は理由にならない
出力形式: 5案は必ず以下の型を1本ずつ割り当てる。各案に「今出す理由（または早い/遅い理由）」を1行必ず添える
  - 王道案（伸びそうな鉄板テーマ）
  - 逆張り案（読者の思い込みを裏切る切り口）
  - 感情訴求案（共感・不安・悔しさに刺さる）
  - 実用訴求案（今日から使えるノウハウ・手順）
  - ニュース解説案（直近のAI・ビジネスニュースを噛み砕く。取り上げるニュース名を必ず明記）

## Writer
役割: 読者が反応しやすい形に具体化する / フック・本文方向・伝わる表現に落とす
禁止: 会議を再び抽象化すること / 読者視点のない自己満表現
X夜投稿のCTAルール（必須）:
  - フォロー誘導は原則禁止
  - note遷移 / Google Form（無料テンプレ受け取り）/ 無料PDF のいずれかに誘導すること
  - 直前の会議ログの改善アクション表を必ず参照し、指示があればそれをデフォルトとして採用する

## Editor
役割: 弱い案を見抜く / 強い案をより鋭く短くする / トーンを統一する
禁止: ゼロから企画を作り直すこと / ふわっと褒めて流すこと
出力形式: 各案への指摘を以下の形式で整理する
  - 判定ラベル（以下の3つのいずれか）：「そのまま通せる」「修正すれば通せる」「今日は見送る」
  - 致命傷（これがあると今日出せない理由。なければ「なし」と明記）
  - 補助的な懸念（直せば通る問題）
  - 通すならこう直す（具体的な修正案）

## Analyst
役割: 数字やログから勝ち筋を抽出する / 根拠に基づいて示唆を出す
禁止: 根拠のない主観 / データにない断定 / 品質・成果を数値なしで断定すること（例:「品質は良好」は不可。「トーン整合性は高い」「構成は整っている」「ただし成果は未検証」の形で書く）
出力形式: 各示唆を以下の2段で書く。仮説は因果の飛躍に注意し、中間ステップを省略しない
  - 確認できた事実（ログ・数値・ファイルから直接読み取れること）
  - そこからの仮説（事実から推論できること。断定せず可能性として書く）

## Secretary
役割: 会議を整理する / 決定事項・却下理由・次アクションを明文化する
禁止: 自分の意見で会議を支配すること / 結論を曖昧にまとめること
冒頭整理の出力形式（3区分必須）:
  - 取得済みデータ（確認できた事実）
  - 未取得データ（何が欠けているか）
  - 今日の判断可能範囲（欠損を踏まえてどこまで判断できるか）
本日のタスクの出力形式: 番号付き順序リストで書く（実行順に並べる）

# 会議の進行

1. Secretaryが前日データ（日次ログ・CEOスコア・Xメトリクス）を3行以内で整理する
2. Analystが事実ベースで重要示唆を3つ出す
3. Plannerが候補案を5つ出す
4. CEOが一次選別して2案まで絞る（前日会議で使用時期が決まっている案は再評価せず除外する）
   ※ content/note/ の直近ファイルを確認し、Day Nシリーズが3日連続していた場合はDayシリーズを選択肢から除外する
5. Writerがその2案を具体化する
6. Editorが弱点を指摘して改善する
7. CEOが最終決定する
8. Secretaryが議事録形式で結論を出力する

# 評価基準

1. 読者の反応が期待できるか
2. 過去データとの整合性があるか
3. すぐ制作に移れるか
4. 他案より明確に強いか
5. 将来の商品化・導線につながるか

# 出力形式

必ず以下の形式で出力すること。ファイルは logs/meeting/{DATE}_meeting.md に保存する。

## 会議要約

- 今日の論点:
- 主な示唆:（構成・トーンの評価と、定量評価の可否を分けて書く）
- 対立した意見:
- CEO最終判断:
- 採用理由:
- 却下理由:
- 今日の実行アクション:
- 明日以降に持ち越す論点:

## Agent発言ログ

[Secretary]
...

[Analyst]
...

[Planner]
...

[CEO]
...

[Writer]
...

[Editor]
...

[CEO Final]
採用：
今回の判断基準（優先した順に列挙）：（例「①シリーズ継続性 ②今日の制作可能性 ③新規流入への寄与」）
採用理由：
今回捨てたもの：（例「連続実験ログを捨てて新規流入を優先した」）
Writerへの指示：

## 改善アクション

優先度を必ず明示すること（最優先 / 次点 / その次 / 保留準備）。
形式：優先度 | 問題 | 原因 | 改善策 | 担当Agent | 期限 | 確認方法（完了判定の基準）
"""


def collect_yesterday_data() -> dict:
    yesterday = date.today() - timedelta(days=1)
    ds = str(yesterday)
    data: dict = {"date": ds}

    # Secretary日次ログ
    daily_log = SODA_DIR / "logs" / "daily" / f"{ds}.md"
    data["daily_log"] = daily_log.read_text() if daily_log.exists() else ""

    # CEOスコア（1行目がスコア数字、2行目以降が判断理由）
    score_file = SODA_DIR / "logs" / "daily" / f"{ds}_ceo_score.txt"
    if score_file.exists():
        score_text = score_file.read_text().strip()
        lines_score = score_text.splitlines()
        data["ceo_score"] = lines_score[0].strip()
        data["ceo_score_reason"] = "\n".join(lines_score[1:]).strip() if len(lines_score) > 1 else ""
    else:
        data["ceo_score"] = ""
        data["ceo_score_reason"] = ""

    # note公開URL
    note_url_file = SODA_DIR / "logs" / "daily" / f"{ds}_note_url.txt"
    data["note_url"] = note_url_file.read_text().strip() if note_url_file.exists() else ""

    # Xメトリクス
    metrics_file = SODA_DIR / "logs" / "metrics" / f"{ds}.json"
    data["metrics"] = json.loads(metrics_file.read_text()) if metrics_file.exists() else []

    # note記事
    note_files = sorted((SODA_DIR / "content" / "note").glob(f"{ds}_*.md"))
    data["note_content"] = note_files[0].read_text()[:600] if note_files else ""

    # X投稿
    x_files = sorted((SODA_DIR / "content" / "x_posts").glob(f"{ds}_*.md"))
    data["x_content"] = x_files[0].read_text() if x_files else ""

    # cronパイプラインログ（直近4000字）
    run_log = SODA_DIR / "logs" / "cron" / f"{ds}_run.log"
    data["run_log"] = run_log.read_text()[-4000:] if run_log.exists() else ""

    # 直前の会議ログ（改善アクションセクションのみ抽出）
    meeting_files = sorted((SODA_DIR / "logs" / "meeting").glob("*_meeting.md"))
    if meeting_files:
        full = meeting_files[-1].read_text()
        start = full.find("## 改善アクション")
        data["last_meeting_actions"] = full[start:] if start != -1 else full[-1500:]
    else:
        data["last_meeting_actions"] = ""

    # 直近3日のアイデアログ（Planner用）
    idea_texts = []
    for i in range(1, 4):
        idea_ds = str(date.today() - timedelta(days=i))
        idea_file = SODA_DIR / "logs" / "ideas" / f"{idea_ds}_ideas.md"
        if idea_file.exists():
            idea_texts.append(f"--- {idea_ds} ---\n{idea_file.read_text()[:800]}")
    data["recent_ideas"] = "\n\n".join(idea_texts)

    # 読者データ（personas / winning_topics）
    personas_file = SODA_DIR / "audience" / "personas.md"
    data["personas"] = personas_file.read_text()[:600] if personas_file.exists() else ""
    winning_file = SODA_DIR / "audience" / "winning_topics.md"
    data["winning_topics"] = winning_file.read_text()[:400] if winning_file.exists() else ""
    objections_file = SODA_DIR / "audience" / "objections.md"
    data["objections"] = objections_file.read_text()[:400] if objections_file.exists() else ""

    return data


def build_prompt(data: dict, today: date) -> str:
    ds = data["date"]
    lines = [
        f"今日は{today}（JST）。以下の前日（{ds}）データを踏まえてSODA全Agent会議を実行せよ。",
        "",
        "## 実行手順",
        "1. agents/ceo.md、agents/secretary.md、agents/planner.md、"
        "agents/writer.md、agents/editor.md を Read toolで読み込む",
        "2. 下記「前日データ」と「会議フォーマット」に従い、全Agent会議を進行する",
        f"3. 会議まとめを logs/meeting/{today}_meeting.md に Write toolで保存する",
        "",
        "## 前日データ",
        "",
    ]

    # CEOスコア
    score = data.get("ceo_score") or "未取得"
    lines.append(f"### CEOスコア（公開判断）\n{score} / 5")
    if data.get("ceo_score_reason"):
        lines.append(f"判断理由: {data['ceo_score_reason']}")

    # note URL
    if data.get("note_url"):
        lines.append(f"\n### note公開URL\n{data['note_url']}")

    # Xメトリクス
    lines.append("\n### Xメトリクス")
    if data["metrics"]:
        for m in data["metrics"]:
            met = m.get("metrics") or {}
            lines.append(
                f"- {m['post_number']}本目: "
                f"いいね:{met.get('likes', '?')} "
                f"RT:{met.get('retweets', '?')} "
                f"IMP:{met.get('impressions', '?')} "
                f"| {m['text'][:40]}..."
            )
    else:
        lines.append("（未取得 — 投稿内容から定性評価すること）")

    # Secretary日次ログ
    lines.append("\n### Secretary日次ログ")
    lines.append(data["daily_log"] if data["daily_log"] else "（なし）")

    # note記事抜粋
    lines.append("\n### note記事（先頭600字）")
    lines.append(data["note_content"] if data["note_content"] else "（なし）")

    # X投稿
    lines.append("\n### X投稿内容")
    lines.append(data["x_content"] if data["x_content"] else "（なし）")

    # パイプラインログ
    if data["run_log"]:
        lines.append("\n### 自動実行ログ（直近4000字）")
        lines.append(f"```\n{data['run_log']}\n```")

    # 直前の会議の改善アクション
    if data.get("last_meeting_actions"):
        lines.append("\n### 前回会議の改善アクション（Writerは夜投稿CTA設計時に必ず確認すること）")
        lines.append(data["last_meeting_actions"])

    # 直近3日のアイデアログ（Planner用）
    if data.get("recent_ideas"):
        lines.append("\n### 直近3日のアイデア資産（Plannerは企画案作成時に必ず参照すること）")
        lines.append(data["recent_ideas"])

    # 読者データ
    if data.get("personas"):
        lines.append("\n### 読者ペルソナ（PlannerとWriterは必ず参照すること）")
        lines.append(data["personas"])
    if data.get("winning_topics"):
        lines.append("\n### 勝ちトピック（反応が取れた確定テーマ）")
        lines.append(data["winning_topics"])
    if data.get("objections"):
        lines.append("\n### 読者の反論・離脱理由（Growth参照：CTA設計・導線設計に使う）")
        lines.append(data["objections"])

    lines.append("\n---")
    lines.append(MEETING_FORMAT.replace("{DATE}", str(today)))

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="SODA全Agent会議スクリプト")
    parser.add_argument("--dry-run", action="store_true", help="プロンプトだけ表示")
    args = parser.parse_args()

    today = date.today()
    data = collect_yesterday_data()
    prompt = build_prompt(data, today)

    if args.dry_run:
        print("=== PROMPT ===")
        print(prompt)
        return

    meeting_dir = SODA_DIR / "logs" / "meeting"
    meeting_dir.mkdir(parents=True, exist_ok=True)

    log_file = SODA_DIR / "logs" / "cron" / f"{today}_meeting.log"

    print(f"[{today}] SODA全Agent会議を開始...")

    result = subprocess.run(
        [
            CLAUDE, "-p",
            "--dangerously-skip-permissions",
            "--allowedTools", "Read,Write,Glob,Grep",
        ],
        input=prompt,
        cwd=str(SODA_DIR),
        capture_output=True,
        text=True,
        timeout=1800,
    )

    log_file.write_text(result.stdout + result.stderr)

    if result.returncode != 0:
        # エラー通知
        subprocess.run(
            [
                "python3", str(SODA_DIR / "scripts" / "notify_error.py"),
                "全Agent会議", f"run_meeting.py が失敗しました（exit: {result.returncode}）",
            ],
            cwd=str(SODA_DIR),
        )
        print(f"エラー: {result.stderr[-300:]}")
        return

    meeting_file = meeting_dir / f"{today}_meeting.md"
    if meeting_file.exists():
        print(f"会議まとめ保存完了: {meeting_file}")
    else:
        print("警告: 会議ファイルが作成されませんでした")
        print(result.stdout[-500:])


if __name__ == "__main__":
    main()
