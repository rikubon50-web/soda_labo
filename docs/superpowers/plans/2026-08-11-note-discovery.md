# note内発見性・導線再設計 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** note内の発見面（マガジン3誌・プロフィール・固定サイトマップ記事・タグ規則・導線チェック）を一度で整備し、日次維持を自動化する。

**Architecture:** 新規 `scripts/note_magazine.py` がマガジン操作（作成・当日記事追加・プロフィール更新）を担い、`scripts/note_backfill_magazines.py`（使い捨て）が既存111本を一括振り分けする。noteのマガジン系エンドポイントは非公開のため、**まず実UIのネットワークトレースで実エンドポイントを特定してから実装を確定する**（note_metrics.py で成功した実物合わせパターン）。日次はパイプラインが誌名判定ファイルを書き、note投稿成功後に追加を実行。

**Tech Stack:** Python 3、Playwright（`.browser_profile/note` 永続セッション、`note_metrics.py` の `launch_persistent_context` パターン踏襲）、Claude CLI（`soda_utils.run_claude`）

**Spec:** `docs/superpowers/specs/2026-08-11-note-discovery-design.md`

## Global Constraints

- 全テキスト・コミットメッセージは日本語
- note側操作は必ず `--dry-run` / `--limit 1` で実挙動を確認してから全量実行
- note操作の失敗はすべて「notify_error 通知して継続」。パイプラインを止めない
- **notify_error.py を実発火させるテスト禁止**（実メールが飛ぶ）
- マガジン名・説明文・プロフィール文・タグ規則は仕様書の文言をそのまま使う（変更禁止）
- cron時刻は変更しない（21:15 の run_list_check はそのまま）
- Playwright 起動は `note_metrics.py` の `launch_persistent_context(str(PROFILE_DIR), headless=True)` パターンを踏襲。ページ間・記事間ウェイトは最低2秒
- このプロジェクトに pytest 基盤はない。検証は各タスクの実行コマンドで行う

---

### Task 1: `scripts/note_magazine.py` 新規作成（マガジン操作の中核）

**Files:**
- Create: `scripts/note_magazine.py`
- 参照（読むだけ）: `scripts/note_metrics.py`（Playwright起動・API呼び出し・エラーダンプのパターン）

**Interfaces:**
- Produces: CLI `python3 scripts/note_magazine.py <サブコマンド>`:
  - `--discover` … マガジン管理UIを開いてネットワークトレースを `logs/errors/magazine_api_trace.txt` に記録（開発用）
  - `--create-all` … 3誌を作成（既存同名誌はスキップ）。作成結果（誌名→magazine key）を `config/magazines.json` に保存
  - `--add-today` … `logs/daily/{今日}_magazine.txt` の誌名（なければタイトルからルール判定）に当日記事を追加
  - `--update-profile` … プロフィール文を仕様の文面に更新
- Produces: `config/magazines.json` = `{"AIとマネーの定点観測": {"key": "...", "id": ...}, ...}`（Task 3・6 が読む）

- [ ] **Step 1: 実エンドポイントを特定する**

以下の骨格で `--discover` を先に実装し、実行してトレースを取る:

```python
def discover(ctx):
    """マガジン管理UIを操作し、飛んだAPIリクエストを記録する（開発用）"""
    page = ctx.new_page()
    trace = []
    page.on("request", lambda r: trace.append(f"{r.method} {r.url}\n  post={r.post_data}") if "/api/" in r.url and r.method in ("POST", "PUT", "PATCH", "DELETE") else None)
    page.on("response", lambda r: trace.append(f"  -> {r.status} {r.url}") if "/api/" in r.url else None)
    page.goto("https://note.com/notes", wait_until="domcontentloaded")
    page.wait_for_timeout(3000)
    # マガジン管理ページへ（URLは実環境で確認: https://note.com/magazines または設定画面から）
    page.goto("https://note.com/magazines", wait_until="domcontentloaded")
    page.wait_for_timeout(5000)
    (ERRORS_DIR / "magazine_api_trace.txt").write_text("\n".join(trace))
```

`--discover` 実行後、**Playwrightのheadless=Falseで一時的に起動してマガジンを1誌手動相当の操作（page.click等）で作成してみて**、トレースに現れた実エンドポイント・ペイロードを確認する。仮説は `POST https://note.com/api/v1/our/magazines`（作成）と `POST https://note.com/api/v1/our/magazines/{key}/notes`（記事追加）。**実トレースが違えば実物に合わせる**。UI操作でしか作成できない場合は `page.click`/`form_input` によるUI自動化で実装してよい（その場合もセレクタをコード内定数にまとめる）。

