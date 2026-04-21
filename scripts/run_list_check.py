#!/usr/bin/env python3
"""
リスト導線確認スクリプト（毎日21:15）
4項目の導線設置状況を確認し、未設定なら具体的なアクションを出力する。
使い方:
  python3 scripts/run_list_check.py          # 実行
  python3 scripts/run_list_check.py --dry-run  # プロンプトだけ表示
"""

import re
import argparse
from pathlib import Path
from datetime import date

SODA_DIR = Path(__file__).parent.parent

FUNNEL_STATUS = SODA_DIR / "docs" / "funnel_status.md"

CHECK_PROMPT = """\
あなたはSODAのリスト導線管理担当です。
以下のデータを確認し、4項目の導線設置状況をチェックして結果を保存してください。

## チェック項目と判定基準

### 1. Xプロフィールに導線あるか
- docs/funnel_status.md の「状態」欄が ✅ 設定済み かどうかを確認する
- 未設定なら具体的なアクション文を出す

### 2. X固定ポストに導線あるか
- docs/funnel_status.md の「状態」欄が ✅ 設定済み かどうかを確認する
- 未設定なら具体的なアクション文を出す

### 3. note末尾に登録導線あるか
- 今日のnote記事ファイルの末尾200字を読み、以下のキーワードがあるか確認する
  検出ワード: 「メール」「登録」「受け取」「プレゼント」「フォーム」「LINE」「無料」＋URL（http）
- どちらかが揃っていれば ✅、なければ ❌

### 4. 無料プレゼントの受け皿あるか
- docs/funnel_status.md の「状態」欄が ✅ 設定済み かどうかを確認する
- products/product_seeds.md に商品タネが3件以上あれば「準備中」扱い

## ステータス記号
- ✅ 設定済み — 導線が機能している
- ⚠️ 準備中 — タネはあるが未公開・未設置
- ❌ 未設定 — 何も存在しない

## 出力フォーマット（必ずこの形式で出力すること）

# リスト導線チェック — {DATE}

| 項目 | 状態 | 詳細 |
|------|------|------|
| Xプロフィール導線 | （✅/⚠️/❌） | （1文） |
| X固定ポスト導線 | （✅/⚠️/❌） | （1文） |
| note末尾登録導線 | （✅/⚠️/❌） | （1文） |
| 無料プレゼント受け皿 | （✅/⚠️/❌） | （1文） |

## 総合評価
**整備率**: X / 4 項目
**フェーズ**: （リスト構築前 / リスト構築中 / リスト活用可能）

## 今日やること（最優先1つだけ）
**タスク**: （未設定のうち最も優先すべき1項目の具体的なアクション）
**所要時間**: （5分 / 15分 / 1時間など）
**完了条件**: （何ができたら完了か1文）

## メモ
（今日の商品タネや反応データとリスト導線の関係で気づいたこと。なければ省略）
"""


def check_note_cta(today: date) -> tuple[str, str]:
    """note末尾200字を読んでCTA検出。(status, detail) を返す"""
    ds = str(today)
    note_files = sorted((SODA_DIR / "content" / "note").glob(f"{ds}_*.md"))
    if not note_files:
        return "❌", "今日のnote記事なし"

    tail = note_files[0].read_text()[-200:]
    cta_words = ["メール", "登録", "受け取", "プレゼント", "フォーム", "LINE"]
    has_keyword = any(w in tail for w in cta_words)
    has_url = bool(re.search(r"https?://", tail))

    if has_keyword and has_url:
        return "✅", "登録キーワード＋URLを検出"
    elif has_keyword or has_url:
        return "⚠️", f"{'キーワードのみ検出（URL未設置）' if has_keyword else 'URLのみ検出（誘導文なし）'}"
    else:
        return "❌", "登録導線なし（末尾200字に該当なし）"


def count_product_seeds() -> int:
    seeds = SODA_DIR / "products" / "product_seeds.md"
    if not seeds.exists():
        return 0
    return seeds.read_text().count("# 商品メモ —")


