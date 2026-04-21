#!/usr/bin/env python3
"""
CTA改善スクリプト（毎日18:00）
今日のCTAを一つ決定し、夜投稿（20:00）のCTAを書き直して反映する。
使い方:
  python3 scripts/run_cta_review.py          # 実行
  python3 scripts/run_cta_review.py --dry-run  # プロンプトだけ表示
"""

import os
import argparse
import subprocess
from pathlib import Path
from datetime import date

SODA_DIR = Path(__file__).parent.parent
CLAUDE = os.path.expanduser("~/.local/bin/claude")
PYTHON = "/Users/rikubon50/.pyenv/shims/python3"

CTA_PROMPT = """\
あなたはSODAのCTA設計担当です。
今日のコンテンツを確認し、「今日のCTA」を一つ決定して夜投稿（3本目）を改善してください。

## CTA候補（この3つだけ）

1. **無料テンプレを受け取ってほしい** — Googleフォームへ誘導。メアドと引き換えにAIチーム設計テンプレを配布。
   フォームURL: docs/funnel_status.md の「フォームURL」欄を参照。
2. **noteを読んでほしい** — 夜投稿にnote URLが付く。本文でnoteに誘導する。
3. **メール登録してほしい** — メールリスト登録ページへ誘導する。（Googleフォームと重複する場合は使わない）

## CTA選定ルール

- **1投稿につきCTAは1つだけ**（複数のCTAは全部弱くなる）
- 今日の記事テーマと自然につながるCTAを選ぶ
- フォームURLが設定済みなら「無料テンプレ」を優先する（リード取得が最優先）
- フォームURLが未設定なら「noteを読んでほしい」をデフォルトにする
- docs/funnel_status.md を確認して設定状況を判断すること

## 夜投稿（3本目）の制約

- **117字以内**（note URLが自動追加されるため）
- 単体で意味が通ること（昼・朝の内容を前提にしない）
- 締めに「↓」「→」「note」などで自然にnoteへ誘導する

## 実行手順

1. 今日のX投稿ファイルを Read toolで読み込む
2. 今日のnote記事を Read toolで読み込む（content/note/ 内の今日のファイル）
3. products/idea_bank.md を Read toolで読み込む（テンプレ・商品の準備状況確認）
4. 以下の出力フォーマットで logs/daily/{DATE}_cta.md を Write toolで作成する
5. 夜投稿（3本目）のCTAが改善できる場合、今日のX投稿ファイルの3本目部分を Edit toolで書き直す
   （書き直す場合は117字以内を厳守。他の投稿（1本目・2本目）は触らない）

## 出力フォーマット

# CTA記録 — {DATE}

## 今日のCTA決定
**選択**: （noteを読んでほしい / メール登録してほしい / 無料テンプレを受け取ってほしい）
**理由**: （なぜこのCTAを選んだか1文）
**状態**: （準備済み / 準備中）

## 現在の夜投稿（3本目）評価
**現行テキスト**: （現在の投稿本文）
**CTA強度**: （強い / 普通 / 弱い）
**問題点**: （あれば1文）

## 改善後の夜投稿（3本目）
**改善テキスト**: （改善した投稿本文。117字以内）
**文字数確認**: （改善テキストの文字数を必ず数えて記載。例: 112字）
**変更点**: （何をどう変えたか1文）
**ファイル更新**: （更新した / 更新不要）

## 文字数チェック（必須）
改善テキストが117字を超えていた場合、117字以内に収まるまで削ってから保存すること。
URLは含まない（note URLは自動追加されるため）。

## 明日のCTA仮説
（今日の結果を踏まえ、明日はどのCTAが適切か1文）
"""


def find_today_x_file() -> Path | None:
    today = date.today()
    ds = str(today)
    files = sorted((SODA_DIR / "content" / "x_posts").glob(f"{ds}_*.md"))
    return files[0] if files else None


def build_prompt(today: date) -> str:
    ds = str(today)
    x_file = find_today_x_file()

    lines = [
        CTA_PROMPT.replace("{DATE}", ds),
        "",
        "---",
        f"## 本日（{ds}）のファイル情報",
        "",
    ]

    if x_file:
        lines.append(f"- X投稿ファイル: `{x_file.relative_to(SODA_DIR)}`")
    else:
        lines.append("- X投稿ファイル: （今日のファイルが見つかりません）")

    # note記事の存在確認
    note_files = sorted((SODA_DIR / "content" / "note").glob(f"{ds}_*.md"))
    if note_files:
        lines.append(f"- note記事: `{note_files[0].relative_to(SODA_DIR)}`")
    else:
        lines.append("- note記事: （なし）")

    # idea_bank の存在確認
    idea_bank = SODA_DIR / "products" / "idea_bank.md"
    if idea_bank.exists():
        lines.append("- アイデアバンク: `products/idea_bank.md`（テンプレ・商品準備状況の確認に使う）")
    else:
        lines.append("- アイデアバンク: （なし — noteを読んでほしいをデフォルトで選択）")

    lines.append("")
    lines.append(
        "上記の実行手順に従って処理し、CTA記録を保存し、"
        "必要なら夜投稿（3本目）を Edit toolで書き直すこと。"
        "処理完了後は「CTA設定完了: [選んだCTA]」と出力して終了すること。"
    )

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="SODA CTA改善スクリプト")
    parser.add_argument("--dry-run", action="store_true", help="プロンプトだけ表示")
    args = parser.parse_args()

    today = date.today()
    prompt = build_prompt(today)

    if args.dry_run:
        print("=== PROMPT ===")
        print(prompt)
        return

    log_file = SODA_DIR / "logs" / "cron" / f"{today}_cta.log"
    print(f"[{today}] CTA改善を開始...")

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
                "CTA改善", f"run_cta_review.py が失敗しました（exit: {result.returncode}）",
            ],
            cwd=str(SODA_DIR),
        )
        print(f"エラー: {result.stderr[-300:]}")
        return

    cta_file = SODA_DIR / "logs" / "daily" / f"{today}_cta.md"
    if cta_file.exists():
        print(f"CTA記録保存完了: {cta_file}")
        # 決定したCTAをコンソール表示
        content = cta_file.read_text()
        start = content.find("## 今日のCTA決定")
        end = content.find("## 現在の夜投稿")
        if start != -1 and end != -1:
            print(content[start:end].strip())
    else:
        print("警告: CTA記録ファイルが作成されませんでした")
        print(result.stdout[-500:])


if __name__ == "__main__":
    main()
