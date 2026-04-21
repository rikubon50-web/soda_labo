#!/usr/bin/env python3
"""
リード獲得導線チェック（毎週金曜19:00）
4つの導線を戦略的にレビューし、来週の具体的なアクションを決める。
使い方:
  python3 scripts/run_lead_funnel_check.py          # 実行
  python3 scripts/run_lead_funnel_check.py --dry-run  # プロンプトだけ表示
"""

import os
import argparse
import subprocess
from pathlib import Path
from datetime import date, timedelta

SODA_DIR = Path(__file__).parent.parent
CLAUDE = os.path.expanduser("~/.local/bin/claude")
PYTHON = "/Users/rikubon50/.pyenv/shims/python3"

FUNNEL_PROMPT = """\
あなたはSODAのリード獲得戦略担当です。
今週の発信と導線の状況を確認し、「認知が次につながっているか」を戦略レビューしてください。

## このチェックの目的

無料コンテンツ（X・note）を見た人が、連絡先を残す動線があるかを確認する。
以下の4つのどれかが機能していないと、フォロワーが増えても収益にならない。

1. **メール登録** — メルマガ・ニュースレター登録フォーム
2. **LINE登録** — LINEオープンチャットやLINE公式アカウント
3. **無料PDF配布** — PDFを受け取る代わりに連絡先を登録してもらう
4. **テンプレ配布** — テンプレをDLする代わりに連絡先を登録してもらう

## レビューの視点

**存在チェック**（あるかないか）ではなく：
- **機能チェック**（動線が成立しているか）
- **魅力チェック**（受け取る側のメリットが明確か）
- **摩擦チェック**（登録が面倒でないか）
- **連結チェック**（X・noteからその導線に自然につながっているか）

## 判断基準

| 状態 | 記号 | 意味 |
|------|------|------|
| 機能している | ✅ | 動線が成立し、魅力があり、発信と連結している |
| 設置済みだが弱い | ⚠️ | 存在するが魅力・連結のどちらかが欠けている |
| 未設置 | ❌ | 何もない |
| 準備中 | 🔧 | 商品タネ/バックログにあるが未公開 |

## 実行手順

1. docs/funnel_status.md を Read toolで読む
2. products/product_seeds.md を Read toolで読む（リードマグネット化できるものを探す）
3. products/product_backlog.md を Read toolで読む（近日公開できるものを確認）
4. 今週の daily list_check ログ（logs/daily/*_list_check.md）をGlob toolで確認する
5. 出力フォーマットに従って結果を保存する

## 出力フォーマット（必ずこの形式で出力すること）

# リード獲得導線チェック — {DATE}（金曜）

## 4つの導線の現状

### 1. メール登録
- **状態**: （✅/⚠️/❌/🔧）
- **登録先**: （URLまたは「なし」）
- **魅力**: （何を提供しているか、またはなし）
- **X・noteとの連結**: （ある/ない/弱い）
- **問題点**: （あれば1文）

### 2. LINE登録
- **状態**: （✅/⚠️/❌/🔧）
- **登録先**: （URLまたは「なし」）
- **魅力**: （何を提供しているか、またはなし）
- **X・noteとの連結**: （ある/ない/弱い）
- **問題点**: （あれば1文）

### 3. 無料PDF配布
- **状態**: （✅/⚠️/❌/🔧）
- **配布先**: （URLまたは「なし」）
- **内容**: （何を配布しているか、またはなし）
- **X・noteとの連結**: （ある/ない/弱い）
- **問題点**: （あれば1文）

### 4. テンプレ配布
- **状態**: （✅/⚠️/❌/🔧）
- **配布先**: （URLまたは「なし」）
- **内容**: （何を配布しているか、またはなし）
- **X・noteとの連結**: （ある/ない/弱い）
- **問題点**: （あれば1文）

---

## 今週の認知→リスト転換の評価

**転換できた可能性がある接点**:
（今週の発信でリードにつながり得たポイント。なければ「なし」）

**転換できなかった理由**:
（導線がなかった/弱かった/CTAが機能していなかった など、最も大きな理由1つ）

**今週のリード獲得数の推定**:
（0人 / 数人 / 不明 — 根拠も書く）

---

## 来週やること（1つだけ）

**最優先タスク**:
（4つの中で最も優先すべき1つを具体的なアクションで書く）

**作業内容**:
- （ステップ1）
- （ステップ2）
- （ステップ3、あれば）

**所要時間**: （　分/時間）
**完了条件**: （何ができたら完了か1文）
**期待効果**: （これが完成するとどう変わるか1文）

---

## リードマグネット候補（商品タネ・バックログから）
（今週の商品タネ・バックログで「無料で配れる形」に最も近いもの1〜2件）
- 「（タイトル）」→ （何の形で配れるか）
"""


