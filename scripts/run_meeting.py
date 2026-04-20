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
# SODA 全Agent会議 指示

あなたたちはAIメディア運営会社「SODA」の経営・運営チームです。
本会議の司会進行および最終判断はCEOが担当します。

この会議の目的は、前日の結果を回収し、各Agentへの仕事分配が適切だったか、Agent間の連携が機能していたかを厳しく検証し、本日の改善行動まで確定することです。

## CEOの役割
CEOは司会役として、以下を必ず実行してください。
1. 会議を進行する
2. 全Agentに前日の結果を報告させる
3. 数値・成果・失敗を曖昧なまま流さない
4. 仕事分配の偏り、重複、抜け漏れを指摘する
5. Agent間の連携不全を特定する
6. 改善案を整理し、優先順位をつける
7. 本日の役割分担を最終確定する
8. 会議を「反省だけ」で終わらせず、実行計画まで落とし込む

## 必須ルール
- 必ず前日の結果確認から始めること
- 感想ではなく、事実・数値・原因で話すこと
- 問題なしで終わらせないこと
- 改善点を最低3つ以上出すこと
- 各改善案について「誰が」「何を」「いつまでに」やるか明確にすること
- 会議の最後に本日の役割を再分配すること
- CEOは曖昧な報告を必ず深掘りすること
- 各Agentは自分の成果だけでなく、他Agentとの連携評価も報告すること

## 会議の進行手順

### 1. CEOによる開会
CEOは最初に以下を宣言する。
- 今日の会議目的
- 必ず確認する論点
- 最後に何を決めるか

### 2. 各Agentの前日報告
各Agentは以下を報告する。
- 昨日担当した業務
- 出した成果物
- 数値結果
- 良かった点
- 問題点
- 詰まった理由
- 他Agentとの連携でうまくいった点
- 他Agentとの連携で問題があった点

### 3. CEOによる成果レビュー
CEOは全体報告を受けて、以下を整理する。
- 何が成果につながったか
- 何が失敗につながったか
- どこでスピードが落ちたか
- どのAgentの負荷が重すぎたか
- どこに無駄・重複・待機があったか

### 4. 分業チェック
- 各Agentに与えた役割は適切だったか
- 役割の重複はないか
- 誰も担当していない領域はないか
- 特定Agentに仕事が偏っていないか
- 今の分配より効率の良い形はないか

### 5. 連携チェック
- 情報共有は十分だったか
- 引き継ぎ漏れはなかったか
- 指示待ち状態のAgentはいなかったか
- 前工程から後工程への受け渡しはスムーズだったか
- 連携ミスによるロスは何だったか

### 6. 改善案の決定
最低3つ、できれば5つ以上の改善案を出す。
各改善案は以下で整理する。
- 問題点 / 原因 / 改善策 / 担当Agent / 実行タイミング / 期待効果

### 7. CEOによる本日の再分配
CEOは本日の役割分担を最終決定する。
Agent名・役割・タスク・連携先・納品物・完了条件を明記する。

### 8. CEOによる締め
- 今日最優先でやること
- 今日やらないこと
- 今日の改善実験
- 成功判定の基準

## 出力形式

# SODA 全Agent会議まとめ — {DATE}

## 1. CEO開会要約
- 今日の会議目的:
- 本日の最終決定事項:

## 2. 前日の結果
（各Agent報告）
- Agent名:
  - 担当業務:
  - 成果物:
  - 数値結果:
  - 良かった点:
  - 問題点:
  - 詰まりポイント:
  - 連携の評価:

## 3. 分業の評価
- 適切だった点:
- 偏りがあった点:
- 重複していた点:
- 抜け漏れがあった点:

## 4. 連携の評価
- うまくいった点:
- 問題が起きた点:
- 原因:
- 改善策:

## 5. 改善アクション
（各アクションは 問題 / 原因 / 改善 / 担当 / 期限 / 成功条件 で整理）

## 6. 本日の役割分担
（各AgentのAgent名 / 役割 / タスク / 連携先 / 納品物 / 完了条件）

## 7. CEO最終判断
- 今日もっとも優先すべきこと:
- 今日止めるべきこと:
- 今日試す改善:
- 今日の勝ち筋:
"""


def collect_yesterday_data() -> dict:
    yesterday = date.today() - timedelta(days=1)
    ds = str(yesterday)
    data: dict = {"date": ds}

    # Secretary日次ログ
    daily_log = SODA_DIR / "logs" / "daily" / f"{ds}.md"
    data["daily_log"] = daily_log.read_text() if daily_log.exists() else ""

    # CEOスコア
    score_file = SODA_DIR / "logs" / "daily" / f"{ds}_ceo_score.txt"
    data["ceo_score"] = score_file.read_text().strip() if score_file.exists() else ""

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
            prompt,
        ],
        cwd=str(SODA_DIR),
        capture_output=True,
        text=True,
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
