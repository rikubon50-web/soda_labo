# 収益化コンテンツ戦略（曜日モード制）実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** デイリーパイプラインを曜日モード制にし（月〜金=ニュース解説/土=週間構造まとめ/日=運営実録）、第4マガジン・戦略文書・商品トリガー監視を整備する。

**Architecture:** `build_pipeline_prompt(today)` を曜日分岐に改修する。土日は Step 0（ニュース収集）と Step 1.5（取材）を曜日専用の素材読み込み・執筆指示に差し替え、他のStep（企画・執筆・批評・公開・マガジン追加）は共通のまま流す。cron・公開フロー・批評ループは一切変更しない。**平日のプロンプト出力はリファクタ前後でバイト一致させる**（回帰ゼロの保証）。

**Tech Stack:** Python 3（f-stringプロンプト合成）、既存の note_magazine.py / weekly_analysis.py、Playwright（第4誌作成・配信許諾確認のみ）

**Spec:** `docs/superpowers/specs/2026-08-11-monetization-content-design.md`

## Global Constraints

- 全テキスト・コミットメッセージは日本語
- cron・公開フロー・批評ループ（Step 5.5）・CEO推敲（Step 6）・マガジン追加配線は変更しない
- 平日（月〜金）の `build_pipeline_prompt()` 出力は改修前後で**完全一致**させる
- 第4誌の誌名・説明文、戦略文書の内容は仕様の文言をそのまま使う
- **notify_error.py の実発火テスト禁止**（実メール）
- note本番への書き込みは第4誌の作成のみ（`--create-all` は冪等設計済み・仕様承認済み）。配信許諾設定は確認と報告まで（変更が必要なら手動手順としてユーザーに引き継ぐ）
- 並行作業時のgitルール: `git add` は自タスクの成果物のみファイル名指定（`-A`/`.` 禁止）、index.lock エラーは2秒待ち最大3回リトライ

---

### Task 1: 戦略文書 `docs/content_strategy.md` 新設

**Files:**
- Create: `docs/content_strategy.md`

**Interfaces:**
- Produces: パイプライン事前読み込み対象の standing document（Task 2 がパスを参照する）

- [ ] **Step 1: ファイルを作成する**

以下の内容で作成する:

```markdown
# SODA コンテンツ戦略（2026-08-11版）

CEO・Plannerは毎朝これを読む。戦略の根拠は docs/research/2026-08-11-note-monetization-research.md（実測リサーチ）。

## 曜日編成

| 曜日 | コンテンツ | 役割 |
|------|-----------|------|
| 月〜金 | ニュース構造解説 | 習慣・信頼・素材製造。成長ドライバーとは見なさない |
| 土 | 今週のAI構造まとめ | 成長面。週次編集+論点見出し（実測で確認された唯一の勝ち型） |
| 日 | SODA運営実録 | 収益化の本体。数字+変更理由+読者向け再現手順の三点セット |

## 戦略の要点（リサーチ結論）

- 日次ニュース更新は伸びない（137日連続更新でフォロワー24人の実例）。noteの公式アルゴリズムは「一次性・独自性・検証可能性」を優先し、AI生成ニュースは優先度が低い
- SODAの武器は検証可能性: 全ログ・全コード・全プロンプトが実在する。実録ジャンルの「話半分」問題への完全な反証になる
- 実録は数字の垂れ流し禁止。毎回「読者が真似できる再現手順」で締める

## 商品ロードマップ（数字トリガー制）

| トリガー | 商品 | 価格 |
|---------|------|------|
| フォロワー50人 or 実録記事が週300ビュー | 有料note第1弾「SODAを作った全手順+プロンプト実物」 | ¥300〜500 |
| 第1弾が10部 | 第2弾（テンプレ・仕組み深掘り） | ¥980 |
| フォロワー300人 | メンバーシップ（実録の裏側・意思決定ログ） | 月¥500 |

トリガー到達は weekly_analysis が検知して報告する。到達前に商品を出さない（早すぎる商品化はゼロ売上で終わる）。

## 検証と見直し

- 週次: 土日記事のビューが平日記事を上回るかを比較（weekly_analysis）
- 2026-11月中旬: 実録が反応ゼロなら戦略ごと見直す

## 手動運用メモ

- noteのお題企画・コンテスト（note.com/contests）を月1でチェックし、合うものがあれば土曜まとめ記事のタグで相乗りする
```

