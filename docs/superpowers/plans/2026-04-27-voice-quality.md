# Voice Quality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 記事生成パイプライン全層に「声の基準書（voice_guide.md）」を統合し、AI臭いパターンを自動排除する仕組みを作る。

**Architecture:** `docs/voice_guide.md` を Single Source of Truth として新設し、Writer・Editor エージェント定義ファイルとデイリーパイプラインの3層からそれぞれ参照させる。既存のフロー・ファイル構造は変えない。

**Tech Stack:** Markdown（プロンプトファイル）、Python（daily_pipeline.py）

**Spec:** `docs/superpowers/specs/2026-04-27-voice-quality-design.md`

---

### Task 1: `docs/voice_guide.md` を新設する

**Files:**
- Create: `docs/voice_guide.md`

- [ ] **Step 1: ファイルを作成する**

以下の内容で `docs/voice_guide.md` を新規作成する。

```markdown
# 声の基準書（Voice Guide）

WriterとEditorは、文章を生成・編集する前に必ずこのファイルを読み込むこと。

---

## 自然さの定義

「書いた人間の迷いや手触りが残っている」こと。

整いすぎた文章はAI臭い。論点が全部きれいに並んでいる、締めが教訓で終わる、揺れがない——それが人間らしさを消す。

---

## AI臭いパターン一覧（NG → 修正方針）

以下のパターンが原稿に含まれている場合は必ず修正すること。

| NG パターン | 修正方針 |
|------------|---------|
| 「3点あります」「以下の〇点」など番号で整理して始める | 番号を振らず、次の文でいきなり語る |
| 「まとめると〜」で締める | 締めは余韻・問い・宣言。まとめない |
| 「〜と言えるでしょう」「〜ではないでしょうか」 | 断定するか削除する |
| 「〜を意識することが大切です」「〜が重要です」 | 説教。削除して具体的な行動か事実に置き換える |
| 「〜の時代において」「近年、〜が進んでいます」などの前置き | 削除して本論から始める |
| 箇条書きで全部並べて、最後に自分の見解がない | 箇条書きの後に自分の一文を必ず追加する |
| 「ぜひ〜してみてください」 | 締めとして弱すぎる。削除するか別の言葉に変える |
| うまくいった話だけで終わる | うまくいかなかった話・留保・迷いを必ず残す |
| 「AIの力を借りることで〜が実現できます」などの煽り | 削除。実際に起きたことだけ書く |

---

## 自然な文章のOK条件

以下が1つ以上含まれていれば「人間らしい」と判断する。

- 途中に「でも」「ただ」「とはいえ」など自分の中の揺れが見える
- 具体的な固有名詞・数字・日付・固有の状況がある
- 「まだわからない」「そうとも言えない」「断言できないが」などの留保が入っている
- 読み上げて詰まらない（声に出して不自然な箇所がない）
- うまくいかなかったことが正直に書いてある

---

## 書く前の自己確認（3問）

文章を保存する前に、以下を自問すること。

1. **この文章、自分が実際に経験・観察したことか？** 経験のない話を一般論で補っていないか
2. **「で、読者は何をする気になる？」** 読み終わった後に読者が取る行動が1つ思い浮かぶか
3. **これを友人に口頭で話したら、同じ言い回しになるか？** ならないなら書き直す

---

## 具体的な書き換え例

**Before（AI臭い）:**
> 近年、AIが急速に進化する中で、多くの企業がその活用に注目しています。本記事では、AIエージェントについて3つの観点から解説します。

**After（自然）:**
> Googleが今週1,000億円超をAIエージェントに突っ込んだ。金額だけ見てスルーするのは簡単だ。何に使われているかを知ると、自分の仕事とつながって見える。

---

**Before（AI臭い）:**
> まとめると、AIエージェントは今後のビジネスにおいて重要な役割を果たすことが期待されます。ぜひ参考にしてみてください。

**After（自然）:**
> 確実ではない。でも、今触れる機会があるなら、触れておく方がいい。
```

- [ ] **Step 2: ファイルが作成されたことを確認する**

```bash
wc -l docs/voice_guide.md
```

期待出力: 60行以上

