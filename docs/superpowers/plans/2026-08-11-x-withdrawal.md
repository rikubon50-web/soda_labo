# X全面撤退・noteメトリクス切替 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** X関連機能をすべて撤去し、学習ループ（メトリクス取得→投稿分析→朝会議）をnoteベースに切り替えて、SODAをnote完結メディアにする。

**Architecture:** 新規 `scripts/note_metrics.py` が note の非公開統計API（Playwright永続セッション経由）で記事別ビュー・スキを取得し `logs/metrics/` に保存。既存の分析・会議スクリプトはプロンプトと入力データをnote版に書き換え、`daily_pipeline.py` からX工程とショー機構を除去。X専用ファイルは完全削除（git履歴に残る）。cron変更は全コード変更後の最終タスクで行う。

**Tech Stack:** Python 3、Playwright（`note_post.py` と同じ永続プロファイル `.browser_profile/note`）、Claude CLI

**Spec:** `docs/superpowers/specs/2026-08-11-x-withdrawal-design.md`

## Global Constraints

- 全テキスト・コミットメッセージは日本語
- パイプラインの note 公開フロー（`note_post.py`）と朝7:30会議・8:07パイプライン・8:45分析・21:15リード導線確認の cron 時刻は変更しない
- `run_list_check.py`（リード導線確認）と `daily_report.py`（休眠）と `retrofit_note_cta.py` は触らない
- 過去データ（`logs/tweet_ids/`・既存の `logs/metrics/*.json`）は削除しない
- `logs/daily/{ds}_post_analysis.md` の出力パスは変更しない（朝会議・パイプラインが読むため）
- crontab の変更は Task 7 まで行わない（コード削除より先に cron を消すと、削除済みスクリプトを cron が呼ぶ事故は起きないが、逆順だと note_metrics 未実装のまま 22:30 枠が空く）
- このプロジェクトに pytest 基盤はない。検証は各タスクの実行コマンドで行う

---

### Task 1: `scripts/note_metrics.py` 新規作成

**Files:**
- Create: `scripts/note_metrics.py`
- 参照（読むだけ）: `scripts/note_post.py`（Playwright永続コンテキストの起動パターン、31行目 `PROFILE_DIR` と 123行目 `launch_persistent_context` 周辺）

**Interfaces:**
- Produces: `logs/metrics/{YYYY-MM-DD}.json` — 形式 `{"date": "YYYY-MM-DD", "source": "note", "articles": [{"title": str, "key": str, "views": int, "likes": int, "comments": int}]}`（Task 2 の post_analysis がこれを読む）
- Produces: コマンド `python3 scripts/note_metrics.py`（Task 4 のパイプラインと Task 7 の cron が呼ぶ）

- [ ] **Step 1: note_post.py の起動パターンを確認する**

`scripts/note_post.py` を読み、`PROFILE_DIR`（`.browser_profile/note`）と `launch_persistent_context` の引数（ヘッドレス設定・ロック処理）を確認する。note_metrics.py でも同じプロファイルを使う。

- [ ] **Step 2: スクリプトを作成する**

以下の内容で `scripts/note_metrics.py` を作成する。noteのクリエイター統計は非公開API `https://note.com/api/v2/stats/pv` がダッシュボードの実体なので、ログイン済みセッションでこれを叩く。**レスポンスのキー名は実環境で異なる可能性があるため、パース失敗時は生レスポンスを `logs/errors/` に保存する設計にしてある**（Step 3 で実物を見て調整する）。