def build_prompt(today: date) -> str:
    ds = str(today)
    note_cta_status, note_cta_detail = check_note_cta(today)
    seed_count = count_product_seeds()

    lines = [
        CHECK_PROMPT.replace("{DATE}", ds),
        "",
        "---",
        f"## 事前チェック結果（スクリプトによる自動確認）",
        "",
        f"- note末尾登録導線: {note_cta_status}（{note_cta_detail}）",
        f"- 商品タネ数（product_seeds.md）: {seed_count} 件",
        "",
        "## 読み込むファイル",
        "- docs/funnel_status.md（プロフィール・固定ポスト・受け皿の状態確認）",
        f"- products/product_seeds.md（タネ蓄積数・内容確認）",
        "",
        "## 実行手順",
        "1. docs/funnel_status.md を Read toolで読む",
        "2. 上記の事前チェック結果と合わせて4項目を評価する",
        f"3. 出力フォーマットに従って logs/daily/{ds}_list_check.md を Write toolで保存する",
        "4. docs/funnel_status.md の「更新ログ」末尾に今日の確認日時を1行追記する（Edit tool）",
        "5. 保存完了後は「導線チェック完了: X/4項目」と出力して終了すること",
    ]

    return "\n".join(lines)


ACTIONS = {
    "Xプロフィール導線":   "docs/x_profile_copy.md を参照してXプロフィールにフォームURLを設置する（5分）",
    "X固定ポスト導線":     "固定ポスト用テキストを投稿してプロフィールに固定する（5分）",
    "note末尾登録導線":    "今日のnote記事末尾にCTAテンプレ（agents/writer.md参照）を追加する（5分）",
    "無料プレゼント受け皿": "docs/google_form_setup.md を参照してフォームを作成する（30分）",
}


def check_funnel_status(item_keyword: str) -> str:
    """funnel_status.md から該当項目のステータスを読み取る"""
    if not FUNNEL_STATUS.exists():
        return "❌"
    text = FUNNEL_STATUS.read_text()
    idx = text.find(item_keyword)
    if idx == -1:
        return "❌"
    snippet = text[idx:idx + 200]
    if "✅" in snippet:
        return "✅"
    if "🔧" in snippet:
        return "⚠️"
    return "❌"


def determine_phase(count: int) -> str:
    if count <= 1:
        return "リスト構築前"
    if count <= 3:
        return "リスト構築中"
    return "リスト活用可能"


def main():
    parser = argparse.ArgumentParser(description="SODAリスト導線確認スクリプト")
    parser.add_argument("--dry-run", action="store_true", help="結果を表示するだけ")
    args = parser.parse_args()

    today = date.today()
    ds = str(today)

    # 4項目を判定
    items = {
        "Xプロフィール導線":   check_funnel_status("Xプロフィールに導線"),
        "X固定ポスト導線":     check_funnel_status("X固定ポストに導線"),
        "note末尾登録導線":    check_note_cta(today)[0],
        "無料プレゼント受け皿": check_funnel_status("無料プレゼントの受け皿"),
    }
    note_detail = check_note_cta(today)[1]
    seed_count = count_product_seeds()
    ok_count = sum(1 for v in items.values() if v == "✅")
    phase = determine_phase(ok_count)

    # 最優先アクション（❌ → ⚠️ → ✅ の順で最初の未完了）
    priority_item = next((k for k, v in items.items() if v == "❌"), None) or \
                    next((k for k, v in items.items() if v == "⚠️"), None)
    priority_action = ACTIONS.get(priority_item, "すべて設定済みです") if priority_item else "すべて設定済みです"

    # レポート生成
    rows = "\n".join(
        f"| {k} | {v} | {'登録キーワード＋URL確認' if k == 'note末尾登録導線' else v} |"
        for k, v in items.items()
    )
    # note行だけ詳細を入れる
    rows = "\n".join(
        f"| {k} | {v} | {note_detail if k == 'note末尾登録導線' else ('設定済み' if v == '✅' else ('準備中' if v == '⚠️' else '未設定'))} |"
        for k, v in items.items()
    )

    report = f"""# リスト導線チェック — {ds}

| 項目 | 状態 | 詳細 |
|------|------|------|
{rows}

## 総合評価
**整備率**: {ok_count} / 4 項目
**フェーズ**: {phase}
**商品タネ数**: {seed_count} 件

## 今日やること（最優先1つだけ）
**タスク**: {priority_action}
"""

    if args.dry_run:
        print(report)
        return

    log_file = SODA_DIR / "logs" / "cron" / f"{ds}_list_check.log"
    check_file = SODA_DIR / "logs" / "daily" / f"{ds}_list_check.md"

    check_file.write_text(report)
    log_file.write_text(f"[{today}] 導線チェック完了: {ok_count}/4項目\n{report}")

    # funnel_status.md の更新ログに追記
    if FUNNEL_STATUS.exists():
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y-%m-%d")
        FUNNEL_STATUS.write_text(
            FUNNEL_STATUS.read_text() + f"| {timestamp} | 自動チェック: {ok_count}/4項目 |\n"
        )

    print(f"導線チェック完了: {ok_count}/4項目")
    print(report)


if __name__ == "__main__":
    main()
