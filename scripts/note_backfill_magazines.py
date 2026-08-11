#!/usr/bin/env python3
"""
既存note記事の一括マガジン振り分けスクリプト（Task 3）。

背景:
  Task 1（scripts/note_magazine.py）で3誌を作成済み（config/magazines.json）。
  当日記事は note_magazine.py --add-today で1件ずつ振り分けられるが、
  それ以前に公開済みの既存記事（logs/metrics/{最新}.json に含まれる全記事）は
  未分類のまま残っている。本スクリプトはそれを一括で分類・追加する。

処理フロー:
  1. logs/metrics/ の最新JSONから全記事（title, key）を取得
  2. logs/ops/magazine_assignment.json を読み込み、status: "added" の記事は
     再実行時にスキップする（同じ記事を二重にマガジン追加しないための冪等性担保）
  3. 未処理記事のタイトル一覧を1回の run_claude 呼び出しでまとめて分類する
     （3誌の名前と対象定義を提示し、番号→誌名のJSON配列で返させる。ツール不要のテキスト応答）。
     応答のパースに失敗した記事、または応答自体が壊れている場合は
     note_magazine.py の FALLBACK_RULES / DEFAULT_MAGAZINE で判定する。
  4. --dry-run のときはここで終了（Playwrightは一切起動しない）。分類結果を表示するのみ。
  5. 本実行時は note_magazine.py の _launch_ctx 等を再利用し、Playwrightセッションで
     1記事ずつマガジンに追加する（記事間 time.sleep(2)）。追加操作は
     note_magazine.py の add_today() と同じUI操作パターン（「記事を追加」アイコン→
     マガジン名クリック→belonging_magazine_keys で検証）を踏襲する。
     失敗した記事は "failed" として記録し、処理を継続する。
  6. 完了後、追加/失敗/スキップの件数を表示する。

再実行安全性:
  logs/ops/magazine_assignment.json には「今回の実行で実際に処理した記事」のみを
  逐次追記・上書き保存する。まだ一度も処理していない記事はファイルに現れない
  （次回実行時にあらためて分類・処理される）。これにより --limit で分割実行しても
  取りこぼしなく全記事を処理できる。

CLI:
  --dry-run       分類結果を表示するのみ（Playwright起動なし。本実行では使わない）
  --limit N       先頭N件（未処理記事のうち）だけ追加を実行する

使い方:
  python3 scripts/note_backfill_magazines.py --dry-run
  python3 scripts/note_backfill_magazines.py --limit 5
  python3 scripts/note_backfill_magazines.py
"""

import argparse
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

from soda_utils import SODA_DIR, run_claude, notify_error

from note_magazine import (
    MAGAZINES,
    FALLBACK_RULES,
    DEFAULT_MAGAZINE,
    CREATOR_URLNAME,
    SEL_NOTE_MAGAZINE_ADD_ICON,
    _load_config,
    _launch_ctx,
    _dump_failure,
)

METRICS_DIR    = SODA_DIR / "logs" / "metrics"
ASSIGNMENT_PATH = SODA_DIR / "logs" / "ops" / "magazine_assignment.json"


# ─── 記事一覧 / 割り当て台帳の読み書き ──────────────────────────────────

def _latest_metrics_articles() -> list[dict]:
    """logs/metrics/ の最新JSONから記事一覧（title, key を含む）を返す"""
    files = sorted(METRICS_DIR.glob("*.json"))
    if not files:
        raise RuntimeError(f"metrics JSONが見つかりません: {METRICS_DIR}")
    latest = files[-1]
    raw = json.loads(latest.read_text(encoding="utf-8"))
    articles = raw.get("articles", [])
    print(f"metricsソース: {latest.name}（{len(articles)}件）", file=sys.stderr)
    return articles


