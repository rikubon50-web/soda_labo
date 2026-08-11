#!/usr/bin/env python3
"""
リスト導線確認スクリプト（毎日21:15）
note内で完結する導線4項目の設置状況を確認し、未設定なら具体的なアクションを出力する。
使い方:
  python3 scripts/run_list_check.py          # 実行
  python3 scripts/run_list_check.py --dry-run  # 結果を表示するだけ（保存・通知なし）
"""

import json
import argparse
from pathlib import Path
from datetime import date

SODA_DIR = Path(__file__).parent.parent

FUNNEL_STATUS = SODA_DIR / "docs" / "funnel_status.md"
FOLLOWER_LOG = SODA_DIR / "logs" / "ops" / "follower_log.jsonl"
MAGAZINES_CONFIG = SODA_DIR / "config" / "magazines.json"

def _magazine_names(magazines) -> set:
    """config/magazines.json の値から誌名の集合を作る（スキーマ不定に備えて防御的に解釈）"""
    names: set = set()
    if isinstance(magazines, dict):
        names.update(magazines.keys())
    elif isinstance(magazines, list):
        for m in magazines:
            if isinstance(m, str):
                names.add(m)
            elif isinstance(m, dict):
                name = m.get("name") or m.get("title") or m.get("誌名")
                if name:
                    names.add(name)
    return names


def check_magazine(today: date) -> tuple[str, str]:
    """今日の記事がマガジンに入っているか確認する。(status, detail) を返す"""
    ds = str(today)
    magazine_log = SODA_DIR / "logs" / "daily" / f"{ds}_magazine.txt"

    if not magazine_log.exists():
        return "⚠️", "未整備（logs/daily/{}_magazine.txt が未作成）".format(ds)
    if not MAGAZINES_CONFIG.exists():
        return "⚠️", "未整備（config/magazines.json が未作成）"

    try:
        magazines = json.loads(MAGAZINES_CONFIG.read_text())
    except json.JSONDecodeError:
        return "⚠️", "未整備（config/magazines.json の解析に失敗）"

    magazine_log_content = magazine_log.read_text().strip()
    magazine_name = magazine_log_content.splitlines()[0].strip() if magazine_log_content else ""
    if not magazine_name:
        return "❌", "logs/daily/{}_magazine.txt に誌名の記録なし".format(ds)

    names = _magazine_names(magazines)
    if magazine_name in names:
        return "✅", f"「{magazine_name}」に追加済み"
    return "❌", f"「{magazine_name}」はconfig/magazines.jsonに未登録"


def check_note_follow_cta(today: date) -> tuple[str, str]:
    """note記事末尾400字にフォローCTAがあるか確認する。(status, detail) を返す"""
    ds = str(today)
    note_files = sorted((SODA_DIR / "content" / "note").glob(f"{ds}_*.md"))
    if not note_files:
        return "❌", "今日のnote記事なし"

    tail = note_files[0].read_text()[-400:]
    if "フォロー" in tail:
        return "✅", "末尾400字にフォローCTAを検出"
    return "❌", "末尾400字にフォローCTAなし"


def read_follower_log() -> list[dict]:
    """logs/ops/follower_log.jsonl を読み込む。壊れた行はスキップする"""
    if not FOLLOWER_LOG.exists():
        return []
    entries = []
    for line in FOLLOWER_LOG.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


def check_followers(today: date) -> tuple[str, str, int | None]:
    """当日のfollowers数を読み取り、前回記録比を算出する。(status, detail, followers) を返す。
    ここではログへの書き込みは行わない（副作用なし）。"""
    ds = str(today)
    metrics_file = SODA_DIR / "logs" / "metrics" / f"{ds}.json"
    if not metrics_file.exists():
        return "⚠️", f"メトリクス未取得（logs/metrics/{ds}.json なし、スキップ）", None

    try:
        metrics = json.loads(metrics_file.read_text())
    except json.JSONDecodeError:
        return "⚠️", "メトリクスJSON解析エラー（スキップ）", None

    followers = metrics.get("followers")
    if followers is None:
        return "⚠️", "followersキー未整備（Task2整備待ち、スキップ）", None

    entries = read_follower_log()
    by_date = {e.get("date"): e.get("followers") for e in entries if "date" in e}
    prev_dates = sorted(d for d in by_date if d and d < ds)

    if prev_dates:
        prev_date = prev_dates[-1]
        prev_followers = by_date[prev_date]
        diff = followers - prev_followers
        sign = "+" if diff >= 0 else ""
        detail = f"{followers}人（前回記録比 {sign}{diff}、{prev_date}比較）"
    else:
        detail = f"{followers}人（比較データなし、記録開始）"

    return "✅", detail, followers