- [ ] **Step 3: コミットする**

```bash
git add docs/voice_guide.md
git commit -m "feat: 声の基準書（voice_guide.md）を新設"
```

---

### Task 2: `agents/writer.md` を更新する

**Files:**
- Modify: `agents/writer.md`（冒頭に4行追加）

- [ ] **Step 1: 現在の冒頭を確認する**

```bash
head -10 agents/writer.md
```

期待出力: `# Writer Claude` から始まり `## 役割` が続く

- [ ] **Step 2: `## 役割` の直前に新セクションを挿入する**

`agents/writer.md` の `## 役割` の直前（ファイル先頭の `# Writer Claude` の直後）に以下を挿入する。

挿入箇所は `# Writer Claude` と `## 役割` の間。

```markdown

## 文章を書く前に必ず実行すること

`docs/voice_guide.md` を Read tool で読み込む。
生成した文章を voice_guide の「AI臭いパターン」に1つずつ照合し、
該当箇所があれば修正してからファイルに保存する。

```

- [ ] **Step 3: 挿入を確認する**

```bash
head -15 agents/writer.md
```

期待出力: `# Writer Claude` → `## 文章を書く前に必ず実行すること` → `## 役割` の順で並んでいること

- [ ] **Step 4: コミットする**

```bash
git add agents/writer.md
git commit -m "feat: writer にvoice_guide参照を追加"
```

---

### Task 3: `agents/editor.md` を更新する

**Files:**
- Modify: `agents/editor.md`（チェックリストに自然さ確認セクションを追加）

- [ ] **Step 1: 現在のチェックリスト末尾を確認する**

```bash
grep -n "文章確認\|自然さ" agents/editor.md
```

期待出力: `### 文章確認` が存在し、`自然さ` はまだない

- [ ] **Step 2: `### 文章確認` セクションの末尾（最後の `- [ ]` 行の後）に新セクションを追加する**

`### 文章確認` の最後の項目 `- [ ] X投稿3本すべてにハッシュタグが含まれていないか（含まれていたら削除）` の直後に以下を挿入する。

```markdown

### 自然さ確認（voice_guide.md 照合）
- [ ] `docs/voice_guide.md` を Read tool で読み込んだか
- [ ] AI臭いパターンが残っていないか（一覧に1つずつ照合したか）
- [ ] 「まとめると」「〜点あります」「〜が大切です」が残っていないか
- [ ] 途中に「でも」「ただ」「まだわからない」などの揺れが1箇所以上あるか
- [ ] 読み上げて詰まる文がないか
```

- [ ] **Step 3: 挿入を確認する**

```bash
grep -n "自然さ確認" agents/editor.md
```

期待出力: 行番号つきで `### 自然さ確認（voice_guide.md 照合）` が表示される

- [ ] **Step 4: コミットする**

```bash
git add agents/editor.md
git commit -m "feat: editor に自然さ確認チェックリストを追加"
```

---

### Task 4: `src/pipelines/daily_pipeline.py` を更新する（3箇所）

**Files:**
- Modify: `src/pipelines/daily_pipeline.py`

#### 4-a: 事前読み込みリストに voice_guide を追加

- [ ] **Step 1: 現在の事前読み込みリストを確認する**

```bash
grep -n "winning_topics\|voice_guide" src/pipelines/daily_pipeline.py
```

期待出力: `winning_topics.md` の行が表示される。`voice_guide` はまだない。

- [ ] **Step 2: `winning_topics.md` の行の直後に追記する**

`6. audience/winning_topics.md — 反応が取れた確定テーマ（あれば優先的に参考にする）` の直後に以下を追記する。

```
7. docs/voice_guide.md — 声の基準書（WriterとEditorは必ず参照すること）
```

- [ ] **Step 3: 確認する**

```bash
grep -n "voice_guide" src/pipelines/daily_pipeline.py
```

期待出力: 1行目に `7. docs/voice_guide.md` が表示される

---

#### 4-b: Step4（Writer）に voice_guide 照合の指示を追加

- [ ] **Step 4: Step4セクションの末尾を確認する**

