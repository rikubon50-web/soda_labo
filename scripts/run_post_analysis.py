#!/usr/bin/env python3
"""
投稿分析スクリプト（毎朝8:45）
前日公開したnote記事を4観点で分析し、「伸びた理由」「弱かった理由」を記録する。
メトリクスは前夜22:30の note_metrics.py が保存した logs/metrics/ を読む（この工程では取得しない）。
使い方:
  python3 scripts/run_post_analysis.py          # 実行
  python3 scripts/run_post_analysis.py --dry-run  # プロンプトだけ表示
"""

import argparse
import json
from datetime import date, timedelta
from pathlib import Path

from soda_utils import SODA_DIR, CLAUDE, run_claude, notify_error

ANALYSIS_PROMPT = """\
あなたはnoteメディア「SODA」の記事アナリストです。
以下のデータを分析し、指定の出力フォーマットで結果を書き出してください。
分析は事実・数値に基づき、感想ではなく原因の仮説を書くこと。

## 分析の4観点

1. **読まれ方** — 昨日公開した記事のビュー数。直近7日の他記事と比べて多いか少ないか。
2. **スキ率** — スキ数÷ビュー数。高い記事・低い記事の内容の違い。
3. **伸びるテーマ** — 直近7日でビューが多い記事に共通するテーマ・切り口。
4. **フックの効き** — タイトルと冒頭300字が読者を掴めているか（内容とビューの関係から推定）。

メトリクスが未取得の日は、記事の内容（テーマ・構成・フック・視点接続）の定性評価に切り替えること。

## 出力フォーマット（必ずこの形式で出力すること）

# SODA 記事分析 — {DATE}

## 数値サマリー
| 記事 | ビュー | スキ | コメント | スキ率 |
|------|--------|------|----------|--------|
| 昨日の記事 | - | - | - | - |
| 直近7日平均 | - | - | - | - |

## 4観点の分析
1. **読まれ方**: （観察と仮説を1〜2文）
2. **スキ率**: （観察と仮説を1〜2文。データがなければ「不明」と書く）
3. **伸びるテーマ**: （観察と仮説を1〜2文）
4. **フックの効き**: （観察と仮説を1〜2文）

## 結論
**昨日伸びた理由**: （1行で。なければ「データ不足」と書く）
**昨日弱かった理由**: （1行で。なければ「データ不足」と書く）

## 明日への仮説
（明日の記事で試すべき1点。1〜2文）
"""


def collect_yesterday_data() -> dict:
    yesterday = date.today() - timedelta(days=1)
    ds = str(yesterday)
    data: dict = {"date": ds}

    # noteメトリクス（当日取得分＝最新値。過去7日分も推移用に集める）
    metrics = []
    for i in range(8):
        d = date.today() - timedelta(days=i)
        f = SODA_DIR / "logs" / "metrics" / f"{d}.json"
        if f.exists():
            try:
                j = json.loads(f.read_text())
                if isinstance(j, dict) and j.get("source") == "note":
                    metrics.append(j)
            except (json.JSONDecodeError, KeyError):
                pass
    data["metrics"] = metrics

    # 昨日のnote記事本文
    note_files = sorted((SODA_DIR / "content" / "note").glob(f"{ds}_*.md"))
    data["note_content"] = note_files[0].read_text() if note_files else ""

    # note公開URL
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

    # 昨日の記事を特定するキー/タイトル（メトリクス一覧からの照合用）
    yesterday_key = ""
    if data.get("note_url"):
        yesterday_key = data["note_url"].rstrip("/").rsplit("/", 1)[-1]
    yesterday_title = ""
    for line in (data.get("note_content") or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            yesterday_title = stripped[2:].strip()
            break

    def _is_yesterday_article(a: dict) -> bool:
        if yesterday_key and a.get("key") == yesterday_key:
            return True
        title = a.get("title", "")
        if yesterday_title and title and (
            title.startswith(yesterday_title) or yesterday_title.startswith(title)
        ):
            return True
        return False

    # メトリクス詳細（直近8日分のnoteメトリクス推移。プロンプト肥大化を避けるため
    # 各日ビュー上位20件に絞り、昨日の記事が上位20件外なら個別に追記する）
    if data["metrics"]:
        lines.append(
            "### noteメトリクス（直近8日分の推移、日付降順、各日ビュー上位20件+昨日の記事）"
        )
        for m in sorted(data["metrics"], key=lambda x: x.get("date", ""), reverse=True):
            articles = m.get("articles") or []
            sorted_articles = sorted(articles, key=lambda x: x.get("views", 0), reverse=True)
            top = sorted_articles[:20]
            lines.append(f"- {m.get('date')}（{len(articles)}記事中、ビュー上位20件+昨日の記事）")
            for a in top:
                lines.append(
                    f"  - ビュー:{a.get('views', '?')} "
                    f"スキ:{a.get('likes', '?')} "
                    f"コメント:{a.get('comments', '?')} "
                    f"— {a.get('title', '')}"
                )
            if (yesterday_key or yesterday_title) and not any(
                _is_yesterday_article(a) for a in top
            ):
                match = next((a for a in articles if _is_yesterday_article(a)), None)
                if match:
                    lines.append(
                        f"  - [昨日の記事] ビュー:{match.get('views', '?')} "
                        f"スキ:{match.get('likes', '?')} "
                        f"コメント:{match.get('comments', '?')} "
                        f"— {match.get('title', '')}"
                    )
    else:
        lines.append("### noteメトリクス\n（データなし — 定性分析のみ実施）")

    lines.append("")

    # 記事本文
    if data["note_content"]:
        lines.append("### 昨日公開したnote記事")
        lines.append(data["note_content"])
    else:
        lines.append("### 昨日公開したnote記事\n（なし）")

    # note URL
    if data["note_url"]:
        lines.append(f"\n### 昨日のnote公開URL\n{data['note_url']}")
    else:
        lines.append("\n### 昨日のnote公開URL\n（なし）")

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
    args = parser.parse_args()

    today = date.today()

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