def _load_assignment() -> list[dict]:
    if ASSIGNMENT_PATH.exists():
        try:
            return json.loads(ASSIGNMENT_PATH.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _save_assignment(assignment: list[dict]) -> None:
    ASSIGNMENT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ASSIGNMENT_PATH.write_text(
        json.dumps(assignment, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ─── 分類（run_claude 1回呼び出し + フォールバック） ─────────────────────

def _fallback_classify(title: str) -> str:
    """note_magazine.py の FALLBACK_RULES / DEFAULT_MAGAZINE によるキーワード判定"""
    for keywords, name in FALLBACK_RULES:
        if any(kw in title for kw in keywords):
            return name
    return DEFAULT_MAGAZINE


def _parse_json_array(text: str):
    """Claude応答からJSON配列を取り出す。コードフェンス・前後の説明文があっても拾う"""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    start, end = text.find("["), text.rfind("]")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass
    return None


def _classify_via_claude(articles: list[dict]) -> dict:
    """1回の run_claude 呼び出しでタイトル一覧を分類する。戻り値: {key: 誌名}。
    応答が全く得られない/パースできない場合は空dictを返す（呼び出し側でフォールバック）。
    """
    if not articles:
        return {}

    magazine_lines = "\n".join(f"- 「{name}」: {desc}" for name, desc in MAGAZINES.items())
    numbered = "\n".join(f"{i}: {a['title']}" for i, a in enumerate(articles))

    prompt = f"""以下はnote記事のタイトル一覧です。各記事を、次の3つのマガジンのうち最も適切な1つに分類してください。

{magazine_lines}

判定基準:
- タイトルの主題（何についての記事か）で判断する
- 複数のマガジンに該当しそうでも、最も近いテーマを1つだけ選ぶ
- 誌名は上記3つの名称と完全一致させること

記事一覧（番号: タイトル）:
{numbered}

出力形式: 説明文やコードフェンスを付けず、以下のJSON配列のみを出力してください。
[{{"index": 0, "magazine": "誌名"}}, {{"index": 1, "magazine": "誌名"}}, ...]

全{len(articles)}件ぶん、番号0から{len(articles) - 1}まですべて漏れなく出力してください。"""

    result = run_claude(prompt, tools=["Read"], timeout=600)
    if result.returncode != 0:
        print(f"分類用run_claude失敗: {result.stderr[-300:]}", file=sys.stderr)
        return {}

    parsed = _parse_json_array(result.stdout)
    if not isinstance(parsed, list):
        print("分類応答のJSONパースに失敗（フォールバックを使用）", file=sys.stderr)
        return {}

    valid_names = set(MAGAZINES.keys())
    mapping: dict[str, str] = {}
    for item in parsed:
        if not isinstance(item, dict):
            continue
        idx = item.get("index")
        name = item.get("magazine")
        if not isinstance(idx, int) or not (0 <= idx < len(articles)):
            continue
        if name not in valid_names:
            continue
        mapping[articles[idx]["key"]] = name
    return mapping


def classify_articles(articles: list[dict]) -> dict:
    """全記事を分類する。Claude応答で拾えなかった記事はFALLBACK_RULESで補完する。
    戻り値: {key: 誌名}（articles全件ぶん、必ず埋まる）
    """
    mapping = _classify_via_claude(articles)
    fallback_used = 0
    for a in articles:
        if a["key"] not in mapping:
            mapping[a["key"]] = _fallback_classify(a["title"])
            fallback_used += 1
    if fallback_used:
        print(f"フォールバック判定を使用した記事: {fallback_used}件", file=sys.stderr)
    return mapping


# ─── 本実行: Playwrightでの追加処理 ────────────────────────────────────

def _add_article_to_magazine(page, note_key: str, magazine_name: str, magazine_key: str) -> None:
    """note_magazine.py の add_today() と同じUI操作パターンで1記事を1マガジンに追加する"""
    note_url = f"https://note.com/{CREATOR_URLNAME}/n/{note_key}"
    page.goto(note_url, wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(2000)

    add_icon = page.query_selector(SEL_NOTE_MAGAZINE_ADD_ICON)
    if not add_icon:
        _dump_failure(page, f"backfill_add_icon_not_found_{note_key}")
        raise RuntimeError("「記事を追加」ボタンが見つかりません")
    add_icon.click()
    page.wait_for_timeout(1500)

    target = page.query_selector(f'text="{magazine_name}"')
    if not target:
        _dump_failure(page, f"backfill_modal_target_not_found_{note_key}")
        raise RuntimeError(f"マガジン選択モーダルに '{magazine_name}' が見つかりません")
    target.click()
    page.wait_for_timeout(2000)

    resp = page.goto(f"https://note.com/api/v3/notes/{note_key}", wait_until="domcontentloaded", timeout=20000)
    if resp is None or resp.status != 200:
        _dump_failure(page, f"backfill_verify_fetch_failed_{note_key}")
        raise RuntimeError(f"追加後の検証取得に失敗: status={resp.status if resp else '不明'}")
    body = page.evaluate("() => document.body.innerText")
    raw = json.loads(body)
    belonging = raw.get("data", {}).get("belonging_magazine_keys", [])
    if magazine_key not in belonging:
        _dump_failure(page, f"backfill_verify_failed_{note_key}")
        raise RuntimeError(f"追加後の検証に失敗（belonging_magazine_keys={belonging}）")


def run_backfill(articles: list[dict], assignment: list[dict], limit: int | None) -> None:
    """未処理記事を分類し、Playwrightで実際にマガジンに追加する（本実行）"""
    added_keys = {e["key"] for e in assignment if e.get("status") == "added"}
    pending = [a for a in articles if a["key"] not in added_keys]

    if not pending:
        print("追加対象なし（全記事が処理済み）")
        return

    mapping = classify_articles(pending)
    targets = pending[:limit] if limit is not None else pending
    skipped_count = len(pending) - len(targets)

    config = _load_config()

    added = failed = 0
    pw = ctx = None
    try:
        pw, ctx = _launch_ctx(headless=True)
        page = ctx.new_page()
        for a in targets:
            key, title = a["key"], a["title"]
            magazine_name = mapping[key]
            magazine_info = config.get(magazine_name)

            if not magazine_info:
                print(f"失敗（未登録マガジン）: {title} → {magazine_name}", file=sys.stderr)
                status = "failed"
                failed += 1
            else:
                try:
                    _add_article_to_magazine(page, key, magazine_name, magazine_info["key"])
                    status = "added"
                    added += 1
                    print(f"追加完了: {title} → {magazine_name}")
                except Exception as e:
                    print(f"追加失敗: {title} → {magazine_name}（{e}）", file=sys.stderr)
                    status = "failed"
                    failed += 1

            assignment = [e for e in assignment if e.get("key") != key]
            assignment.append({"key": key, "title": title, "magazine": magazine_name, "status": status})
            _save_assignment(assignment)
            time.sleep(2)
    finally:
        if ctx:
            ctx.close()
        if pw:
            pw.stop()

    print(f"\n完了: added={added} failed={failed} skipped(limit超過)={skipped_count}")


def run_dry_run(articles: list[dict], assignment: list[dict]) -> None:
    """分類結果の表示のみ。Playwrightは起動しない"""
    added_keys = {e["key"] for e in assignment if e.get("status") == "added"}
    pending = [a for a in articles if a["key"] not in added_keys]

    print(f"対象記事: {len(articles)}件（既に追加済み: {len(added_keys)}件 / 分類対象: {len(pending)}件）")
    print("")

    if not pending:
        print("分類対象なし（全記事が処理済み）")
        return

    mapping = classify_articles(pending)

    for a in pending:
        print(f"[{mapping[a['key']]}] {a['title']}")

    counts = Counter(mapping[a["key"]] for a in pending)
    print("\n--- 誌別内訳 ---")
    for name in MAGAZINES:
        print(f"  {name}: {counts.get(name, 0)}件")


# ─── main ───────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="既存note記事の一括マガジン振り分け")
    parser.add_argument("--dry-run", action="store_true", help="分類結果を表示するのみ（Playwright起動なし）")
    parser.add_argument("--limit", type=int, default=None, help="先頭N件（未処理記事のうち）だけ追加を実行する")
    args = parser.parse_args()

    try:
        articles = _latest_metrics_articles()
        assignment = _load_assignment()

        if args.dry_run:
            run_dry_run(articles, assignment)
        else:
            run_backfill(articles, assignment, args.limit)
    except Exception as e:
        detail = str(e)
        print(f"既存記事マガジン振り分け失敗: {detail}", file=sys.stderr)
        if not args.dry_run:
            notify_error("既存記事マガジン振り分け", detail[:300])
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