```python
#!/usr/bin/env python3
"""
noteメトリクス取得スクリプト（毎日22:30）
note.com のクリエイター統計API（要ログインセッション）から
記事別のビュー・スキ・コメント数を取得して logs/metrics/ に保存する。

使い方:
  python3 scripts/note_metrics.py           # 実行
  python3 scripts/note_metrics.py --dry-run # 取得結果を表示するだけで保存しない
"""

import json
import sys
import argparse
from datetime import date, datetime
from pathlib import Path

SODA_DIR    = Path(__file__).parent.parent
PROFILE_DIR = SODA_DIR / ".browser_profile" / "note"
METRICS_DIR = SODA_DIR / "logs" / "metrics"
ERRORS_DIR  = SODA_DIR / "logs" / "errors"

STATS_API = "https://note.com/api/v2/stats/pv?filter=all&page=1&sort=pv"


def fetch_stats() -> dict:
    """ログイン済みプロファイルで統計APIを叩き、生JSONを返す"""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            str(PROFILE_DIR),
            headless=True,
        )
        try:
            page = ctx.new_page()
            resp = page.goto(STATS_API, wait_until="domcontentloaded", timeout=30000)
            if resp is None or resp.status != 200:
                raise RuntimeError(f"統計APIがHTTP {resp.status if resp else '不明'} を返しました（セッション切れの可能性）")
            body = page.evaluate("() => document.body.innerText")
            return json.loads(body)
        finally:
            ctx.close()


def parse_articles(raw: dict) -> list[dict]:
    """APIレスポンスから記事別メトリクスを抽出する"""
    stats = raw.get("data", {}).get("note_stats", [])
    articles = []
    for s in stats:
        articles.append({
            "title":    s.get("name", ""),
            "key":      s.get("key", ""),
            "views":    int(s.get("read_count", 0)),
            "likes":    int(s.get("like_count", 0)),
            "comments": int(s.get("comment_count", 0)),
        })
    return articles


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    try:
        raw = fetch_stats()
        articles = parse_articles(raw)
        if not articles:
            raise ValueError("記事メトリクスが0件（APIレスポンス形式が想定と違う可能性）")
    except Exception as e:
        ERRORS_DIR.mkdir(parents=True, exist_ok=True)
        dump = ERRORS_DIR / f"note_metrics_{datetime.now():%Y%m%d_%H%M%S}.txt"
        detail = str(e)
        try:
            dump.write_text(json.dumps(raw, ensure_ascii=False, indent=2))
            detail += f"（生レスポンス: {dump}）"
        except Exception:
            pass
        print(f"noteメトリクス取得失敗: {detail}", file=sys.stderr)
        import subprocess
        subprocess.run(
            [sys.executable, str(SODA_DIR / "scripts" / "notify_error.py"),
             "noteメトリクス取得", detail[:300]],
            cwd=str(SODA_DIR),
        )
        return 1

    result = {"date": str(date.today()), "source": "note", "articles": articles}

    if args.dry_run:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    METRICS_DIR.mkdir(parents=True, exist_ok=True)
    out = METRICS_DIR / f"{date.today()}.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"保存: {out}（{len(articles)}記事）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: dry-run で実物のレスポンスを確認する**

Run: `cd /Users/rikubon50/Desktop/SODA_LABO && python3 scripts/note_metrics.py --dry-run`

Expected: 記事タイトルとビュー数のJSONが表示される。**失敗した場合**: `logs/errors/note_metrics_*.txt` の生レスポンスを見て `parse_articles()` のキー名（`note_stats`/`read_count` 等）を実物に合わせて修正し、再実行する。`fetch_stats` が401/ログインページを返す場合はセッション切れなので BLOCKED として報告する（人の手でnoteログインが必要）。

- [ ] **Step 4: 本実行して保存を確認する**

Run: `python3 scripts/note_metrics.py && python3 -c "import json; d=json.load(open('logs/metrics/$(date +%F).json')); assert d['source']=='note' and len(d['articles'])>0; print('OK', len(d['articles']), '記事')"`
Expected: `OK <N> 記事`

- [ ] **Step 5: コミット**

```bash
git add scripts/note_metrics.py
git commit -m "noteメトリクス取得スクリプトを追加（Xメトリクスの後継）"
```

---

### Task 2: `run_post_analysis.py` をnote記事アナリストに書き換え

**Files:**
- Modify: `scripts/run_post_analysis.py`（ANALYSIS_PROMPT 全置換、`refresh_metrics()`・`collect_yesterday_data()` 修正）

**Interfaces:**
- Consumes: Task 1 の `logs/metrics/{YYYY-MM-DD}.json`（note形式）と `python3 scripts/note_metrics.py`
- Produces: `logs/daily/{ds}_post_analysis.md`（パス・ファイル名は現行と同一。朝会議とパイプラインが読む）

- [ ] **Step 1: ANALYSIS_PROMPT を全置換する**

現在の「Xアカウント『SODA』の投稿データアナリスト」プロンプト（18〜55行目）を以下に置き換える。

```python
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
```

- [ ] **Step 2: `refresh_metrics()` の呼び先を差し替える**

`fetch_metrics.py` を呼んでいる行（62行目付近）を次に変更する（`--days 2` 引数は note_metrics に存在しないので付けない）:

```python
            [PYTHON, str(SODA_DIR / "scripts" / "note_metrics.py")],
