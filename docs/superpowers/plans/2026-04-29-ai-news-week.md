# AIニュース解説週間 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** writer.md にニュース解説モードを追加し、毎日AIニュース解説3本を投稿できる体制を整える

**Architecture:** writer.md に新セクションを追加してニュース解説専用フォーマットを定義する。毎日使う投稿テンプレートを `content/x_posts/_template_news.md` に作成する。既存パイプラインはそのまま。

**Tech Stack:** Markdown、既存の `scripts/x_post.py`

---

### Task 1: writer.md にニュース解説モードを追加する

**Files:**
- Modify: `agents/writer.md`

- [ ] **Step 1: writer.md を開いて「X投稿のフォーマット」セクションを確認する**

`agents/writer.md` の81〜113行目付近にある「## X投稿のフォーマット」セクションを読む。
ハッシュタグ禁止の記述（109〜113行目）の直後に新セクションを追加する。

- [ ] **Step 2: ニュース解説モードのセクションを追記する**

`agents/writer.md` の「### X投稿 ハッシュタグ禁止」セクションの直後（113行目の後）に以下を追加する：

```markdown
## X投稿 ニュース解説モード

CEOから「ニュース解説」と指定された日はこのフォーマットを使う。
通常モードのフォーマット（主張型・Day N・AIそれって本当？）は使わない。

### 朝（1本目）：数字・事実フック

```
[企業名/固有名詞]が[具体的な数字・事実]を[した/発表した]。
[それが普通と何が違うのかを1文で]。
[今日の昼か夜に詳しく書く、という予告1文]。

ソース：[URL]
```

目安：3〜4文、100字前後。短く驚かせる。

### 昼（2本目）：構造解説

```
[ニュースの核心を問い形式で1文]

・[背景・なぜ今なのか]
・[具体的に何が起きているか]
・[他のプレイヤーとの違い・比較]

[締め：「要するにこういうことだ」の1文]

ソース：[URL]
```

目安：150〜250字。長文OK。箇条書き可。

### 夜（3本目）：読者への示唆

```
[今日のニュースを受けて、20代・これから動く人に何が変わるか]
[具体的に「何をすればいいか」or「何に気づくべきか」を1〜2点]

ソース：[URL]
```

目安：150〜200字。説教・煽りは禁止。

### ソースURLのルール

通常モードでは外部リンク禁止だが、ニュース解説モードではソース明示のためURLを全3本に入れる。
ハッシュタグは引き続き禁止。note URLも入れない。
```

- [ ] **Step 3: 追記内容を確認する**

`agents/writer.md` を読み返して以下を確認する：
- 「## X投稿 ニュース解説モード」セクションが追加されている
- 既存の「### X投稿 ハッシュタグ禁止」セクションが消えていない
- 朝・昼・夜の3フォーマットが揃っている

- [ ] **Step 4: コミットする**

```bash
git add agents/writer.md
git commit -m "feat: writer にニュース解説モードを追加"
```

---

### Task 2: 毎日使う投稿テンプレートを作成する

**Files:**
- Create: `content/x_posts/_template_news.md`

- [ ] **Step 1: テンプレートファイルを作成する**

`content/x_posts/_template_news.md` を以下の内容で作成する：

```markdown
# X投稿テンプレート — AIニュース解説

<!-- 使い方：このファイルをコピーして YYYY-MM-DD_[ネタ名].md にリネームして使う -->
<!-- ネタ元URL を3箇所の [ソースURL] に入れる -->
<!-- Writerはこのテンプレをベースにニュース解説モードで下書きを作る -->

## ニュース情報（Writerへの入力）

- ネタ元：[Step 0 で選んだニュースのタイトル]
- ソースURL：[URL]
- 核心の数字・事実：[例：Googleが1,000億超を投資]
- 20代への影響：[1〜2文で]

---

## 朝（1本目）

[企業名/固有名詞]が[具体的な数字・事実]を[した/発表した]。
[それが普通と何が違うのかを1文で]。
[今日の昼か夜に詳しく書く、という予告1文]。

ソース：[ソースURL]

---

## 昼（2本目）

[ニュースの核心を問い形式で1文]

・[背景・なぜ今なのか]
・[具体的に何が起きているか]
・[他のプレイヤーとの違い・比較]

[締め：「要するにこういうことだ」の1文]

ソース：[ソースURL]

---

## 夜（3本目）

[今日のニュースを受けて、20代・これから動く人に何が変わるか]
[具体的に「何をすればいいか」or「何に気づくべきか」を1〜2点]

ソース：[ソースURL]
```

- [ ] **Step 2: ファイルが正しく作成されたか確認する**

```bash
ls content/x_posts/_template_news.md
```

Expected: ファイルが存在する

- [ ] **Step 3: dry-run で投稿パースが通るか確認する**

```bash
python3 scripts/x_post.py content/x_posts/_template_news.md --dry-run
```

Expected: 朝・昼・夜の3本が表示される（[ソースURL]などのプレースホルダーが残っていてもOK）

- [ ] **Step 4: コミットする**

```bash
git add content/x_posts/_template_news.md
git commit -m "feat: AIニュース解説週間の投稿テンプレートを追加"
```

---

### Task 3: 毎日の運用フローを確認する

このタスクはコード変更なし。毎日の作業手順を頭に入れる。

- [ ] **Step 1: 毎朝の作業（5分）**

1. Step 0 の出力（または手動で調べたAIニュース）から1本選ぶ
2. `content/x_posts/_template_news.md` をコピーして `content/x_posts/YYYY-MM-DD_[ネタ名].md` にリネーム
3. 「ニュース情報」欄（ネタ元・URL・数字・20代への影響）を記入してWriterに渡す
4. Writerがニュース解説モードで朝・昼・夜の下書きを作成
5. CEOが確認・修正

- [ ] **Step 2: 投稿作業（朝・昼・夜）**

```bash
# 朝
python3 scripts/x_post.py --today --post 1

# 昼（4時間後）
python3 scripts/x_post.py --today --post 2

# 夜（さらに4時間後）
python3 scripts/x_post.py --today --post 3
```

- [ ] **Step 3: 翌朝の計測（2分）**

X analytics で前日の投稿3本のIMPを確認し、`logs/daily/YYYY-MM-DD_post_analysis.md` の数値サマリーに記入する。

- [ ] **Step 4: 週次集計（実験終了後：2026-05-05）**

`logs/weekly/2026-04-29_news_week_result.md` を作成して以下を記録する：

```markdown
# AIニュース解説週間 結果

| 日付 | 朝IMP | 昼IMP | 夜IMP | 合計 |
|------|-------|-------|-------|------|
| 04-29 | - | - | - | - |
| 04-30 | - | - | - | - |
| 05-01 | - | - | - | - |
| 05-02 | - | - | - | - |
| 05-03 | - | - | - | - |
| 05-04 | - | - | - | - |
| 05-05 | - | - | - | - |
| **平均** | | | | |

## 最高IMP投稿

## 最低IMP投稿とその分析

## 判断（継続 / 変更 / 中止）
```