def collect_week_data() -> dict:
    today = date.today()
    data: dict = {"date": str(today)}

    # 今週の日次導線チェックログ
    list_checks = []
    for i in range(7):
        ds = str(today - timedelta(days=i))
        f = SODA_DIR / "logs" / "daily" / f"{ds}_list_check.md"
        if f.exists():
            content = f.read_text()
            # サマリー行のみ抜粋
            start = content.find("## 総合評価")
            end = content.find("## 今日やること")
            if start != -1 and end != -1:
                list_checks.append(f"【{ds}】{content[start:end].strip()}")
    data["list_checks"] = list_checks

    return data


def build_prompt(data: dict) -> str:
    ds = data["date"]
    lines = [
        FUNNEL_PROMPT.replace("{DATE}", ds),
        "",
        "---",
        "## 今週の日次チェック履歴（参考）",
        "",
    ]

    if data["list_checks"]:
        lines.extend(data["list_checks"])
    else:
        lines.append("（今週の日次チェックログなし — funnel_status.md から現状を判断する）")

    lines.append("")
    lines.append(
        f"出力フォーマットに従って結果を "
        f"logs/weekly/{ds}_lead_funnel.md に Write toolで保存せよ。\n"
        f"次に docs/funnel_status.md を Read toolで読み込み、"
        f"今日の確認結果を「更新ログ」に追記（Edit tool）せよ。\n"
        f"保存完了後は「導線チェック完了: [整備率X/4]」と出力して終了すること。"
    )

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="SODAリード獲得導線チェック（金曜）")
    parser.add_argument("--dry-run", action="store_true", help="プロンプトだけ表示")
    args = parser.parse_args()

    today = date.today()
    data = collect_week_data()
    prompt = build_prompt(data)

    if args.dry_run:
        print(f"[今週の日次チェック履歴] {len(data['list_checks'])}件")
        print()
        print("=== PROMPT ===")
        print(prompt)
        return

    # logs/weeklyディレクトリ確保
    (SODA_DIR / "logs" / "weekly").mkdir(parents=True, exist_ok=True)

    log_file = SODA_DIR / "logs" / "cron" / f"{today}_lead_funnel.log"
    print(f"[{today}] リード獲得導線チェックを開始...")

    result = subprocess.run(
        [
            CLAUDE, "-p",
            "--dangerously-skip-permissions",
            "--allowedTools", "Read,Write,Edit,Glob",
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
                "リード獲得導線チェック", f"run_lead_funnel_check.py が失敗しました（exit: {result.returncode}）",
            ],
            cwd=str(SODA_DIR),
        )
        print(f"エラー: {result.stderr[-300:]}")
        return

    funnel_file = SODA_DIR / "logs" / "weekly" / f"{today}_lead_funnel.md"
    if funnel_file.exists():
        print(f"導線チェック保存完了: {funnel_file}")
        content = funnel_file.read_text()
        start = content.find("## 来週やること")
        if start != -1:
            print(content[start:start + 400])
    else:
        print("警告: 導線チェックファイルが作成されませんでした")
        print(result.stdout[-500:])


if __name__ == "__main__":
    main()