```

- [ ] **Step 3: `collect_yesterday_data()` をnote入力に書き換える**

X投稿本文（`content/x_posts`）の読み込みを削除し、以下に置き換える:

```python
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
                if j.get("source") == "note":
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
```

main() 側でプロンプトに `data["x_content"]` を埋めている箇所があれば `data["note_content"]` に、「X投稿」「Xメトリクス」の見出し文字列は「note記事」「noteメトリクス」に合わせて書き換える。

- [ ] **Step 4: dry-run で検証する**

Run: `python3 scripts/run_post_analysis.py --dry-run | head -40 && python3 scripts/run_post_analysis.py --dry-run | grep -c "X投稿\|Xメトリクス\|インプレッション"`
Expected: note記事アナリストのプロンプトが表示され、grep カウントが `0`

- [ ] **Step 5: コミット**

```bash
git add scripts/run_post_analysis.py
git commit -m "投稿分析をnote記事アナリストに書き換え"
```

---

### Task 3: `run_meeting.py`・`weekly_analysis.py` のX参照をnoteに書き換え

**Files:**
- Modify: `scripts/run_meeting.py`（66行目付近のX夜投稿CTAルール、98行目付近のSecretary前日データ説明、259行目付近の「### Xメトリクス」、279行目付近の「### X投稿内容」）
- Modify: `scripts/weekly_analysis.py`（Xメトリクス・X投稿への参照全般）

**Interfaces:**
- Consumes: Task 1 のメトリクスJSON形式（`{"source": "note", "articles": [...]}`）
- Produces: なし（出力ファイルパスは現行維持）

- [ ] **Step 1: run_meeting.py を書き換える**

以下の方針で編集する（プロンプト文・データ組み立ての両方）:

1. 「X夜投稿のCTAルール（必須）」ブロック（66行目付近）を削除する
2. Secretaryの前日データ説明（98行目付近）の「Xメトリクス」を「noteメトリクス」に変更
3. データ組み立て部（259行目付近）: `lines.append("\n### Xメトリクス")` を `lines.append("\n### noteメトリクス")` にし、読み込み元はそのまま `logs/metrics/{ds}.json`（Task 1 のnote形式が入る）。読み込み後の整形がX形式（IMP・RT等）を前提にしている場合は `articles` 配列の `title/views/likes/comments` を列挙する形式に変更
4. 「### X投稿内容」ブロック（279行目付近）は丸ごと削除（note記事本文は既に別途渡している場合は重複させない。渡していなければ「### note記事」として `content/note/{ds}_*.md` を読む形に差し替え)
5. その他の「X投稿」「フォロワー」等のX前提文言を全て削除またはnote文言に変更

- [ ] **Step 2: run_meeting.py を検証する**

Run: `python3 scripts/run_meeting.py --dry-run 2>/dev/null | grep -c "X投稿\|Xメトリクス\|IMP\|リツイート" || echo 0; python3 -c "import ast; ast.parse(open('scripts/run_meeting.py').read()); print('syntax OK')"`
Expected: `0` と `syntax OK`（--dry-run オプションがないスクリプトの場合は `grep -c "X投稿\|Xメトリクス" scripts/run_meeting.py` で 0 を確認）

- [ ] **Step 3: weekly_analysis.py を書き換える**

同じ方針: プロンプト内の週次分析対象を「X投稿の反応」から「note記事のビュー・スキ推移」に変更し、メトリクス読み込みを note形式（`articles` 配列）前提に変更。X専用の集計（IMP合計・フォロワー増減等）は削除。

- [ ] **Step 4: weekly_analysis.py を検証する**

Run: `grep -c "X投稿\|Xメトリクス\|IMP\|フォロワー" scripts/weekly_analysis.py; python3 -c "import ast; ast.parse(open('scripts/weekly_analysis.py').read()); print('syntax OK')"`
Expected: `0` と `syntax OK`

- [ ] **Step 5: コミット**

```bash
git add scripts/run_meeting.py scripts/weekly_analysis.py
git commit -m "朝会議と週次分析をnoteメトリクスベースに書き換え"
```

---

### Task 4: `daily_pipeline.py` からX工程・ショー機構を除去

**Files:**
- Modify: `src/pipelines/daily_pipeline.py`

**Interfaces:**
- Consumes: Task 1 の `scripts/note_metrics.py`
- Produces: X工程なしのパイプライン（Step 0→1→1.5→2→3→4→5→5.5→6→7→7.5 → note投稿 → メトリクス取得）

- [ ] **Step 1: プロンプトからX関連を除去する**

`build_pipeline_prompt()` 内で以下を編集する:

1. Step 4 の「X投稿3本 → content/x_posts/...」ブロック（構造解説型テンプレート指示・朝昼夜の説明を含む）を丸ごと削除。note記事と短尺動画台本の指示は残す
2. Step 4 冒頭の説明文に「X投稿」への言及があれば削除
3. 短尺動画台本の指示はそのまま維持

- [ ] **Step 2: main() からX投稿・ショー機構を除去する**

以下をすべて行う:

1. `run_x_post()` 関数を削除
2. ショーモード関連を削除: `STOPPED_SHOWS`、`get_show_mode()`、`run_show_gen()`、main() 内のショーモード判定ブロック
3. `run_fetch_metrics()` を `run_note_metrics()` に改名し、呼び先を `scripts/note_metrics.py`（引数なし）に変更
4. main() の二重実行ガードとStep 8を次の形に書き換える:

```python
    # ─ コンテンツパイプライン（Step 0-7）──────────────────────────
    note_files = sorted(NOTE_DIR.glob(f"{ds}_*.md"))
    if note_files:
        _log.info(f"note記事ファイル存在。Claudeパイプラインをスキップ: {note_files[0].name}")
    else:
        _log.info("Claudeパイプライン開始（Step 0-7）")
        ok = run_content_pipeline(today, run_log)
        if not ok:
            _log.error("Claudeパイプライン失敗。note投稿をスキップ")
            return 1
        note_files = sorted(NOTE_DIR.glob(f"{ds}_*.md"))

    # ─ note投稿 ──────────────────────────────────────────────────
    if note_files:
        _log.info(f"note投稿: {note_files[0].name}")
        run_note_post(note_files[0], run_log)
    else:
        _notify_error("note記事ファイル未作成", f"content/note/{ds}_*.md が存在しません")
        _log.warning("note記事ファイルが見つかりません")

    # ─ CEOスコア確認 ─────────────────────────────────────────────
    _check_ceo_score(today)

    # ─ noteメトリクス取得 ────────────────────────────────────────
    _log.info("noteメトリクス取得")
    run_note_metrics(run_log)

    # ─ 成功通知 ──────────────────────────────────────────────────
    _notify_success()
    _log.info("全工程完了")
    return 0
