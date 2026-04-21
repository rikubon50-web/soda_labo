#!/usr/bin/env python3
"""
アイデア資産化スクリプト（毎朝9:00）
前日の会議ログから学びを抽出し、X/note/有料商品の3素材に分解して蓄積する。
使い方:
  python3 scripts/run_idea_mining.py          # 実行
  python3 scripts/run_idea_mining.py --dry-run  # プロンプトだけ表示
"""

import os
import argparse
import subprocess
from pathlib import Path
from datetime import date, timedelta

SODA_DIR = Path(__file__).parent.parent
CLAUDE = os.path.expanduser("~/.local/bin/claude")
PYTHON = "/Users/rikubon50/.pyenv/shims/python3"

IDEA_BANK = SODA_DIR / "products" / "idea_bank.md"

MINING_PROMPT = """\
あなたはSODAのコンテンツストラテジストです。
以下の「前日データ」から学びを2〜3個抽出し、それぞれを3種類の素材に分解してください。

## 分解ルール

各学びを必ず以下の3素材に変換する：

1. **X単発ネタ** — 140字以内で成立するツイート案。断言・逆説・数字で始めると強い。
2. **note化候補** — 記事タイトル案と、書けるアングル（なぜ読まれるか1文で）。
3. **有料商品候補** — この学びが積み重なったときに何を売れるか。テンプレ・ツール・講座・PDF等。

## 素材化のコツ

- 「詰まった経験」「失敗」「ズレ」は最も強い素材
- 数字・具体的な手順・比較（変更前/後）があればそのまま使う
- 有料商品は「今すぐ売れる」ではなく「3〜6ヶ月後に売れる」視点で考える
- X案は投稿日が今日でなくていい。ストック案でよい

## 出力フォーマット（必ずこの形式で出力すること）

# アイデア資産 — {DATE}

## 抽出した学び一覧
1. （学び1：1文で）
2. （学び2：1文で）
3. （学び3：1文で、あれば）

---

## 学び1: （タイトル）

### X単発ネタ
（ツイート本文。140字以内）

### note化候補
- タイトル案: 「（タイトル）」
- アングル: （なぜ読まれるか1文）

### 有料商品候補
- 商品名: 「（商品名）」
- 形式: （テンプレ / PDF / 講座 / ツール など）
- 根拠: （なぜこれが売れるか1文）

---

## 学び2: （タイトル）

### X単発ネタ
（ツイート本文。140字以内）

### note化候補
- タイトル案: 「（タイトル）」
- アングル: （なぜ読まれるか1文）

### 有料商品候補
- 商品名: 「（商品名）」
- 形式: （テンプレ / PDF / 講座 / ツール など）
- 根拠: （なぜこれが売れるか1文）

---

（学び3があれば同様に）

## 今週の資産化メモ
（今日の3素材を踏まえ、シリーズ化・深掘りすべき方向を1〜2文で）
"""


def collect_yesterday_data() -> dict:
    yesterday = date.today() - timedelta(days=1)
    ds = str(yesterday)
    data: dict = {"date": ds}

    # 会議まとめ（最重要ソース）
    meeting_file = SODA_DIR / "logs" / "meeting" / f"{ds}_meeting.md"
    data["meeting"] = meeting_file.read_text() if meeting_file.exists() else ""

    # 投稿分析（補助）
    analysis_file = SODA_DIR / "logs" / "daily" / f"{ds}_post_analysis.md"
    data["analysis"] = analysis_file.read_text() if analysis_file.exists() else ""

    # Secretary日次ログ（補助）
    daily_log = SODA_DIR / "logs" / "daily" / f"{ds}.md"
    data["daily_log"] = daily_log.read_text() if daily_log.exists() else ""

    return data


def build_prompt(data: dict, today: date) -> str:
    ds = data["date"]
    lines = [
        MINING_PROMPT.replace("{DATE}", str(today)),
        "",
        "---",
        f"## 前日データ（{ds}）",
        "",
    ]

    # 会議まとめ（改善アクション〜CEO最終判断を重点的に使う）
    if data["meeting"]:
        content = data["meeting"]
        # 改善アクション以降を抜粋（ここが学びの宝庫）
        start = content.find("## 5. 改善アクション")
        excerpt = content[start:] if start != -1 else content
        lines.append("### 前日の全Agent会議まとめ（抜粋）")
        lines.append(excerpt[:3000])
    else:
        lines.append("### 前日の全Agent会議まとめ\n（なし — Secretary日次ログとnote記事から抽出する）")

    lines.append("")

    # 投稿分析の「明日への仮説」
    if data["analysis"]:
        content = data["analysis"]
        start = content.find("## 結論")
        if start != -1:
            lines.append("### 前日の投稿分析（結論・仮説）")
            lines.append(content[start:start + 400])

    # Secretary日次ログ（バックアップ）
    if data["daily_log"] and not data["meeting"]:
        lines.append("\n### Secretary日次ログ")
        lines.append(data["daily_log"][:1500])

    lines.append("")
    lines.append(
        f"上記データから学びを2〜3個抽出し、出力フォーマットに従って "
        f"logs/ideas/{today}_ideas.md に Write toolで保存せよ。"
        f"\n次に、同じ内容を products/idea_bank.md の末尾に追記せよ（上書きではなく追記）。"
        f"\nidea_bank.md が存在しない場合は '# SODAアイデア資産バンク\\n\\n' で始めて作成する。"
        f"\nファイル保存が完了したら「資産化完了」と出力して終了すること。"
    )

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="SODAアイデア資産化スクリプト")
    parser.add_argument("--dry-run", action="store_true", help="プロンプトだけ表示")
    args = parser.parse_args()

    today = date.today()
    data = collect_yesterday_data()
    prompt = build_prompt(data, today)

    if args.dry_run:
        print("=== PROMPT ===")
        print(prompt)
        return

    log_file = SODA_DIR / "logs" / "cron" / f"{today}_idea_mining.log"
    print(f"[{today}] アイデア資産化を開始...")

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
    )

    log_file.write_text(result.stdout + result.stderr)

    if result.returncode != 0:
        subprocess.run(
            [
                PYTHON, str(SODA_DIR / "scripts" / "notify_error.py"),
                "アイデア資産化", f"run_idea_mining.py が失敗しました（exit: {result.returncode}）",
            ],
            cwd=str(SODA_DIR),
        )
        print(f"エラー: {result.stderr[-300:]}")
        return

    ideas_file = SODA_DIR / "logs" / "ideas" / f"{today}_ideas.md"
    if ideas_file.exists():
        print(f"アイデア保存完了: {ideas_file}")
        # 抽出した学び一覧だけコンソール表示
        content = ideas_file.read_text()
        start = content.find("## 抽出した学び")
        end = content.find("---")
        if start != -1 and end != -1:
            print(content[start:end].strip())
    else:
        print("警告: アイデアファイルが作成されませんでした")
        print(result.stdout[-500:])


if __name__ == "__main__":
    main()