- [ ] **Step 2: 検証**

Run: `grep -c "曜日編成\|商品ロードマップ\|三点セット" docs/content_strategy.md`
Expected: `3`

- [ ] **Step 3: コミット**

```bash
git add docs/content_strategy.md
git commit -m "コンテンツ戦略文書を新設（曜日編成・商品トリガー・検証基準）"
```

---

### Task 2: `build_pipeline_prompt()` の曜日モード化

**Files:**
- Modify: `src/pipelines/daily_pipeline.py`（`build_pipeline_prompt()` のみ。main()は変更しない）

**Interfaces:**
- Consumes: `docs/content_strategy.md`（Task 1）、第4誌名「SODA運営実録 — AI全自動メディアの数字と中身」（Task 4 と一致必須）
- Produces: 曜日分岐プロンプト。`today.weekday()` 5=土曜、6=日曜

- [ ] **Step 0: 改修前の平日プロンプトを保存する（回帰基準）**

```bash
cd /Users/rikubon50/Desktop/SODA_LABO && python3 -c "
import sys; sys.path.insert(0,'.')
from datetime import date
from src.pipelines.daily_pipeline import build_pipeline_prompt
open('/tmp/prompt_weekday_before.txt','w').write(build_pipeline_prompt(date(2026,8,13)))
print('saved')"
```

- [ ] **Step 1: 事前読み込みリストに戦略文書を追加する（全曜日共通）**

`8. docs/perspectives.md — ...` の行の直後に追加:

```
9. docs/content_strategy.md — コンテンツ戦略（CEOとPlannerは曜日編成と商品トリガーを把握すること）
```

注意: これは平日出力も変えるため、Step 0 の回帰基準はこの行を除いた比較にする（Step 6 参照）。

- [ ] **Step 2: 曜日分岐の構造を入れる**

`build_pipeline_prompt()` 冒頭に `wd = today.weekday()` を追加し、Step 0 と Step 1.5 のブロックを変数化する（現行文字列を `step0_news` / `step15_research` として抽出し、平日はそのまま使用）。土日はそれぞれ以下に差し替え、Step 1（CEO）・Step 4（Writer）に曜日専用の追記を挿入する。

**土曜（wd == 5）の Step 0 差し替え（`step0` 変数）:**

```
## Step 0: 今週の記事の読み込み（土曜まとめモード）
本日は「今週のAI構造まとめ」の日。ニュース収集は行わない。
代わりに、今週月曜から金曜までの自分のnote記事（content/note/ の当週分5本）をすべてRead toolで読み込む。
各記事の公開URLは logs/daily/ の当週の *_note_url.txt から取得してメモすること（まとめ記事内の内部リンクに使う）。
```

**土曜の Step 1 追記（CEO指示の直後に挿入）:**

```
**本日は土曜まとめモード。個別ニュースの再掲ではなく、今週の5本を貫く「1週間の論点」を1つ立てること（例:「◯◯と◯◯が同時に動いた1週間」型の編集見出し）。docs/perspectives.md の仮説がこの1週間でどう動いたかも論点候補にする。**
```

**土曜の Step 4 追記（Writer指示の直後に挿入）:**

```
**土曜まとめ記事の要件: タイトルに週の論点を立てる（個別ニュース名の羅列にしない）/ 今週の各記事への内部リンクをStep 0で取得したURLで張る / perspectives.md の伏線の進捗に触れる / 記事冒頭に約50字のリード文を置く。**
```

**日曜（wd == 6）の Step 0 差し替え:**

```
## Step 0: 運営データの読み込み（日曜実録モード）
本日は「SODA運営実録」の日。ニュース収集は行わない。代わりに以下を読み込む。
1. logs/ops/follower_log.jsonl — フォロワー推移（今週分と前週比）
2. logs/metrics/ の当週分JSON — 記事別ビュー・スキ（当週各記事の読まれ方）
3. logs/daily/ の当週分 *_post_analysis.md — 日次分析の結論
4. Bash toolで `git log --oneline --since="7 days ago"` を実行 — 今週システムに入った変更の一覧
```

**日曜の Step 1 追記:**

```
**本日は日曜実録モード。テーマは「今週のSODA運営で何が起き、何を変え、読者は何を真似できるか」。docs/content_strategy.md の三点セット構成（①今週の数字 ②何を変えたか・なぜか ③読者が真似する場合の再現手順）を必ず守ること。数字は良くても悪くても正直に書く。**
```