```

5. 不要になった import（`X_POSTS_DIR`、ショー関連で使っていた `json` が他で未使用なら等）を整理する。`X_POSTS_DIR` が `src/config.py` で定義されている場合、config側の定義は残してよい（削除は他の参照確認が必要になるため今回はimportの除去のみ）

- [ ] **Step 3: 検証する**

Run:

```bash
cd /Users/rikubon50/Desktop/SODA_LABO && python3 -c "
import sys; sys.path.insert(0, '.')
from datetime import date
from src.pipelines.daily_pipeline import build_pipeline_prompt
p = build_pipeline_prompt(date(2026, 8, 13))
for ng in ['X投稿', 'x_posts', '構造解説型テンプレート']:
    assert ng not in p, f'X残存: {ng}'
for key in ['Step 1.5', 'Step 5.5', 'Step 7.5', '短尺動画台本', 'note記事']:
    assert key in p, f'欠落: {key}'
import src.pipelines.daily_pipeline as dp
assert not hasattr(dp, 'run_x_post') and not hasattr(dp, 'get_show_mode') and not hasattr(dp, 'run_show_gen')
assert hasattr(dp, 'run_note_metrics')
print('OK')
"
```

Expected: `OK`

- [ ] **Step 4: コミット**

```bash
git add src/pipelines/daily_pipeline.py
git commit -m "パイプラインからX投稿工程とショー機構を除去"
```

---

### Task 5: エージェント定義のX記述除去とCTA差替

**Files:**
- Modify: `agents/writer.md`、`agents/editor.md`、`agents/ceo.md`、`agents/secretary.md`、`agents/REGISTRY.md`
- Modify: `agents/analyst.md`（全面書き換え）

**Interfaces:**
- Consumes: なし
- Produces: X記述のないエージェント定義一式（パイプラインプロンプトが読む）

- [ ] **Step 1: writer.md を編集する**

1. 「## X投稿のフォーマット（構造解説型 / 標準）」セクション全体（構造解説型テンプレート・例・朝昼夜の使い分け・ルールを含む、次の `## 短尺動画台本のフォーマット` の直前まで）を削除
2. 「## 責任範囲」の「X投稿の下書き（1テーマにつき3本）」行を削除
3. 「## note記事末尾CTAルール」の定型文ブロックを以下に差し替え（前後のルール説明文は「note読者がフォローする価値を1文で示す」趣旨に合わせて修正）:

