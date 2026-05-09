# X グロース戦略再設計 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** X×note 並走モデル（X=ニュース速報3本/日×構造解説型、note=AI×お金・雇用・構造転換の深掘り1本/日）への運用切り替えに必要なシステム改修を実装する。

**Architecture:** 既存の Claude パイプライン（`src/pipelines/daily_pipeline.py`）が agents/*.md のプロンプトに従って Writer・Editor・CEO を呼び出す構造を維持したまま、(1) writer/ceo の運用方針を v2 に更新、(2) パイプラインプロンプトの X 投稿前提を「3本=別ニュース×構造解説型」に切り替え、(3) `x_post.py` の夜投稿に note CTA 自動付与を組み込む、(4) 戦略ドキュメントとパターン蓄積を更新する。AItsm/Day N の生成系は新規生成停止する（既存ファイルは凍結）。

**Tech Stack:** Python 3 / tweepy（X API） / Claude Code パイプライン / Markdown ベースの agent prompt

設計書: `docs/superpowers/specs/2026-05-09-x-news-redesign-design.md`

---

## File Structure

| 種別 | パス | 役割 |
|------|------|------|
| 修正 | `agents/writer.md` | X 投稿の構造解説型テンプレートを正式化、Day N／AItsm 関連の旧ルールを削除 |
| 修正 | `agents/ceo.md` | テーマ方針を「ニュース解説一本化」に統一、Day N 補完・AItsm 関連を削除 |
| 修正 | `src/pipelines/daily_pipeline.py` | Step 4 プロンプトを「X=3本×別ニュース×構造解説型」「note=毎日1本×3テーマ深掘り」「AItsm/Day N 廃止」に変更 |
| 修正 | `scripts/x_post.py` | 夜投稿（post_number==3）で note CTA を自動付与（既存 `append_note_url` を `post_one` から呼ぶ） |
| 修正 | `docs/x_strategy.md` | 役割分担と投稿型を v2 に書き換え、リプライ戦略の節を削除 |
| 修正 | `audience/winning_topics.md` | 「構造解説型 X 投稿（朝・昼・夜）」を確定パターンとして追記 |
| 新規 | `content/drafts/_FROZEN.md` | AItsm／Day N テンプレートが凍結されたことを示す README |

---

## Task 1: writer.md を構造解説型に書き換え

**Files:**
- Modify: `agents/writer.md`

- [ ] **Step 1: writer.md の X 投稿セクション全体を差し替える**

`agents/writer.md` の以下の範囲を新版に書き換える：
- 「## X投稿のフォーマット」セクション全体（旧：朝＝主張型／昼＝気づき／夜＝長文）
- 「## X投稿 ニュース解説モード」セクション全体（旧：朝＝予告／昼＝構造解説／夜＝示唆）
- 「## Day Nシリーズの構成（追加）」セクション（廃止）

新たに以下を書く：

```markdown
## X投稿のフォーマット（構造解説型 / 標準）

X 投稿は1日3本・独立投稿。各投稿は単体で完結させる（連結禁止）。
朝・昼・夜でそれぞれ別の AI ニュースを取り上げ、すべて以下の構造解説型テンプレートで書く。

### 構造解説型テンプレート

```
[1] ニュースの事実を1〜2文で提示（数字＋主体を必ず含める）
[2] 「なぜか」「これは何の話か」を箇条書き2〜4点で構造化
[3] 一行で示唆（読者が考えたくなる形で締める）
```

### 例

```
AnthropicがOpenAIのARRを抜いた。$30B対$24B。

なぜか。性能勝負ではなく、選ばれる基準が変わった。
・大企業：安全性・コンプラ適合性
・個人：速度・UX

軸が分かれた瞬間、ChatGPTの先行優位は通用しなくなった。
```

### 朝・昼・夜の使い分け

- 朝：その日の AI ニュース1本目（速報性重視のもの）
- 昼：その日の AI ニュース2本目（朝とは別のニュース）
- 夜：当日の note 記事と同一ニュース（同じ構造解説型ショート版で書く。X 単独でも完結。`x_post.py` 側で note CTA が自動付与されるため、Writer は note URL を本文に書かない）

### ルール

- 文字数：140〜400字
- 外部 URL は基本貼らない。本文中に出典名を文字列で明記する（例：`— CNBC報道` `— Anthropic公式`）
- 例外：note 格上げ対象（資金・雇用・構造転換）に該当するニュースは週1〜2回までソース URL を本文末尾に付けてよい
- 単独完結を絶対条件にする：他の投稿に依存する文脈（「今朝の続き」「昼に整理する」など）禁止
- 内輪表現禁止：「Day N」「うちの AI 社員」「実験ログ」など初見不明語を使わない
- 結論を投稿内に必ず置く。「続きはあとで」「note に書く」だけの予告型は禁止
- ハッシュタグは引き続き禁止（既存ルール踏襲）
```

旧「## X投稿 ニュース解説モード」「## Day Nシリーズの構成（追加）」は削除する。

- [ ] **Step 2: writer.md の note 記事方針を「ニュース解説一本化」に更新**

`agents/writer.md` の「## note記事の構成」セクションの直後に以下を追記する（既存 Day N シリーズ用構成は削除済みのため、note は新ルールで一本化）：

```markdown
## note記事のジャンル方針（2026-05-09 v2）

note は毎日1本、「AI×お金・雇用・構造転換」の3テーマに該当するニュース解説のみを書く。

該当基準：
- 大型投資・合弁・M&A
- 大規模レイオフ × AI 活用
- 業界構造の転換（A だったものが B に変わる）
- 競合複数社が同週に同方向に動いた

該当ニュースが当日にない場合は、過去3〜7日のニュースから「今振り返ると」型で1本選ぶ（スロー日対策）。

AI それって本当？／Day N シリーズは新規制作停止。
```

- [ ] **Step 3: writer.md の差分を確認**

Run: `git diff agents/writer.md | head -100`
Expected: X 投稿セクションが構造解説型に置き換わっており、Day N／AItsm 関連が消えている。

- [ ] **Step 4: Commit**

```bash
git add agents/writer.md
git commit -m "feat(writer): X投稿を構造解説型に一本化、note を3テーマ深掘りに統一"
```

---

## Task 2: ceo.md のテーマ方針を更新

**Files:**
- Modify: `agents/ceo.md`

- [ ] **Step 1: テーマ方針セクションを書き換える**

`agents/ceo.md` の「## テーマ方針（2026-05-07 更新）」セクション全体を以下に置き換える：

```markdown
## テーマ方針（2026-05-09 v2）

**X = ニュース速報×構造解説（1日3本）／note = AI×お金・雇用・構造転換の深掘り（毎日1本）の並走運用。**

優先順位：
1. **note：3テーマ該当ニュースの深掘り（毎日1本）**
   - 該当基準：大型投資・合弁・M&A／大規模レイオフ×AI活用／業界構造の転換／競合複数社の同週同方向の動き
   - 当日にニュースがなければ過去3〜7日から「今振り返る」型で1本選ぶ
2. **X：AI ニュース全般から3本（朝・昼・夜）**
   - 朝・昼は別の2ニュース
   - 夜は当日 note と同一ニュース（X 単独完結、CTA は x_post.py 側で自動付与）
   - 全3本とも構造解説型テンプレに従う

詳細は `docs/x_strategy.md` および `audience/winning_topics.md` を参照。

「AI それって本当？」シリーズおよび Day N シリーズは新規制作停止（X・note 両方）。既存ファイルは参照可だが新規生成しない。
```

- [ ] **Step 2: ceo.md の Day N 継続判断セクションを削除**

`agents/ceo.md` の「## Day Nシリーズの継続判断」セクション全体を削除する。

- [ ] **Step 3: 差分確認**

Run: `git diff agents/ceo.md`
Expected: テーマ方針が v2 に書き換わり、Day N 継続判断セクションが消えている。

- [ ] **Step 4: Commit**

```bash
git add agents/ceo.md
git commit -m "feat(ceo): テーマ方針を X×note 並走モデル v2 に更新"
```

---

## Task 3: x_post.py の夜投稿に note CTA を自動付与

**Files:**
- Modify: `scripts/x_post.py:110-138`

現状 `append_note_url` 関数と `load_note_url` 関数は定義されているが `post_one` から呼ばれていない。これを夜投稿（post_number==3）のときだけ自動付与するよう wire up する。

- [ ] **Step 1: post_one を修正して夜投稿で note CTA を付ける**

`scripts/x_post.py` の `post_one` 関数の以下の行：

```python
def post_one(filepath: str, post_number: int, dry_run: bool = False) -> None:
    posts_and_tags = parse_posts_and_tags(filepath)

    if post_number < 1 or post_number > len(posts_and_tags):
        print(f"エラー: {post_number}本目が存在しません（全{len(posts_and_tags)}本）")
        sys.exit(1)

    content, hashtags = posts_and_tags[post_number - 1]
    label = ["朝", "昼", "夜"][post_number - 1] if post_number <= 3 else str(post_number)

    post = build_post_text(content, hashtags)
```

の最後の行（`post = build_post_text(content, hashtags)`）の直後に以下を追加する：

```python
    # 夜投稿（3本目）のみ note CTA を自動付与
    if post_number == 3:
        note_url = load_note_url()
        if note_url:
            post = append_note_url(post, note_url)
```

- [ ] **Step 2: dry-run でCTAなし（note URL ファイル無し）の挙動を確認**

Run:
```bash
rm -f /Users/rikubon50/Desktop/SODA_LABO/logs/daily/$(date +%Y-%m-%d)_note_url.txt
python3 /Users/rikubon50/Desktop/SODA_LABO/scripts/x_post.py /Users/rikubon50/Desktop/SODA_LABO/content/x_posts/2026-05-09_anthropic-arr.md --post 3 --dry-run
```

Expected: 夜投稿の本文末尾に「note→」が含まれない（URL 未設定なので付かない）。

- [ ] **Step 3: dry-run で CTA あり（note URL ファイルあり）の挙動を確認**

Run:
```bash
echo "https://note.com/sodalabo/n/test123" > /Users/rikubon50/Desktop/SODA_LABO/logs/daily/$(date +%Y-%m-%d)_note_url.txt
python3 /Users/rikubon50/Desktop/SODA_LABO/scripts/x_post.py /Users/rikubon50/Desktop/SODA_LABO/content/x_posts/2026-05-09_anthropic-arr.md --post 3 --dry-run
```

Expected: 夜投稿の本文末尾に `note→ https://note.com/sodalabo/n/test123` が付く。文字数が140＋note URL分を超える場合は本文117字に切り詰められる（`append_note_url` の既存仕様）。

- [ ] **Step 4: dry-run で朝・昼に CTA が付かないことを確認**

Run:
```bash
python3 /Users/rikubon50/Desktop/SODA_LABO/scripts/x_post.py /Users/rikubon50/Desktop/SODA_LABO/content/x_posts/2026-05-09_anthropic-arr.md --post 1 --dry-run
python3 /Users/rikubon50/Desktop/SODA_LABO/scripts/x_post.py /Users/rikubon50/Desktop/SODA_LABO/content/x_posts/2026-05-09_anthropic-arr.md --post 2 --dry-run
```

Expected: どちらも本文に `note→` が含まれない（朝・昼は CTA 対象外）。

- [ ] **Step 5: テスト用ファイルをクリーンアップ**

Run:
```bash
rm -f /Users/rikubon50/Desktop/SODA_LABO/logs/daily/$(date +%Y-%m-%d)_note_url.txt
```

- [ ] **Step 6: Commit**

```bash
git add scripts/x_post.py
git commit -m "feat(x_post): 夜投稿に note CTA を自動付与"
```

---

## Task 4: daily_pipeline.py のプロンプトを新運用に揃える

**Files:**
- Modify: `src/pipelines/daily_pipeline.py:39-132`

`build_pipeline_prompt` の Step 4 セクションが Day N／AItsm 前提のテンプレ参照を含んでいるため、新運用に合わせて書き換える。

- [ ] **Step 1: Step 4 セクションを書き換える**

`src/pipelines/daily_pipeline.py` の `build_pipeline_prompt` 関数内、Step 4 セクション：

```
## Step 4: Writer — 下書き制作
agents/writer.md を読み、採用企画をもとに以下を下書きしてファイルに保存する。
**昨日の投稿分析（post_analysis）で反応が高かった表現・フック・構成を参考にすること。**
**アイデア資産（ideas）に使えるネタ・切り口があれば積極的に取り込むこと。**
**朝会議ログのWriterへの指示がある場合は必ず従うこと。**
- note記事 → content/note/{ds}_[タイトル略称].md
  （Day Nシリーズなら content/drafts/template_day-n_note.md を参照）
  note記事の末尾に agents/writer.md の「note記事ハッシュタグルール」に従い #タグ を5つ付与する。
- X投稿3本 → content/x_posts/{ds}_[テーマ略称].md
  （Day Nシリーズなら content/drafts/template_day-n_x.md を参照）
  朝・昼は140字以内。ハッシュタグ・外部リンクは入れない。
  夜（3本目）はagents/writer.md の「夜（長文投稿）の構成」に従い500〜1500字の長文で書く。note記事の核心をX上で完結させること。外部リンク不要。
- 短尺動画台本 → content/short_videos/{ds}_[タイトル略称].md
  （Day Nシリーズなら content/drafts/template_day-n_video.md を参照）
```

を以下に置き換える：

```
## Step 4: Writer — 下書き制作
agents/writer.md を読み、採用企画をもとに以下を下書きしてファイルに保存する。
**昨日の投稿分析（post_analysis）で反応が高かった表現・フック・構成を参考にすること。**
**アイデア資産（ideas）に使えるネタ・切り口があれば積極的に取り込むこと。**
**朝会議ログのWriterへの指示がある場合は必ず従うこと。**

- note記事 → content/note/{ds}_[タイトル略称].md
  「AI×お金・雇用・構造転換」3テーマ該当ニュースの深掘り1本（agents/writer.md「note記事のジャンル方針」参照）。
  該当ニュースが当日になければ過去3〜7日から「今振り返ると」型で1本選ぶ。
  記事末尾に agents/writer.md の「note記事ハッシュタグルール」に従い #タグ を5つ付与する。

- X投稿3本 → content/x_posts/{ds}_[テーマ略称].md
  3本とも構造解説型テンプレート（agents/writer.md「X投稿のフォーマット（構造解説型 / 標準）」）で書く。
  朝・昼・夜でそれぞれ別の AI ニュースを取り上げる（連結禁止・各投稿は単独完結）。
  夜（3本目）は当日 note と同一ニュースを構造解説型ショート版で扱う。note URL は本文に書かない（x_post.py が自動付与）。
  全3本：140〜400字、ハッシュタグ禁止、外部 URL は本文中に出典名で代替（例外：3テーマ該当ニュースは週1〜2回まで URL 可）。

- 短尺動画台本 → content/short_videos/{ds}_[タイトル略称].md
  当日 note 記事と同じニュースを冒頭3秒インパクト型で 30〜45秒に圧縮。

AI それって本当？／Day N シリーズは新規生成しない。
```

- [ ] **Step 2: Step 1 セクションから Day N 言及を削除**

`build_pipeline_prompt` の Step 1：

```
## Step 1: CEO — 本日の優先テーマ決定
agents/ceo.md を読み、CEOとして本日の優先テーマを決定する。
**Step 0で取得した最新ニュースがある場合は、それを最優先のテーマ候補として検討すること。**
**朝会議ログ（logs/meeting/{ds}_meeting.md）のCEO最終判断・Writerへの指示を最優先で参照すること。**
content/note/ の直近ファイルを確認してDay Nシリーズの継続判断を行う。
出力形式: agents/ceo.md の「優先テーマを出すとき」フォーマット。
```

を以下に置き換える：

```
## Step 1: CEO — 本日の優先テーマ決定
agents/ceo.md を読み、CEOとして本日の優先テーマを決定する。
**Step 0で取得した最新ニュースから「AI×お金・雇用・構造転換」3テーマに該当するもの1本を最優先のテーマ候補として選ぶこと（基準は agents/ceo.md「テーマ方針」参照）。**
**該当ニュースがない場合は過去3〜7日から「今振り返ると」型で1本選ぶ。**
**朝会議ログ（logs/meeting/{ds}_meeting.md）のCEO最終判断・Writerへの指示を最優先で参照すること。**
出力形式: agents/ceo.md の「優先テーマを出すとき」フォーマット。
```

- [ ] **Step 3: 差分確認**

Run: `git diff src/pipelines/daily_pipeline.py | head -120`
Expected: Step 1・Step 4 が新運用に書き換わり、Day N テンプレ参照が消えている。

- [ ] **Step 4: Commit**

```bash
git add src/pipelines/daily_pipeline.py
git commit -m "feat(pipeline): プロンプトを X×note 並走モデル v2 に更新"
```

---

## Task 5: docs/x_strategy.md を v2 に書き換え

**Files:**
- Modify: `docs/x_strategy.md`

- [ ] **Step 1: x_strategy.md を全面書き換え**

`docs/x_strategy.md` の内容を以下で完全置換する：

```markdown
# SODA_LABO X投稿戦略 v2

最終更新：2026-05-09

詳細設計：`docs/superpowers/specs/2026-05-09-x-news-redesign-design.md`

---

## アカウントの立ち位置

「AI ニュース全般を、SODA_LABO の構造解説型でカバーするアカウント」。
note とは並走運用：X はニュース速報×構造解説（速度・量・幅）、note は AI×お金・雇用・構造転換の深掘り（深さ・保存価値）。

---

## 投稿の構造（1日3本）

| スロット | 内容 |
|---------|------|
| 朝 | AI ニュース1本目（その日の速報性重視のもの） |
| 昼 | AI ニュース2本目（朝とは別のニュース） |
| 夜 | 当日 note 記事と同一ニュースの構造解説型ショート版（CTA は x_post.py が自動付与） |

3本とも構造解説型テンプレートで書く。連結禁止（各投稿は単独完結）。

---

## 構造解説型テンプレート

```
[1] ニュースの事実を1〜2文で提示（数字＋主体を必ず含める）
[2] 「なぜか」「これは何の話か」を箇条書き2〜4点で構造化
[3] 一行で示唆（読者が考えたくなる形で締める）
```

### 良い投稿例

```
AnthropicがOpenAIのARRを抜いた。$30B対$24B。

なぜか。性能勝負ではなく、選ばれる基準が変わった。
・大企業：安全性・コンプラ適合性
・個人：速度・UX

軸が分かれた瞬間、ChatGPTの先行優位は通用しなくなった。
```

### 悪い投稿例

```
今日の昼にAnthropicの話を整理する。
ソース：https://example.com
```
→ 単独完結していない・予告型・本文に解釈なし。

---

## ルール

- 文字数：140〜400字
- ハッシュタグ禁止
- 外部 URL は基本貼らない。本文中に出典名を文字列で明記（例：`— CNBC報道`）
  - 例外：3テーマ該当ニュースは週1〜2回まで URL 可
- 単独完結を絶対条件にする（「今朝の続き」「昼に整理する」などの予告型禁止）
- 内輪表現禁止：「Day N」「うちのAI社員」「実験ログ」など初見不明語禁止
- 結論を投稿内に必ず置く

---

## スロー日対策（優先順位ルール）

質 > 本数 を絶対の優先順位として、以下の順番で代替策を取る：

| 段階 | 対応 |
|------|------|
| A | 当日の新規ニュースが3つ揃わない場合 → 過去3〜7日のニュースを「新しい角度」で構造解説し直す（同一ニュースの再投稿は NG） |
| B | 過去ニュースでも届かない場合 → 過去1ヶ月の重要ニュースを「今振り返ると」型で再解釈 |
| C | それでも厳しい場合 → 本数を 2本／1本に落とす（最低1本/日は死守） |

ネタ不足で Day 記録・雑記・予告型に逃げることは禁止。

---

## KPI と振り返り

### KPI 構成

| 区分 | 指標 | 目標 |
|------|------|------|
| 結果系 | 1投稿平均 IMP | 4週後 20+（現状≈3） |
| 結果系 | フォロワー増減 | 4週後 +10〜30 |
| 結果系 | note 誘導日のフォーム到達数 | 4週後 累計 5+ |
| プロセス系 | 型遵守率（構造解説型テンプレ準拠） | 90%以上 |
| プロセス系 | 投稿本数達成率（スロー日対策C順守を含む） | 90%以上 |
| プロセス系 | 禁止表現混入率（予告型・Day記録・内輪語） | 0件/週 |

### 振り返りタイミング

- 5/17（1週後）：プロセス確認のみ。型遵守率・本数達成率・禁止表現混入の点検。IMP は参考値。
- 6/7（4週後）：KPI 本評価。打ち手の方向修正判断。

---

## ニュース情報源

### 毎日チェック

| 媒体 | URL | 特徴 |
|------|-----|------|
| Ledge.ai | https://ledge.ai/ | 日本最大級 AI ニュース |
| @masahirochaen (X) | x.com/masahirochaen | 重要 AI ニュース毎日最速 |
| @sora19ai (X) | x.com/sora19ai | AI エージェント・自動化実務 |
| TechCrunch AI | techcrunch.com/category/artificial-intelligence | 英語・速報 |

ニュース供給は `src/pipelines/daily_pipeline.py` の Step 0（WebSearch）で自動収集される。
```

- [ ] **Step 2: Commit**

```bash
git add docs/x_strategy.md
git commit -m "docs: x_strategy を v2（X×note 並走モデル）に書き換え"
```

---

## Task 6: winning_topics.md に構造解説型 X 投稿パターンを追記

**Files:**
- Modify: `audience/winning_topics.md`

- [ ] **Step 1: 確定勝ちパターンセクションに X 用パターンを追記**

`audience/winning_topics.md` の「## 確定勝ちパターン（2026-05-07 確定）」の見出しを「## 確定勝ちパターン」に変更し、その直下（既存の note 解説本文の前）に以下のセクションを追記する：

```markdown
### X 投稿（2026-05-09 確定）：構造解説型

5/07 昼の Anthropic-Blackstone 投稿（35 IMP、1日内最高）から確定。**X の標準テンプレートとして固定**。

#### テンプレート

```
[1] ニュースの事実を1〜2文で提示（数字＋主体を必ず含める）
[2] 「なぜか」「これは何の話か」を箇条書き2〜4点で構造化
[3] 一行で示唆（読者が考えたくなる形で締める）
```

#### なぜ刺さるか

1. 数字＋主体で1行目に強い具体性（読者の足を止める）
2. 箇条書きで「なぜ」を可読化（読み飛ばしても核が掴める）
3. 一行示唆で読者に問いを残す（保存・引用されやすい）

#### 適用ルール

- 文字数：140〜400字
- 朝・昼・夜の3本ともこの型で書く
- 夜は当日 note と同一ニュース（CTA は `scripts/x_post.py` が自動付与）

詳細：`docs/x_strategy.md` および `docs/superpowers/specs/2026-05-09-x-news-redesign-design.md`

---
```

既存の「### ジャンル：「AI×お金・雇用・構造転換」ニュース解説」以下の note 用記述はそのまま残す。

- [ ] **Step 2: Commit**

```bash
git add audience/winning_topics.md
git commit -m "docs(winning_topics): X 投稿の構造解説型を確定パターンに追加"
```

---

## Task 7: AItsm／Day N テンプレートの凍結

**Files:**
- Create: `content/drafts/_FROZEN.md`

`content/drafts/template_day-n_*.md` などのテンプレートは削除せず、新規参照を停止する旨を明示する。

- [ ] **Step 1: drafts ディレクトリの内容を確認**

Run: `ls /Users/rikubon50/Desktop/SODA_LABO/content/drafts/`
Expected: `template_day-n_note.md` `template_day-n_x.md` `template_day-n_video.md` などが見える。

- [ ] **Step 2: 凍結 README を作成**

Create `content/drafts/_FROZEN.md` with content:

```markdown
# 凍結済みテンプレート

2026-05-09 以降、以下のテンプレートは新規生成で参照しない（X×note 並走モデル v2 への移行）。

- `template_day-n_note.md`
- `template_day-n_x.md`
- `template_day-n_video.md`
- AI それって本当？関連テンプレート

ファイルは過去ログとして残すが、`src/pipelines/daily_pipeline.py` および `agents/writer.md` からの参照は削除済み。

新運用の方針は以下を参照：
- 設計書：`docs/superpowers/specs/2026-05-09-x-news-redesign-design.md`
- 戦略：`docs/x_strategy.md`
- Writer プロンプト：`agents/writer.md`
```

- [ ] **Step 3: Commit**

```bash
git add content/drafts/_FROZEN.md
git commit -m "docs: 旧テンプレート（Day N／AItsm）の凍結を明示"
```

---

## Task 8: 移行スモークテスト（パイプライン dry-run）

**Files:**
- 変更なし（実行のみ）

- [ ] **Step 1: 明日（5/10）のパイプライン入力素材があるか確認**

Run:
```bash
ls /Users/rikubon50/Desktop/SODA_LABO/content/x_posts/2026-05-10_*.md 2>/dev/null
ls /Users/rikubon50/Desktop/SODA_LABO/content/note/2026-05-10_*.md 2>/dev/null
```

Expected: 両方とも空（本番パイプラインで生成される予定）。もしファイルが既にあれば、移行前の旧運用で生成された可能性があるので内容を確認し、必要なら退避する。

- [ ] **Step 2: x_post.py の引数仕様が壊れていないか確認**

Run:
```bash
python3 /Users/rikubon50/Desktop/SODA_LABO/scripts/x_post.py --help
```

Expected: ヘルプ表示が正常に出る（修正で構文エラーを入れていないかの最終確認）。

- [ ] **Step 3: Python 構文チェック**

Run:
```bash
python3 -m py_compile /Users/rikubon50/Desktop/SODA_LABO/scripts/x_post.py
python3 -m py_compile /Users/rikubon50/Desktop/SODA_LABO/src/pipelines/daily_pipeline.py
echo "compile OK"
```

Expected: `compile OK` が表示される（構文エラーなし）。

- [ ] **Step 4: 既存の 5/09 ファイルで dry-run 全3本表示**

Run:
```bash
python3 /Users/rikubon50/Desktop/SODA_LABO/scripts/x_post.py /Users/rikubon50/Desktop/SODA_LABO/content/x_posts/2026-05-09_anthropic-arr.md --dry-run
```

Expected: 3本それぞれの本文がプリントされる（朝・昼・夜のラベル付き）。`note→` URL は付かない（その日の note URL ファイルが無いため）。

- [ ] **Step 5: ユーザーに報告**

5/10 の本番パイプラインを観察対象にする旨を伝える：

> 5/10 朝の本番パイプラインで以下が確認できれば移行成功です：
> - 生成された X 投稿3本がすべて構造解説型テンプレート準拠
> - 生成された note 記事が3テーマ該当のニュース解説（または「今振り返る」型）
> - 夜の X 投稿に note URL が自動付与される（CTA）
> - Day N／AItsm が一切生成されない

---

## Self-Review チェック結果

**1. Spec coverage:**
- 設計書「戦略の核」（X×note 役割分担）→ Task 5（x_strategy.md）でカバー
- 設計書「構造解説型テンプレート」→ Task 1, 5, 6 でカバー
- 設計書「1日3本の運用 / note 送客」→ Task 1, 3, 4 でカバー
- 設計書「システム改修」表の全項目 → Task 1〜7 でカバー
- 設計書「KPI と振り返り」→ Task 5（x_strategy.md に記載）。プロセス KPI の自動集計はスコープ外（手動運用で開始、6/7 評価時に必要なら別計画化）
- 設計書「移行」→ Task 7（凍結）と Task 8（スモークテスト）でカバー

**2. Placeholder scan:** TBD/TODO/「適切に」「実装後で」等のプレースホルダなし。

**3. Type consistency:** `append_note_url`・`load_note_url`・`post_one`・`build_post_text` のシグネチャは Task 3 で既存実装をそのまま使用。型・引数名のブレなし。