- [ ] **Step 2: 本実装する**

構成（`note_metrics.py` のパターン踏襲）:

```python
MAGAZINES = {
    "AIとマネーの定点観測": "AIに流れるお金を毎朝定点観測。投資・M&A・資金調達を『なぜ』で読む。",
    "AIと雇用のゆくえ": "AIは誰の仕事をどう変えるのか。レイオフ・働き方・組織の変化を毎朝追う。",
    "AI業界の構造転換": "勝者が入れ替わる瞬間を見逃さない。AI企業の戦略・競争・規制を構造で解説。",
}

PROFILE_TEXT = "毎朝8時、AIニュースを1本だけ深掘り。「何が起きたか」ではなく「なぜ起きているか」まで構造解説します。企画・取材・執筆・公開まで全部AIが運営する実験メディア。"

FALLBACK_RULES = [  # (キーワード群, 誌名)。上から順に判定
    (["レイオフ", "雇用", "人員", "削減", "解雇", "働き方", "スキル"], "AIと雇用のゆくえ"),
    (["投資", "買収", "資金", "ドル", "億円", "M&A", "合弁", "ARR", "評価額"], "AIとマネーの定点観測"),
]
DEFAULT_MAGAZINE = "AI業界の構造転換"
```

- `--create-all`: 既存マガジン一覧を取得（`GET /api/v2/creators/soda_labo` 系 or 発見した一覧API）し、未作成の誌のみ作成。結果を `config/magazines.json` に保存
- `--add-today`: `logs/daily/{date.today()}_magazine.txt` を読む（1行目=誌名）。ない/不正なら当日 `content/note/{ds}_*.md` のタイトルに FALLBACK_RULES を適用。当日記事の note key は `logs/daily/{ds}_note_url.txt` のURL末尾（`/n/nXXXX`）から取得。追加後、確認のためマガジン内記事一覧を取得して当該keyが含まれることを検証
- `--update-profile`: プロフィール設定（`https://note.com/settings/profile` のUI or 発見したAPI）で自己紹介文を PROFILE_TEXT に更新
- すべての操作で失敗時: 生レスポンス/スクリーンショットを `logs/errors/` にダンプ → `notify_error.py` 呼び出し → exit 1（`--dry-run` では何も書き込まない）

- [ ] **Step 3: dry-run 検証**

Run: `cd /Users/rikubon50/Desktop/SODA_LABO && python3 scripts/note_magazine.py --create-all --dry-run && python3 scripts/note_magazine.py --add-today --dry-run`
Expected: 作成予定3誌と、当日記事の判定誌名が表示される（書き込みなし）

- [ ] **Step 4: 本実行（マガジン作成のみ）**

Run: `python3 scripts/note_magazine.py --create-all && cat config/magazines.json`
Expected: 3誌のkeyが保存される。`https://note.com/api/v2/creators/soda_labo` を再取得して `magazineCount: 3` になっていることを確認

- [ ] **Step 5: コミット**

```bash
git add scripts/note_magazine.py config/magazines.json
git commit -m "noteマガジン操作スクリプトを追加（3誌作成・当日追加・プロフィール更新）"
```

---

### Task 2: `note_metrics.py` にフォロワー数記録を追加

**Files:**
- Modify: `scripts/note_metrics.py`

**Interfaces:**
- Produces: 日次JSON（`logs/metrics/{ds}.json`）に `"followers": int` フィールド追加（Task 6 の導線チェックと週次分析が読む）

- [ ] **Step 1: 実装する**

`fetch_stats()` と同じコンテキスト内で `https://note.com/api/v2/creators/soda_labo` を取得し、`data.followerCount`（実レスポンスのキー名を確認して合わせる）を読む関数 `fetch_followers(page) -> int` を追加。`main()` の result に `"followers": followers` を追加。取得失敗時は `"followers": None` として続行（メトリクス本体を巻き添えにしない）。

- [ ] **Step 2: 検証する**

Run: `python3 scripts/note_metrics.py --dry-run | python3 -c "import json,sys; d=json.load(sys.stdin); print('followers:', d['followers']); assert d['followers'] is None or d['followers'] >= 5"`
Expected: `followers: 5`（現在値）

- [ ] **Step 3: コミット**

```bash
git add scripts/note_metrics.py
git commit -m "noteメトリクスにフォロワー数を追加"
```

---

### Task 3: `scripts/note_backfill_magazines.py` 新規作成（既存111本の一括振り分け）