```
---

**毎日、AIニュースを1本ずつ構造解説しています**

「何が起きたか」だけでなく「なぜ起きているか」まで整理して、毎朝更新中。
フォローすると明日の解説が届きます。
```

4. その他「X投稿」への言及行（執筆ルール・制作ルール内）を削除

- [ ] **Step 2: editor.md・ceo.md・secretary.md・REGISTRY.md を編集する**

各ファイルで `grep -n "X投稿\|X 投稿\|Xメトリクス\|x.com\|@SODA_LABO\|ハッシュタグが含まれていないか"` を実行し、ヒットした行・チェック項目・フォーマット欄を削除またはnote文言に修正する。判断基準: X運用が前提の記述は削除、note/共通の記述は残す。

- [ ] **Step 3: analyst.md を全面書き換えする**

以下の内容に置き換える:

```markdown
# Analyst Claude

## 役割

noteメトリクス（ビュー・スキ・コメント）から勝ちパターンを抽出する。
数字の観察と仮説までが仕事。企画への落とし込みはPlannerとCEOが行う。

## 責任範囲

- 記事別ビュー・スキの日次観察（`logs/metrics/` のnote形式JSON）
- スキ率（スキ÷ビュー）による記事品質の推定
- 伸びるテーマ・フックの共通点抽出
- 週次でのテーマ別傾向分析と次週テーマ提案

## このAgentを呼ぶタイミング

- 毎朝の投稿分析（run_post_analysis.py）
- 週次分析（weekly_analysis.py）

## 分析のルール

- 数値に基づく。データがない observation は「データ不足」と明記する
- 単日の数字で結論を出さない。7日推移と比べる
- ビューが少ない記事にも「なぜ読まれなかったか」の仮説を必ず付ける

## 出力形式

```
【note記事分析】
対象: YYYY-MM-DD の記事
ビュー: n / スキ: n / スキ率: n%
観察: （7日平均との比較で1〜2文）
仮説: （原因の推定を1〜2文）
次に試すこと: （1点だけ）
```

## 禁止事項

- 感想を書かない（観察と仮説のみ)
- テーマ選定への直接介入（CEOの領域）

---
*作成日：2026-08-11 / 作成理由：X撤退に伴いXメトリクスアナリストからnote記事アナリストへ全面改訂*
```

- [ ] **Step 4: 検証する**

Run: `grep -rn "X投稿\|Xメトリクス\|x.com/SODA_LABO" agents/ | grep -v "^agents/skills" ; echo "exit:$?"`
Expected: `exit:1`（ヒットなし）。`agents/skills/skill_x_thread.md` が残っていればヒットするが、それは Task 6 で削除するのでこの時点では `grep -v` で除外してよい

- [ ] **Step 5: コミット**

```bash
git add agents/
git commit -m "エージェント定義からX記述を除去しCTAをnoteフォロー版に差替"
```

---

### Task 6: X専用ファイルの削除

**Files:**
- Delete: `scripts/x_post.py`、`scripts/auto_reply.py`、`scripts/remind_reply.py`、`scripts/run_keyword_review.py`、`scripts/run_cta_review.py`、`scripts/fetch_metrics.py`、`scripts/run_show_gen.py`、`scripts/shows/`（ディレクトリごと）、`config/reply_keywords.json`、`docs/x_strategy.md`、`docs/x_profile_copy.md`、`docs/x_reply_api_memo.md`、`agents/skills/skill_x_thread.md`

**Interfaces:**
- Consumes: Task 2〜5 で参照元がすべて書き換え済みであること

- [ ] **Step 1: 削除前に生存参照がないことを確認する**

