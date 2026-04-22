#!/usr/bin/env python3
"""
投稿分析スクリプト（毎朝8:45）
前日のX投稿を5観点で分析し、「伸びた理由」「弱かった理由」を記録する。
使い方:
  python3 scripts/run_post_analysis.py          # 実行
  python3 scripts/run_post_analysis.py --dry-run  # プロンプトだけ表示
"""

import argparse
import json
import subprocess
from datetime import date, timedelta
from pathlib import Path

from soda_utils import SODA_DIR, CLAUDE, PYTHON, run_claude, notify_error

ANALYSIS_PROMPT = """\
あなたはXアカウント「SODA」の投稿データアナリストです。
以下の前日データを分析し、指定の出力フォーマットで結果を書き出してください。
分析は事実・数値に基づき、感想ではなく原因の仮説を書くこと。

## 分析の5観点

1. **インプレッション** — 各投稿のIMP数。朝・昼・夜でどれが多いか。
2. **保存されやすい型** — ブックマーク数が多い投稿の文体・構造の特徴。
3. **返信がつくテーマ** — リプライ数が多い投稿のトピックと書き方の特徴。
4. **クリックされた導線** — 夜投稿（note URL付き）のIMP・エンゲージメントから推定。
5. **noteに飛んだ投稿の特徴** — 夜投稿の内容・CTAの書き方と反応の関係。

## 出力フォーマット（必ずこの形式で出力すること）

# SODA 投稿分析 — {DATE}

## 数値サマリー
| 投稿 | IMP | いいね | RT | 返信 | ブックマーク |
|------|-----|--------|-----|------|------------|
| 朝（1本目） | - | - | - | - | - |
| 昼（2本目） | - | - | - | - | - |
| 夜（3本目） | - | - | - | - | - |

## 5観点の分析
1. **インプレッション**: （観察と仮説を1〜2文）
2. **保存されやすい型**: （観察と仮説を1〜2文。データがなければ「不明」と書く）
3. **返信がつくテーマ**: （観察と仮説を1〜2文）
4. **クリックされた導線**: （夜投稿のデータから推定。1〜2文）
5. **noteに飛んだ投稿の特徴**: （CTA・内容から推定。1〜2文）

## 結論
**昨日伸びた理由**: （1行で。なければ「データ不足」と書く）
**昨日弱かった理由**: （1行で。なければ「データ不足」と書く）

## 明日への仮説
（今日の投稿で試すべき1点。1〜2文）
"""


def refresh_metrics() -> bool:
    """前日のメトリクスを最新値に更新する（失敗しても続行）"""
    try:
        result = subprocess.run(
            [PYTHON, str(SODA_DIR / "scripts" / "fetch_metrics.py"), "--days", "2"],
            cwd=str(SODA_DIR),
            capture_output=True,
            text=True,
            timeout=60,
        )
        print(result.stdout.strip())
        return result.returncode == 0
    except Exception as e:
        print(f"メトリクス再取得スキップ（{e}）")
        return False


def collect_yesterday_data() -> dict:
    yesterday = date.today() - timedelta(days=1)
    ds = str(yesterday)
    data: dict = {"date": ds}

    # Xメトリクス
    metrics_file = SODA_DIR / "logs" / "metrics" / f"{ds}.json"
    data["metrics"] = json.loads(metrics_file.read_text()) if metrics_file.exists() else []

    # X投稿本文
    x_files = sorted((SODA_DIR / "content" / "x_posts").glob(f"{ds}_*.md"))
    data["x_content"] = x_files[0].read_text() if x_files else ""

    # note URL（夜投稿にURLが付いたか確認用）
    note_url_file = SODA_DIR / "logs" / "daily" / f"{ds}_note_url.txt"
    data["note_url"] = note_url_file.read_text().strip() if note_url_file.exists() else ""

    return data


def build_prompt(data: dict, today: date) -> str:
    ds = data["date"]
    lines = [
        ANALYSIS_PROMPT.replace("{DATE}", str(today)),
        "",
        "---",
        f"## 前日データ（{ds}）",
        "",
    ]

    # メトリクス詳細
    if data["metrics"]:
        lines.append("### Xメトリクス（数値）")
        for m in sorted(data["metrics"], key=lambda x: x.get("post_number", 0)):
            met = m.get("metrics") or {}
            label = ["朝", "昼", "夜"][m.get("post_number", 1) - 1] if m.get("post_number") else "?"
            lines.append(
                f"- {label}（{m.get('post_number')}本目）: "
                f"IMP:{met.get('impressions', '?')} "
                f"いいね:{met.get('likes', '?')} "
                f"RT:{met.get('retweets', '?')} "
                f"返信:{met.get('replies', '?')} "
                f"ブックマーク:{met.get('bookmarks', '?')}"
            )
            lines.append(f"  本文: {m.get('text', '')[:80]}")
    else:
        lines.append("### Xメトリクス\n（データなし — 定性分析のみ実施）")

    lines.append("")

    # 投稿本文
    if data["x_content"]:
        lines.append("### X投稿本文")
        lines.append(data["x_content"])
    else:
        lines.append("### X投稿本文\n（なし）")

    # note URL
    if data["note_url"]:
        lines.append(f"\n### 夜投稿に付いたnote URL\n{data['note_url']}")
    else:
        lines.append("\n### 夜投稿のnote URL\n（なし）")

    lines.append("")
    lines.append(
        f"上記データを分析し、出力フォーマットに従って結果を "
        f"logs/daily/{today}_post_analysis.md に Write toolで保存せよ。"
        f"ファイルを保存したら、「分析完了」と出力して終了すること。"
    )

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="SODA投稿分析スクリプト")
    parser.add_argument("--dry-run", action="store_true", help="プロンプトだけ表示")
    parser.add_argument("--no-refresh", action="store_true", help="メトリクス再取得をスキップ")
    args = parser.parse_args()

    today = date.today()

    if not args.dry_run and not args.no_refresh:
        print("メトリクスを再取得中...")
        refresh_metrics()

    data = collect_yesterday_data()
    prompt = build_prompt(data, today)

    if args.dry_run:
        print("=== PROMPT ===")
        print(prompt)
        return

    log_file = SODA_DIR / "logs" / "cron" / f"{today}_post_analysis.log"
    print(f"[{today}] 投稿分析を開始...")

    result = run_claude(prompt, tools=["Read", "Write", "Glob"])

    log_file.write_text(result.stdout + result.stderr)

    if result.returncode != 0:
        notify_error("投稿分析", f"run_post_analysis.py が失敗しました（exit: {result.returncode}）")
        print(f"エラー: {result.stderr[-300:]}")
        return

    analysis_file = SODA_DIR / "logs" / "daily" / f"{today}_post_analysis.md"
    if analysis_file.exists():
        print(f"分析保存完了: {analysis_file}")
        # 結論部分だけコンソールに表示
        content = analysis_file.read_text()
        start = content.find("## 結論")
        if start != -1:
            print(content[start:start + 200])
    else:
        print("警告: 分析ファイルが作成されませんでした")
        print(result.stdout[-500:])


if __name__ == "__main__":
    main()