**Files:**
- Create: `scripts/note_backfill_magazines.py`

**Interfaces:**
- Consumes: `config/magazines.json`（Task 1）、`logs/metrics/{最新}.json` の記事一覧（title/key）、`soda_utils.run_claude`
- Produces: `logs/ops/magazine_assignment.json` = `[{"key": "...", "title": "...", "magazine": "誌名", "status": "added|failed|skipped"}]`

- [ ] **Step 1: 実装する**

処理フロー:

1. `logs/metrics/` の最新JSONから全記事（title, key）を取得
2. `logs/ops/magazine_assignment.json` が既にあれば読み込み、`status: "added"` の記事はスキップ（再実行安全）
3. 未分類記事のタイトル一覧を1回の `run_claude` 呼び出しでまとめて分類（プロンプト: 3誌の名前と対象定義を提示し、`タイトル → 誌名` のJSON配列で返させる。ツール不要のテキスト応答）。応答パース失敗時は Task 1 の FALLBACK_RULES で判定（note_magazine.py から import する）
4. Playwright セッションで1記事ずつマガジンに追加（記事間 `time.sleep(2)`）。失敗は `"failed"` として記録し継続
5. 完了後、集計（added/failed/skipped 件数）を表示

CLI: `--dry-run`（分類結果表示のみ）と `--limit N`（先頭N件だけ追加）を必ず付ける。

- [ ] **Step 2: dry-run で分類品質を確認する**

Run: `python3 scripts/note_backfill_magazines.py --dry-run | head -20`
Expected: 111件の分類が表示され、明らかな誤分類（レイオフ記事がマネー誌等）が目視で概ねないこと

- [ ] **Step 3: 1件だけ本実行して確認する**

Run: `python3 scripts/note_backfill_magazines.py --limit 1 && python3 -c "import json; a=json.load(open('logs/ops/magazine_assignment.json')); print(a[0])"`
Expected: `"status": "added"`。実際にnote上の該当マガジンページに記事が表示されることをAPIまたはページ取得で確認

- [ ] **Step 4: コミット（全量実行は Task 7 で行う）**

```bash
git add scripts/note_backfill_magazines.py
git commit -m "既存記事のマガジン一括振り分けスクリプトを追加"
```

---

### Task 4: パイプラインに誌名判定とマガジン追加を組み込む

**Files:**
- Modify: `src/pipelines/daily_pipeline.py`

**Interfaces:**
- Consumes: `scripts/note_magazine.py --add-today`（Task 1）
- Produces: パイプラインプロンプトの Step 7.6（誌名判定 → `logs/daily/{ds}_magazine.txt`）と、main() の note投稿成功後のマガジン追加呼び出し

- [ ] **Step 1: プロンプトに Step 7.6 を追加する**

`build_pipeline_prompt()` の `## Step 7.5` ブロックの直後（`## 全体ルール` の前）に挿入:

```
## Step 7.6: 本日記事のマガジン判定
本日のnote記事を以下の3誌のうち最も主題が近い1誌に判定し、誌名のみ（1行）を logs/daily/{ds}_magazine.txt に保存する。
- AIとマネーの定点観測（投資・M&A・資金調達・企業価値）
- AIと雇用のゆくえ（レイオフ・働き方・スキル・組織）
- AI業界の構造転換（企業戦略・競争・規制・技術転換）
```

- [ ] **Step 2: main() にマガジン追加を組み込む**

`run_note_post(note_files[0], run_log)` が True を返した直後に実行する関数を追加:

```python
def run_magazine_add(run_log: Path) -> bool:
    """当日記事をマガジンに追加する。失敗しても続行。"""
    try:
        r = subprocess.run(
            [PYTHON_BIN, str(SCRIPTS_DIR / "note_magazine.py"), "--add-today"],
            capture_output=True, text=True, timeout=120, cwd=str(SODA_DIR),
        )
        _log_append(run_log, r.stdout + r.stderr)
        if r.returncode != 0:
            _notify_error("マガジン追加", r.stderr[-300:] or "詳細不明", run_log)
            return False
        return True
    except Exception as e:
        _notify_error("マガジン追加", str(e), run_log)
        return False
```

main() 側:

```python
    if note_files:
        _log.info(f"note投稿: {note_files[0].name}")
        if run_note_post(note_files[0], run_log):
            _log.info("マガジン追加")
            run_magazine_add(run_log)
```

- [ ] **Step 3: 検証する**