**日曜の Step 4 追記:**

```
**日曜実録記事の要件: 三点セット構成（数字→変更と理由→読者向け再現手順）を見出しで明示する / 数字には出どころ（自動収集の仕組み）を一言添える / 検証できない主張・誇張をしない / 数字の羅列だけで終わらせず、必ず「読者が自分の発信・AI活用に適用する具体手順」で締める / 記事冒頭に約50字のリード文を置く。**
```

**日曜の Step 7.6 差し替え（マガジン判定）:**

```
## Step 7.6: 本日記事のマガジン判定
本日は実録記事のため、判定不要。logs/daily/{ds}_magazine.txt に「SODA運営実録 — AI全自動メディアの数字と中身」と1行保存する。
```

土曜の Step 1.5（取材）はスキップ（`step15 = ""`）。日曜も同様。平日は現行の Step 1.5 をそのまま使う。

- [ ] **Step 3: 検証（平日回帰+土日分岐）**

```bash
cd /Users/rikubon50/Desktop/SODA_LABO && python3 -c "
import sys; sys.path.insert(0,'.')
from datetime import date
from src.pipelines.daily_pipeline import build_pipeline_prompt
# 平日回帰: 戦略文書の1行を除けば改修前とバイト一致
after = build_pipeline_prompt(date(2026,8,13))
before = open('/tmp/prompt_weekday_before.txt').read()
after_stripped = '\n'.join(l for l in after.split('\n') if 'content_strategy.md' not in l)
assert after_stripped == before, '平日プロンプトが回帰基準と不一致'
# 土曜
sat = build_pipeline_prompt(date(2026,8,15))
assert '土曜まとめモード' in sat and '1週間の論点' in sat and 'AI news today' not in sat and 'Step 1.5' not in sat
# 日曜
sun = build_pipeline_prompt(date(2026,8,16))
assert '日曜実録モード' in sun and '三点セット' in sun and 'follower_log' in sun and 'SODA運営実録 — AI全自動メディアの数字と中身' in sun and 'AI news today' not in sun
# 共通Step健在
for p in (sat, sun):
    assert 'Step 5.5' in p and 'Step 7.5' in p and '全体ルール' in p
print('OK')"
```

Expected: `OK`

- [ ] **Step 4: コミット**

```bash
git add src/pipelines/daily_pipeline.py
git commit -m "パイプラインを曜日モード制に（土=週間まとめ・日=運営実録）"
```

---

### Task 3: writer.md リード文ルールと voice_guide.md 実録禁止事項

**Files:**
- Modify: `agents/writer.md`（「執筆ルール」セクションに1行追加）
- Modify: `docs/voice_guide.md`（末尾にセクション追加）

- [ ] **Step 1: writer.md に追加する**

「## 執筆ルール」の箇条書きに1行追加:

```
- 記事冒頭に約50字のリード文を置く（note公式推奨。レコメンドやSNS表示で本文冒頭が要約として使われるため）
```

- [ ] **Step 2: voice_guide.md 末尾に追加する**

```markdown
---

## 実録記事（日曜）の追加ルール

- 数字の羅列だけで終わらせない。必ず「読者が真似する場合の再現手順」で締める
- 検証できない主張・誇張・水増し表現をしない。数字には出どころ（自動収集の仕組み）を一言添える
- 停滞・失敗も正直に書く。悪い数字を隠した実録は一度で信頼を失う
```

- [ ] **Step 3: 検証**

Run: `grep -c "リード文" agents/writer.md && grep -c "実録記事（日曜）" docs/voice_guide.md`
Expected: `1` と `1`

- [ ] **Step 4: コミット**

```bash
git add agents/writer.md docs/voice_guide.md
git commit -m "リード文ルールと実録記事の文体ルールを追加"
```

---

### Task 4: 第4マガジン「SODA運営実録」の作成

**Files:**
- Modify: `scripts/note_magazine.py`（MAGAZINES 定数に1誌追加）
- Modify: `config/magazines.json`（--create-all 実行で自動更新される）

**Interfaces:**
- Produces: 第4誌の誌名「SODA運営実録 — AI全自動メディアの数字と中身」が config/magazines.json に登録される（Task 2 の Step 7.6 と一字一句一致すること）

- [ ] **Step 1: MAGAZINES に追加する**