def append_follower_log(today: date, followers: int) -> None:
    """logs/ops/follower_log.jsonl に当日分を追記する（同日分が既にあれば追記しない）"""
    ds = str(today)
    entries = read_follower_log()
    if any(e.get("date") == ds for e in entries):
        return
    FOLLOWER_LOG.parent.mkdir(parents=True, exist_ok=True)
    with FOLLOWER_LOG.open("a") as f:
        f.write(json.dumps({"date": ds, "followers": followers}, ensure_ascii=False) + "\n")


ACTIONS = {
    "マガジン追加":         "config/magazines.json とlogs/daily/{ds}_magazine.txtの整備を確認し、今日の記事をマガジンに追加する",
    "note末尾フォローCTA":  "今日のnote記事末尾にフォロー導線文（agents/writer.md参照）を追加する（5分）",
    "プロフィール固定記事":  "note プロフィールにサイトマップ記事を固定表示し、docs/funnel_status.md を✅に更新する（15分）",
    "フォロワー数記録":     "logs/metrics/{ds}.json のfollowers取得が整うまで待機（Task2整備待ち）",
}


def check_funnel_status(item_keyword: str) -> str:
    """funnel_status.md から該当項目の「状態」欄のステータスを読み取る。
    「次のアクション」などの説明文中の✅記述に誤反応しないよう、
    見出し直後の **状態**: 行だけを見る。"""
    if not FUNNEL_STATUS.exists():
        return "❌"
    text = FUNNEL_STATUS.read_text()
    idx = text.find(item_keyword)
    if idx == -1:
        return "❌"
    status_idx = text.find("**状態**:", idx)
    if status_idx == -1 or status_idx - idx > 300:
        return "❌"
    snippet = text[status_idx:status_idx + 20]
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
    parser = argparse.ArgumentParser(description="SODA note導線確認スクリプト")
    parser.add_argument("--dry-run", action="store_true", help="結果を表示するだけ")
    args = parser.parse_args()

    today = date.today()
    ds = str(today)

    magazine_status, magazine_detail = check_magazine(today)
    note_cta_status, note_cta_detail = check_note_follow_cta(today)
    pinned_status = check_funnel_status("サイトマップ記事が固定表示されているか")
    followers_status, followers_detail, followers_value = check_followers(today)

    # 4項目を判定
    items = {
        "マガジン追加":        magazine_status,
        "note末尾フォローCTA": note_cta_status,
        "プロフィール固定記事": pinned_status,
        "フォロワー数記録":    followers_status,
    }
    details = {
        "マガジン追加":        magazine_detail,
        "note末尾フォローCTA": note_cta_detail,
        "プロフィール固定記事": "設定済み" if pinned_status == "✅" else ("準備中" if pinned_status == "⚠️" else "未設定"),
        "フォロワー数記録":    followers_detail,
    }
    ok_count = sum(1 for v in items.values() if v == "✅")
    phase = determine_phase(ok_count)

    # 最優先アクション（❌ → ⚠️ の順で最初の未完了）
    priority_item = next((k for k, v in items.items() if v == "❌"), None) or \
                    next((k for k, v in items.items() if v == "⚠️"), None)
    priority_action = (ACTIONS.get(priority_item, "すべて設定済みです").format(ds=ds)
                        if priority_item else "すべて設定済みです")

    rows = "\n".join(f"| {k} | {items[k]} | {details[k]} |" for k in items)

    report = f"""# note導線チェック — {ds}

| 項目 | 状態 | 詳細 |
|------|------|------|
{rows}

## 総合評価
**整備率**: {ok_count} / 4 項目
**フェーズ**: {phase}

## 今日やること（最優先1つだけ）
**タスク**: {priority_action}
"""

    if args.dry_run:
        print(report)
        return

    # フォロワー数が取得できていれば記録する（未取得日はスキップ）
    if followers_value is not None:
        append_follower_log(today, followers_value)

    log_file = SODA_DIR / "logs" / "cron" / f"{ds}_list_check.log"
    check_file = SODA_DIR / "logs" / "daily" / f"{ds}_list_check.md"

    check_file.write_text(report)
    log_file.write_text(f"[{today}] 導線チェック完了: {ok_count}/4項目\n{report}")

    # 未達（❌）項目があれば通知する（⚠️=準備中・スキップは通知しない）
    ng_items = [k for k, v in items.items() if v == "❌"]
    if ng_items:
        from soda_utils import notify_error
        notify_error("note導線チェック", f"未達: {'、'.join(ng_items)}（{ok_count}/4項目）。対応: {priority_action}")

    # funnel_status.md の更新ログに追記
    if FUNNEL_STATUS.exists():
        FUNNEL_STATUS.write_text(
            FUNNEL_STATUS.read_text() + f"| {ds} | 自動チェック: {ok_count}/4項目 |\n"
        )

    print(f"導線チェック完了: {ok_count}/4項目")
    print(report)


if __name__ == "__main__":
    main()