Run: `python3 -c "import sys; sys.path.insert(0,'.'); from datetime import date; from src.pipelines.daily_pipeline import build_pipeline_prompt; p=build_pipeline_prompt(date(2026,8,13)); assert 'Step 7.6' in p and p.index('Step 7.6') < p.index('## 全体ルール') and '2026-08-13_magazine.txt' in p; import src.pipelines.daily_pipeline as dp; assert hasattr(dp,'run_magazine_add'); print('OK')"`
Expected: `OK`

- [ ] **Step 4: コミット**

```bash
git add src/pipelines/daily_pipeline.py
git commit -m "パイプラインに誌名判定とマガジン自動追加を組み込み"
```

---

### Task 5: `agents/writer.md` のタグ・タイトル規則を差し替える

**Files:**
- Modify: `agents/writer.md`（「note記事ハッシュタグルール」セクション）

- [ ] **Step 1: ハッシュタグルールを置換する**

現行の「候補例から5つ」の記述（候補例リスト含む）を以下に置換:

```markdown
## note記事ハッシュタグルール

note記事の末尾（本文の最後の行の後）にハッシュタグを5つ、以下の設計で付与する。

```
#タグ1 #タグ2 #タグ3 #タグ4 #タグ5
```

1. **大タグ2個（固定）**: `#AI` `#生成AI` — noteのタグページ流入用
2. **検索ニッチタグ2個**: 記事の主題で読者が実際に検索しそうな語（例: `#レイオフ` `#AI投資` `#AI規制` `#働き方`）
3. **記事固有タグ1個**: 企業名・製品名（例: `#OpenAI` `#Anthropic` `#Gemini`）

- 1行にまとめて書く
- 大タグ以外は記事内容から選ぶ。汎用すぎるタグ（#ビジネス #ニュース）は避ける
```

「執筆ルール」セクションに1行追加: `- タイトルには読者が検索しそうな固有名詞または数字を必ず1つ含める`

- [ ] **Step 2: 検証する**

Run: `grep -n "大タグ2個\|検索ニッチタグ\|記事固有タグ\|固有名詞または数字" agents/writer.md | wc -l`
Expected: `4`

- [ ] **Step 3: コミット**

```bash
git add agents/writer.md
git commit -m "ハッシュタグ規則を発見性重視の3層設計に変更"
```

---

### Task 6: 導線チェックのnote化と `funnel_status.md` 書き換え

**Files:**
- Modify: `scripts/run_list_check.py`（チェック項目の全面置換。cron時刻21:15は不変）
- Modify: `docs/funnel_status.md`（全面書き換え）

**Interfaces:**
- Consumes: `config/magazines.json`（Task 1）、`logs/daily/{ds}_magazine.txt`（Task 4）、`logs/metrics/{ds}.json` の `followers`（Task 2）
- Produces: `logs/ops/follower_log.jsonl`（1行= `{"date": "YYYY-MM-DD", "followers": N}`）

- [ ] **Step 1: run_list_check.py のチェック項目を置換する**

X前提の4項目（Xプロフィール・X固定ポスト・note末尾登録導線・無料プレゼント受け皿）を以下の4項目に置換する。既存の「Claudeに判定させて結果を保存する」構造・出力先はそのまま使う:

1. **今日の記事がマガジンに入っているか**: `logs/daily/{ds}_magazine.txt` が存在し、`config/magazines.json` にある誌名か
2. **今日の記事末尾にnoteフォローCTAがあるか**: `content/note/{ds}_*.md` の末尾400字に「フォロー」を含むか
3. **プロフィール固定記事が設定されているか**: `docs/funnel_status.md` の該当欄が ✅ か（API確認は初期整備後に手動で✅化し、以後はステータスファイル基準）
4. **フォロワー数の記録**: 当日の `logs/metrics/{ds}.json` から `followers` を読み `logs/ops/follower_log.jsonl` に追記（メトリクス未取得の日はスキップ）。前日比も出力

- [ ] **Step 2: funnel_status.md を全面書き換えする**

以下の構成で書き換える（現行のX前提の6項目を廃棄）:

```markdown
# SODA note導線ステータス

このファイルはnote内の読者獲得導線の設置状況を追跡する。
run_list_check.py が毎日21:15に自動確認する。手動で変更した場合もここを更新すること。

## 方針（2026-08-11 X撤退に伴い全面改訂）

読者獲得はnote内で完結させる。指標はnoteフォロワー数（起点: 5人 / 2026-08-11）。

## 1. マガジン3誌が存在し、毎日の記事が追加されているか
**状態**: 🔧 整備中（初期整備タスクで✅化する）