`scripts/note_magazine.py` の MAGAZINES 辞書に追加:

```python
    "SODA運営実録 — AI全自動メディアの数字と中身": "フォロワー5人から始めたAI全自動メディアの運営数字・変更・再現手順を毎週日曜に公開。全ログ実在・全て検証可能。",
```

- [ ] **Step 2: dry-run → 本実行（既存3誌は冪等スキップされる）**

Run: `python3 scripts/note_magazine.py --create-all --dry-run`（新規1誌のみ作成予定と表示されること）→ `python3 scripts/note_magazine.py --create-all && python3 -c "import json; d=json.load(open('config/magazines.json')); assert len(d)==4 and 'SODA運営実録 — AI全自動メディアの数字と中身' in d; print('OK 4誌')"`
Expected: `OK 4誌`。`https://note.com/api/v2/creators/soda_labo` で `magazineCount: 4` も確認

- [ ] **Step 3: コミット**

```bash
git add scripts/note_magazine.py config/magazines.json
git commit -m "第4マガジン「SODA運営実録」を追加・作成"
```

---

### Task 5: weekly_analysis のトリガー監視と土日/平日ビュー比較

**Files:**
- Modify: `scripts/weekly_analysis.py`

**Interfaces:**
- Consumes: `logs/ops/follower_log.jsonl`（`{"date","followers"}` 行形式）、`logs/metrics/` の note形式JSON、`logs/daily/*_magazine.txt`（曜日判定の補助）

- [ ] **Step 1: プロンプトに分析観点を2つ追加する**

weekly_analysis のプロンプト（分析指示部）に追加:

```
- 土日記事（週間まとめ・運営実録）と平日記事のビュー・スキを比較し、戦略仮説（土日型が平日型を上回る）が成立しているか判定すること
- 商品化トリガーの判定: follower_log.jsonl の最新フォロワー数が50以上、または日曜実録記事の週間ビューが300以上なら、分析結果の冒頭に「★商品化トリガー到達」と明記し、docs/content_strategy.md の商品ロードマップ第1弾の準備を提案すること
```

データ組み立て部に follower_log.jsonl の直近8行（存在すれば）を「### フォロワー推移」として追加する（既存のnoteメトリクス組み立てと同じ流儀で。ファイル欠如時はスキップ）。

- [ ] **Step 2: 検証**

Run: `python3 scripts/weekly_analysis.py --dry-run 2>/dev/null | grep -c "商品化トリガー\|フォロワー推移\|土日"; python3 -c "import ast; ast.parse(open('scripts/weekly_analysis.py').read()); print('OK')"`
Expected: `2以上` と `OK`

- [ ] **Step 3: コミット**

```bash
git add scripts/weekly_analysis.py
git commit -m "週次分析に商品化トリガー監視と土日/平日比較を追加"
```

---

### Task 6: 外部配信許諾の確認と最終検証

**Files:**
- 変更なし（設定確認とレポートのみ。必要ならユーザーへの手動手順を残す）

- [ ] **Step 1: noteの配信許諾設定を確認する**

Playwright（`.browser_profile/note`、`note_metrics.py` の起動パターン）で `https://note.com/settings` 配下を探索し、外部配信（SmartNews・LINE NEWS等への配信許諾）の設定項目と現在値を確認する。スクリーンショットを `logs/ops/note_syndication_setting.png` に保存。**設定がOFFでも自動で変更しない** — 項目の場所と現在値をレポートに記録し、ONにする手動手順を書く（設定変更はユーザー判断）。項目が見つからない場合は「該当設定なし（noteの仕様変更の可能性）」と記録

- [ ] **Step 2: 全体の最終検証**

Task 2 の Step 3 検証スクリプトを再実行し `OK`。さらに `python3 scripts/note_magazine.py --add-today --dry-run` が正常（4誌構成で判定が動く）ことを確認

- [ ] **Step 3: コミット（スクリーンショットのみ）**

```bash
git add logs/ops/note_syndication_setting.png
git commit -m "外部配信許諾設定の現状を記録"
```

---

## 実装後の運用検証

1. **8/15（土）朝8:07**: 週間まとめ記事が論点見出し+内部リンク付きで公開され、内容主題の誌に追加される
2. **8/16（日）朝8:07**: 実録記事が三点セット構成で公開され、第4誌に追加される
3. **8/16（日）21:30**: weekly_analysis が土日/平日比較とトリガー判定を出力する