```bash
grep -n "Step 4\|Step 5" src/pipelines/daily_pipeline.py
```

期待出力: `## Step 4: Writer` と `## Step 5: Editor` の行番号が確認できる

- [ ] **Step 5: Step4 の短尺動画台本の行（`- 短尺動画台本 →`）の直後に追記する**

`- 短尺動画台本 → content/short_videos/{ds}_[タイトル略称].md` の行の直後に以下を追記する。

```
**文章生成前に `docs/voice_guide.md` を Read tool で確認し、AI臭いパターンが出ていないかを照合してからファイルに保存すること。**
```

- [ ] **Step 6: 確認する**

```bash
grep -n "voice_guide\|AI臭い" src/pipelines/daily_pipeline.py
```

期待出力: 2行になる（事前読み込みの行 + Step4の行）

---

#### 4-c: Step5（Editor）の編集メモに自然さ確認を追加

- [ ] **Step 7: 編集メモのフォーマットを確認する**

```bash
grep -n "残課題\|自然さ" src/pipelines/daily_pipeline.py
```

期待出力: `残課題:` が存在し、`自然さ` はまだない

- [ ] **Step 8: `- 残課題:` の直後に追記する**

編集メモの最後の行 `- 残課題: （直しきれなかった点があれば記載。なければ「なし」）` の直後に以下を追記する。

```
- 自然さ確認: voice_guide照合 ✅/❌ | AI臭いパターン修正箇所（あれば列挙、なければ「なし」）
```

- [ ] **Step 9: 確認する**

```bash
grep -n "自然さ確認" src/pipelines/daily_pipeline.py
```

期待出力: 1行 `自然さ確認: voice_guide照合` が表示される

---

#### 4-d: Step6（CEO採点）に自然さを採点基準として追加

- [ ] **Step 10: Step6の採点基準を確認する**

```bash
grep -n "Step 6\|スコアが3以下" src/pipelines/daily_pipeline.py
```

期待出力: `## Step 6` と `スコアが3以下` の行番号が確認できる

- [ ] **Step 11: Step6 の1文目（`agents/ceo.md の「最終公開判断を出すとき」`）の後ろに追記する**

`agents/ceo.md の「最終公開判断を出すとき」フォーマットで5段階スコアを出す。` の直後に以下を追記する。

```
採点時は以下の基準も含めること：自然さ（voice_guide の AI臭いパターンが残っていないか。人間が書いた手触りがあるか）。AI臭いパターンが残っている場合はスコアを1点減点する。
```

- [ ] **Step 12: 最終確認——全追加箇所を一覧で確認する**

```bash
grep -n "voice_guide\|AI臭い\|自然さ" src/pipelines/daily_pipeline.py
```

期待出力: 4行（事前読み込み・Step4・Step5編集メモ・Step6採点基準）

- [ ] **Step 13: コミットする**

```bash
git add src/pipelines/daily_pipeline.py
git commit -m "feat: パイプラインにvoice_guide照合・自然さ採点を統合"
```

---

### Task 5: 動作確認

- [ ] **Step 1: 全変更ファイルを確認する**

```bash
git log --oneline -5
```

期待出力: 直近5件のコミットに今回の4件（voice_guide新設・writer更新・editor更新・pipeline更新）が含まれる

- [ ] **Step 2: voice_guide が各ファイルから参照されていることを確認する**

```bash
grep -rn "voice_guide" agents/ src/pipelines/daily_pipeline.py
```

期待出力:
```
agents/writer.md:   `docs/voice_guide.md` を Read tool で読み込む。
agents/editor.md:   `docs/voice_guide.md` を Read tool で読み込んだか
src/pipelines/daily_pipeline.py: 7. docs/voice_guide.md
src/pipelines/daily_pipeline.py: docs/voice_guide.md を Read tool で確認し
src/pipelines/daily_pipeline.py: voice_guide照合
src/pipelines/daily_pipeline.py: voice_guide の AI臭いパターン
```

- [ ] **Step 3: daily_pipeline.py の構文チェック**

```bash
python3 -m py_compile src/pipelines/daily_pipeline.py && echo "OK"
```

期待出力: `OK`（エラーがなければパス）