## 2. note記事末尾にフォローCTAがあるか
**状態**: ✅ 設定済み（2026-08-11〜、writer.md定型文）

## 3. プロフィールがニュースメディアの価値提案になっているか
**状態**: 🔧 整備中（初期整備タスクで✅化する）

## 4. サイトマップ記事が固定表示されているか
**状態**: 🔧 整備中（初期整備タスクで✅化する）
```

- [ ] **Step 3: 検証する**

Run: `python3 scripts/run_list_check.py --dry-run | head -30 && grep -c "Xプロフィール\|X固定\|フォーム\|LINE" scripts/run_list_check.py docs/funnel_status.md; python3 -c "import ast; ast.parse(open('scripts/run_list_check.py').read()); print('OK')"`
Expected: note版4項目のプロンプトが表示、grepは各ファイル0、`OK`

- [ ] **Step 4: コミット**

```bash
git add scripts/run_list_check.py docs/funnel_status.md
git commit -m "導線チェックをnote4項目に書き換え、funnel_statusを全面改訂"
```

---

### Task 7: 初期整備の本実行（バックフィル・プロフィール・サイトマップ記事）

**Files:**
- Create: `content/drafts/sitemap.md`（生成物）
- Modify: `docs/funnel_status.md`（✅化）、`logs/ops/magazine_assignment.json`（生成物、コミットする)

**Interfaces:**
- Consumes: Task 1〜3 の全スクリプト、`scripts/note_post.py`（公開に使用。**事前に `note_post.py` のCLIを読み、スコアなし単発公開の方法を確認する** — CEOスコアファイル前提なら一時スコアファイルを作るか、`--dry-run` で挙動確認してから対応）

- [ ] **Step 1: 既存111本を全量バックフィルする**

Run: `python3 scripts/note_backfill_magazines.py 2>&1 | tail -5`
Expected: `added: 110前後 / failed: 少数 / skipped: Task 3で追加済みの分`。failed があれば `logs/ops/magazine_assignment.json` で確認し、5件以上失敗していたら原因を調べてから再実行（再実行安全）

- [ ] **Step 2: プロフィールを更新する**

Run: `python3 scripts/note_magazine.py --update-profile`
確認: `https://note.com/api/v2/creators/soda_labo` を取得し、profile文言が新文面になっていること

- [ ] **Step 3: サイトマップ記事を生成・公開・固定する**

1. `soda_utils.run_claude` で `content/drafts/sitemap.md` を生成する。プロンプト要件: タイトル「SODAの歩き方 — 毎朝のAIニュース構造解説、どこから読むか」/ SODAの読み方（毎朝1本・構造解説・伏線回収）/ 3誌の紹介（仕様の説明文を使用）/ `logs/metrics/` 最新JSONのビュー上位5記事をリンク付きで紹介（URLは `https://note.com/soda_labo/n/{key}`）/ 末尾にnoteフォローCTA（writer.mdの定型文）/ voice_guide.md 準拠
2. 生成物を目視確認してから `scripts/note_post.py content/drafts/sitemap.md` で公開（note_post.py の公開条件は事前確認どおり対処）
3. 公開されたURLをプロフィールの固定記事に設定（note UIの固定操作をPlaywrightで実行。セレクタは実UI確認で特定。失敗したら手動手順を報告に書いて人に引き継ぐ — ここだけは失敗許容）
4. `docs/funnel_status.md` の項目1・3・4を ✅ に更新（日付入り）

- [ ] **Step 4: 目視検証とスクリーンショット**

Playwrightで `https://note.com/soda_labo` を開き、スクリーンショットを `logs/ops/note_profile_after.png` に保存。確認: 新プロフィール文・マガジン3誌・固定記事（またはサイトマップ記事の存在）

- [ ] **Step 5: コミット**

```bash
git add content/drafts/sitemap.md logs/ops/magazine_assignment.json docs/funnel_status.md logs/ops/note_profile_after.png
git commit -m "初期整備を実行（111本振り分け・プロフィール更新・サイトマップ記事公開）"
```

---

## 実装後の運用検証（翌日）

1. 朝8:07: パイプライン完走後、`logs/daily/{当日}_magazine.txt` が生成され、当日記事が該当マガジンに入っている
2. 21:15: 導線チェックが4項目を評価し、`logs/ops/follower_log.jsonl` に当日行が追記されている
3. 夜22:30: メトリクスJSONに `followers` が入っている

## ユーザーへの申し送り

- noteアカウント設定のTwitter連携解除は手動でお願いする（実装対象外）