Run: `grep -rln "x_post\|auto_reply\|remind_reply\|run_keyword_review\|run_cta_review\|fetch_metrics\|run_show_gen\|reply_keywords\|skill_x_thread" scripts/ src/ agents/ --include="*.py" --include="*.md" | grep -v "daily_report.py" | sort`
Expected: 削除対象ファイル自身のみが列挙される（`daily_report.py` はスコープ外につき除外済み）。それ以外のファイルがヒットしたら、そのファイルの参照を先に除去する（Task 2〜5 の漏れ）

- [ ] **Step 2: 削除する**

```bash
git rm scripts/x_post.py scripts/auto_reply.py scripts/remind_reply.py \
  scripts/run_keyword_review.py scripts/run_cta_review.py scripts/fetch_metrics.py \
  scripts/run_show_gen.py config/reply_keywords.json \
  docs/x_strategy.md docs/x_profile_copy.md docs/x_reply_api_memo.md \
  agents/skills/skill_x_thread.md
git rm -r scripts/shows/
```

`scripts/shows/__pycache__` が git 管理外で残る場合は `rm -rf scripts/shows` で掃除する。

- [ ] **Step 3: 検証する**

Run: `ls scripts/x_post.py scripts/shows 2>&1 | grep -c "No such"; python3 -c "import sys; sys.path.insert(0,'.'); from src.pipelines.daily_pipeline import build_pipeline_prompt; print('import OK')"`
Expected: `2` と `import OK`

- [ ] **Step 4: コミット**

```bash
git commit -m "X専用スクリプト・ショー機構・X戦略ドキュメントを削除"
```

---

### Task 7: crontab 更新と最終検証

**Files:**
- Modify: ユーザーcrontab（`crontab -l` / `crontab -`）。バックアップを `logs/ops/crontab_backup_2026-08-11.txt` に保存

**Interfaces:**
- Consumes: Task 1 の `scripts/note_metrics.py`（22:30枠の新しい呼び先）

- [ ] **Step 1: 現在のcrontabをバックアップする**

```bash
mkdir -p logs/ops && crontab -l > logs/ops/crontab_backup_2026-08-11.txt && wc -l logs/ops/crontab_backup_2026-08-11.txt
```

- [ ] **Step 2: X関連4本を削除し、22:30をnote_metricsに差し替える**

```bash
crontab -l \
  | grep -v "x_post.py" \
  | grep -v "run_cta_review.py" \
  | grep -v "run_keyword_review.py" \
  | sed 's|/Users/rikubon50/Desktop/SODA_LABO/scripts/fetch_metrics.py --days 2|/Users/rikubon50/Desktop/SODA_LABO/scripts/note_metrics.py|; s|logs/cron/fetch_metrics.log|logs/cron/note_metrics.log|' \
  | crontab -
```

- [ ] **Step 3: crontabを検証する**

Run: `crontab -l | grep -c "x_post\|cta_review\|keyword_review\|fetch_metrics"; crontab -l | grep note_metrics; crontab -l | grep -c "run_daily\|run_meeting\|run_post_analysis\|run_list_check"`
Expected: `0`、note_metrics の行（22:30）が表示、既存ジョブのカウント `4`（run_daily・meeting・post_analysis・list_check が無傷）

- [ ] **Step 4: 全体の残存参照チェック**

Run: `grep -rn "X投稿\|Xメトリクス\|x.com/SODA_LABO\|tweepy" scripts/ src/ agents/ --include="*.py" --include="*.md" | grep -v daily_report.py`
Expected: ヒットなし

- [ ] **Step 5: コミット（バックアップファイルのみ）**

```bash
git add logs/ops/crontab_backup_2026-08-11.txt
git commit -m "crontab更新（X関連4本削除・22:30をnoteメトリクスに差替）のバックアップを記録"
```

---

## 実装後の運用検証（翌朝〜翌晩）

1. 朝8:07: パイプラインがX工程なしで完走し、note公開まで到達（`logs/cron/{当日}_run.log`）
2. 朝8:45: `logs/daily/{当日}_post_analysis.md` がnote版フォーマット（「SODA 記事分析」見出し）で生成
3. 夜22:30: `logs/metrics/{当日}.json` に `"source": "note"` のメトリクスが保存
4. 12:00・18:00・20:00・日曜21:00 に cron エラーメールが来ないこと
