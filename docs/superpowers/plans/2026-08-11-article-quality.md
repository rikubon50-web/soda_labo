# SODA記事品質強化 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** デイリーパイプラインに「Researcher取材工程」「SODA視点ライブラリ」「Critic批評ループ」を追加し、記事の取材の深さ・独自性・文体を完全自動のまま強化する。

**Architecture:** パイプラインの実体は `src/pipelines/daily_pipeline.py` の `build_pipeline_prompt()` が返す1本のプロンプト文字列。ここに新Step（1.5 / 5.5 / 7.5）を挿入し、各Stepが参照するエージェント定義（`agents/*.md`）と視点ライブラリ（`docs/perspectives.md`）を新規作成する。Python のロジック変更はタイムアウト値のみ。

**Tech Stack:** Python 3（f-stringプロンプト構築）、Claude CLI（`run_claude`）、Markdownエージェント定義

**Spec:** `docs/superpowers/specs/2026-08-11-article-quality-design.md`

## Global Constraints

- 全テキスト・コミットメッセージは日本語（プロジェクト開発ルール）
- cron設定・公開フロー（`note_post.py` / `x_post.py`）は一切変更しない
- 完全自動運転を維持する（人の確認工程を入れない）
- 新工程の失敗でパイプラインを止めない（フォールバックあり）
- エージェント定義は `agents/_template_agent.md` の見出し構成（役割/責任範囲/出力形式/禁止事項）に従う
- このプロジェクトに pytest 等のテスト基盤はない。検証は `build_pipeline_prompt()` の出力確認コマンドで行う

---

### Task 1: `agents/researcher.md` 新規作成

**Files:**
- Create: `agents/researcher.md`

**Interfaces:**
- Produces: 取材ノートのフォーマット定義。保存先パス規約 `content/news/{日付}_research.md`（Task 3 の writer.md と Task 5 の Step 1.5 がこのパスを参照する）

- [ ] **Step 1: ファイルを作成する**

以下の内容で `agents/researcher.md` を作成する。

```markdown
# Researcher Claude

## 役割

CEOが採用したテーマ1本を深掘りし、Writerが安心して使える「取材ノート」を作る。
記事は書かない。事実の裏取りと材料集めに徹する。

## 責任範囲

- 採用ニュースの一次情報（公式発表・プレスリリース・元記事）の読み込み
- 英語ソースを含む追加検索（WebSearchで3〜5本）
- 反対意見・懐疑的な見方の収集（最低1つ）
- 比較に使える過去の数字（前年・前四半期・類似事例）の収集

## このAgentを呼ぶタイミング

- Step 1でCEOが本日のテーマを決定した直後（Step 2 Plannerの前）
- 成果物の取材ノートはWriter（Step 4）が執筆時の唯一の事実ソースとして使う

## 取材のルール

- 検索結果の要約文を信用しない。必ずWebFetchで元ページを開いて中身を確認する
- 数字は「数値・単位・出典・時点」をセットで記録する
- 1ソースしか確認できなかった数字は「未確認事項」に回す。複数ソースで確認できたもの、または公式一次情報で確認できたものだけを「確認できた事実」に載せる
- 反対意見が見つからない場合も「探したが見つからなかった」と記録する（省略しない）

## 出力形式（取材ノート）

保存先: `content/news/{日付}_research.md`

\```
# 取材ノート: [テーマ名]（YYYY-MM-DD）

## 確認できた事実（各項目に出典名を付す）
- 事実 — 出典名

## 数字一覧（数値・単位・出典・時点）
- 数値 | 単位 | 出典 | 時点

## 反対意見・留保
- （最低1つ。なければ「探したが見つからなかった」と書く）

## 未確認事項（検索したが裏取りできなかったこと）
- （Writerはここにある内容を使う場合、本文で未確認・報道ベースと明示する）
\```

## 禁止事項

- 記事本文を書かない（Writerの領域）
- 取材ノートに自分の意見・解釈を書かない（事実と出典に徹する）
- 未確認の数字を「確認できた事実」に入れない

---
*作成日：2026-08-11 / 作成理由：取材の浅さ解消のため Step 1.5 として新設*
```

注意: 上記の `\``` は実ファイルでは通常のコードフェンス ` ``` ` として書く（このプラン内でのエスケープ）。

- [ ] **Step 2: 内容を確認する**

Run: `head -20 agents/researcher.md`
Expected: `# Researcher Claude` で始まり、テンプレート見出し（役割/責任範囲）が含まれる

- [ ] **Step 3: コミット**

```bash
git add agents/researcher.md
git commit -m "Researcher定義を追加（Step 1.5 一次取材工程）"
```

---

### Task 2: `agents/critic.md` 新規作成

**Files:**
- Create: `agents/critic.md`

**Interfaces:**
- Produces: 採点基準（10点満点・合格7点・最大2周）と採点ログの保存先パス規約 `logs/daily/{日付}_critic.md`（Task 5 の Step 5.5 がこれを参照する）

- [ ] **Step 1: ファイルを作成する**

以下の内容で `agents/critic.md` を作成する。

```markdown
# Critic Claude

## 役割

Editorが仕上げたnote記事を、公開前に敵対的に批評する。
褒めない。直せる欠点を見つけることだけが仕事。

## 責任範囲

- note記事のAI臭・文体の採点（10点満点）
- Editorが実行できる形の修正指示の提示（必ず3つ以上）

## このAgentを呼ぶタイミング

- Step 5（Editor仕上げ）の後、Step 6（CEO最終判断）の前
- 修正指示の宛先はEditor。書き直すのはEditorであってCriticではない

## 採点基準（各項目2点、合計10点）

1. **voice_guide照合**: `docs/voice_guide.md` の「AI臭いパターン一覧」に1件でも該当したら0点
2. **構造の揺れ**: 論点が全部きれいに並び、迷い・揺れ（「でも」「ただ」「まだわからない」）が一度も出ない文章は減点
3. **締め**: 教訓・まとめで終わっていたら0点。余韻・問い・宣言で終わっているか
4. **リズム**: 声に出して読んだとき、息継ぎできない長文や読み返したくなる文がないか
5. **実感**: 具体的な数字・固有名詞・状況で書かれているか。実感のない一般論の段落があれば減点

## 運用ルール

- 合格ライン: 7点以上
- 7点未満: 修正指示を付けてEditorに書き直させ、再採点する（最大2周）
- 2周後も7点未満なら打ち切り、そのままCEOの最終判断（Step 6）に進む
- 採点と指摘は `logs/daily/{日付}_critic.md` に保存する（書き直しが発生した場合は各周の点数を追記する）

## 出力形式

\```
【Critic採点】
点数: n/10（内訳: ①n ②n ③n ④n ⑤n）
判定: 合格 / 書き直し（n周目）

修正指示（3つ以上、Editorが直せる形で具体的に）:
1. （段落・文を特定して指摘し、修正方針を添える）
2. …
3. …
\```

## 禁止事項

- 褒める・良い点を挙げる（それはCEOの仕事）
- テーマ選定・記事の方向性への口出し（Editorが直せない指摘はしない）
- 自分で本文を書き換える（書き直すのはEditor）

---
*作成日：2026-08-11 / 作成理由：AI臭の自己申告チェックを独立批評工程に置き換えるため Step 5.5 として新設*
```

注意: 上記の `\``` は実ファイルでは通常のコードフェンスとして書く。

- [ ] **Step 2: 内容を確認する**

Run: `grep -c "採点基準" agents/critic.md`
Expected: `1` 以上

- [ ] **Step 3: コミット**

```bash
git add agents/critic.md
git commit -m "Critic定義を追加（Step 5.5 敵対的批評工程）"
```

---

### Task 3: `agents/writer.md` に取材ノート縛りと視点接続ルールを追記

**Files:**
- Modify: `agents/writer.md`（「## 役割」セクションの直前に2セクション挿入）

**Interfaces:**
- Consumes: Task 1 の取材ノートパス `content/news/{日付}_research.md`
- Consumes: Task 4 の `docs/perspectives.md`

- [ ] **Step 1: writer.md に追記する**

`agents/writer.md` の `## 役割` の直前（voice_guide 照合の段落の後）に、以下の2セクションを挿入する。

```markdown
## 取材ノートの使用ルール（note記事）

`content/news/{日付}_research.md`（取材ノート）が存在する場合:

- 記事中の事実・数字は取材ノートに記載のあるものだけを使う。ノートにない数字は書かない
- 「未確認事項」の内容を使うときは、本文でも未確認・報道ベースであると明示する
- 取材ノートが存在しない場合のみ、Step 0の検索結果ベースで執筆してよい

## SODA視点の接続ルール（note記事）

`docs/perspectives.md`（SODA視点ライブラリ）を執筆前に必ず読む。

- 接続できる持論・伏線があれば本文で明示的に接続する（例:「以前から〜と見ている」「◯月に書いた◯◯がここに繋がる」）
- 新しい仮説を立てるときは「まだ仮説だが」と明示して書く（後日 perspectives.md に登録され、回収対象になる）
- 無理な接続はしない。接続できるものがない日は接続なしでよい
```

- [ ] **Step 2: 挿入位置と内容を確認する**

Run: `grep -n "取材ノートの使用ルール\|SODA視点の接続ルール\|^## 役割" agents/writer.md`
Expected: 「取材ノートの使用ルール」「SODA視点の接続ルール」の行番号が「## 役割」より小さい

- [ ] **Step 3: コミット**

```bash
git add agents/writer.md
git commit -m "Writerに取材ノート縛りとSODA視点接続ルールを追加"
```

---

### Task 4: `docs/perspectives.md` 初期版を過去記事から生成

**Files:**
- Create: `docs/perspectives.md`
- 参照（読むだけ）: `content/note/` の直近30ファイル

**Interfaces:**
- Produces: `docs/perspectives.md`（見出し構成「持論 / ウォッチ中の仮説 / 回収済みアーカイブ」。Task 3 の writer.md と Task 5 の Step 1・7.5 がこの見出し名に依存する）

- [ ] **Step 1: 過去記事を読む**

`content/note/` の直近30ファイル（`ls -t content/note/ | head -30`）を読み、次の2つを抽出する。

1. **持論**: 複数記事で繰り返し現れる主張・スタンス（例: 2026-08-11の記事にある「削られているのはAIに仕事を奪われた人ではなく、AI導入後の組織に役割が残らなかった人」のような、SODA固有の見方）。5〜10個
2. **未回収の伏線**: 「Q3の数字が出るとき〜が見えてくる」のように、将来の答え合わせを予告している記述。初出記事の日付・回収予定時期とセットで最大15個

- [ ] **Step 2: ファイルを作成する**

以下の骨格で `docs/perspectives.md` を作成し、Step 1 の抽出結果を埋める。

```markdown
# SODA視点ライブラリ

CEOとWriterは記事制作時に必ずこのファイルを読む。
更新はデイリーパイプラインの Step 7.5（Secretary）が行う。

## 持論（SODAのスタンス）

- （抽出した主張を1行1件で列挙。例: レイオフは「AIに仕事を奪われる」ではなく「AI導入後の組織に自分の役割が残るか」の話）

## ウォッチ中の仮説（最大15件）

形式: `- 仮説の内容 | 初出: YYYY-MM-DD | 回収予定: YYYY-MM頃`

- （抽出した伏線を列挙。例: テックレイオフの波が一時的調整か構造転換かはQ3雇用統計で判明する | 初出: 2026-08-11 | 回収予定: 2026-10頃）

## 回収済みアーカイブ

形式: `- 仮説の内容 | 結果: 当たり/外れ/部分的 | 回収日: YYYY-MM-DD`

- （初期版では空でよい。過去記事内で既に答え合わせ済みの伏線があれば移す）
```

- [ ] **Step 3: 件数と構成を確認する**

Run: `grep -n "^## " docs/perspectives.md && grep -c "回収予定" docs/perspectives.md`
Expected: 見出し3つ（持論/ウォッチ中の仮説/回収済みアーカイブ）、回収予定付き項目が1〜15件

- [ ] **Step 4: コミット**

```bash
git add docs/perspectives.md
git commit -m "SODA視点ライブラリ初期版を過去記事から生成"
```

---

### Task 5: `build_pipeline_prompt()` に新Stepを組み込む

**Files:**
- Modify: `src/pipelines/daily_pipeline.py`（`build_pipeline_prompt()` 内のプロンプト文字列。44〜139行付近）

**Interfaces:**
- Consumes: `agents/researcher.md`（Task 1）、`agents/critic.md`（Task 2）、`docs/perspectives.md`（Task 4）、取材ノートパス `content/news/{ds}_research.md`、採点ログパス `logs/daily/{ds}_critic.md`
- Produces: 新しいパイプラインプロンプト（Step 0拡張 / 1.5 / 5.5 / 7.5 追加）

プロンプトは f-string なので `{ds}` `{ds_prev}` はそのまま変数展開として書く。以下の5編集をすべて行う。

- [ ] **Step 1: 事前読み込みリストに perspectives.md を追加する**

`7. docs/voice_guide.md — 声の基準書（WriterとEditorは必ず参照すること）` の行の直後に追加:

```
8. docs/perspectives.md — SODA視点ライブラリ（CEOとWriterは必ず参照すること）
```

- [ ] **Step 2: Step 0 の検索クエリを4本に拡張する**

既存の2クエリ行:

```
- 検索クエリ: "AI news today {ds}"
- 検索クエリ: "生成AI ニュース {ds}"
```

の直後に2行追加:

```
- 検索クエリ: "AI layoffs OR funding OR acquisition news {ds}"
- 検索クエリ: "AI industry news {ds_prev}"
```

- [ ] **Step 3: Step 1 に伏線回収の優先検討を追記し、Step 1.5 を新設する**

Step 1 の `**朝会議ログ（logs/meeting/{ds}_meeting.md）のCEO最終判断・Writerへの指示を最優先で参照すること。**` の直後に1行追加:

```
**docs/perspectives.md の「ウォッチ中の仮説」に回収予定時期が到来したものがあれば、その回収をその日のテーマ候補として最優先で検討すること。**
```

Step 1 ブロックの末尾（`出力形式: agents/ceo.md の「優先テーマを出すとき」フォーマット。`の後、`## Step 2` の前）に新Stepを挿入:

```
## Step 1.5: Researcher — 一次取材（Step 2の前に必ず実行）
agents/researcher.md を読み、Step 1でCEOが採用したテーマ1本を深掘りする。
- 一次情報（公式発表・プレスリリース・元記事）をWebFetchで実際に開いて読む
- 英語ソースを含む追加検索をWebSearchで3〜5本行う
- 反対意見・懐疑的な見方を最低1つ探す（見つからなければ「探したが見つからなかった」と記録）
- 比較に使える過去の数字（前年・前四半期・類似事例）を集める
取材結果を content/news/{ds}_research.md に agents/researcher.md の「取材ノート」フォーマットで保存する。
一次情報が取得できない場合も、確認できた範囲で取材ノートを保存する（4区分の見出しは維持する）。
```

- [ ] **Step 4: Step 4（Writer）に取材ノート縛りと視点接続を追記する**

Step 4 の `**朝会議ログのWriterへの指示がある場合は必ず従うこと。**` の直後に2行追加:

```
**note記事の事実・数字は content/news/{ds}_research.md（取材ノート）に記載のあるものだけを使うこと。ノートにない数字は書かない。「未確認事項」の内容は本文でも未確認・報道ベースと明示する。取材ノートが存在しない場合のみStep 0の検索結果ベースで執筆してよい。**
**docs/perspectives.md を読み、接続できる持論・伏線があれば本文で明示的に接続すること（agents/writer.md「SODA視点の接続ルール」参照）。**
```

- [ ] **Step 5: Step 5.5（Critic）と Step 7.5（視点ライブラリ更新）を新設する**

`## Step 6` の前に挿入:

```
## Step 5.5: Critic — 敵対的批評（Step 6の前に必ず実行）
agents/critic.md を読み、Step 5でEditorが仕上げたnote記事を採点する。
- docs/voice_guide.md の「AI臭いパターン一覧」と照合する
- agents/critic.md の採点基準（各2点×5項目=10点満点）で採点し、直せる欠点を必ず3つ以上、修正指示として挙げる
- 7点未満の場合: Editorが修正指示に従って記事を書き直し、Criticが再採点する。この書き直しは最大2周まで
- 2周後も7点未満なら打ち切り、そのままStep 6に進む（CEOの減点判断に委ねる）
採点結果（各周の点数と指摘）を logs/daily/{ds}_critic.md に保存する。
```

`## 全体ルール` の前（Step 7 の後）に挿入:

```
## Step 7.5: Secretary — 視点ライブラリ更新
docs/perspectives.md を更新して上書き保存する。
- 今日のnote記事に新しい仮説・伏線があれば「ウォッチ中の仮説」に追記する（初出日付と回収予定時期を必ず付す）
- 今日の記事で回収（答え合わせ）した仮説があれば、結果（当たり/外れ/部分的）を添えて「回収済みアーカイブ」へ移動する
- 「ウォッチ中の仮説」が15件を超える場合は、古い・弱いものからアーカイブへ移す
```

- [ ] **Step 6: プロンプト出力を検証する**

Run:

```bash
cd /Users/rikubon50/Desktop/SODA_LABO && python3 -c "
import sys; sys.path.insert(0, '.')
from datetime import date
from src.pipelines.daily_pipeline import build_pipeline_prompt
p = build_pipeline_prompt(date(2026, 8, 12))
for key in ['Step 1.5', 'Step 5.5', 'Step 7.5', '2026-08-12_research.md', '2026-08-12_critic.md', 'perspectives.md', 'AI layoffs OR funding']:
    assert key in p, f'欠落: {key}'
assert p.index('Step 1.5') < p.index('## Step 2'), 'Step 1.5の位置が不正'
assert p.index('Step 5.5') < p.index('## Step 6'), 'Step 5.5の位置が不正'
assert p.index('Step 7.5') < p.index('## 全体ルール'), 'Step 7.5の位置が不正'
print('OK')
"
```

Expected: `OK`

- [ ] **Step 7: コミット**

```bash
git add src/pipelines/daily_pipeline.py
git commit -m "パイプラインにStep 1.5取材・5.5批評・7.5視点更新を追加"
```

---

### Task 6: タイムアウト延長と最終検証

**Files:**
- Modify: `src/config.py`（`PIPELINE_TIMEOUT = 1800` の行）

**Interfaces:**
- Consumes: Task 5 のプロンプト（工程増加により実行時間が延びるため）

- [ ] **Step 1: タイムアウトを45分に延長する**

`src/config.py` の

```python
PIPELINE_TIMEOUT = 1800   # 秒（30分）
```

を

```python
PIPELINE_TIMEOUT = 2700   # 秒（45分）取材・批評工程の追加分を含む
```

に変更する。

- [ ] **Step 2: 変更を確認する**

Run: `cd /Users/rikubon50/Desktop/SODA_LABO && python3 -c "import sys; sys.path.insert(0,'.'); from src.config import PIPELINE_TIMEOUT; assert PIPELINE_TIMEOUT == 2700; print('OK')"`
Expected: `OK`

- [ ] **Step 3: プロンプト全文を出力して通し読みする**

Run: `cd /Users/rikubon50/Desktop/SODA_LABO && python3 -c "import sys; sys.path.insert(0,'.'); from datetime import date; from src.pipelines.daily_pipeline import build_pipeline_prompt; print(build_pipeline_prompt(date(2026,8,12)))"`

確認観点: Step番号が 0→1→1.5→2→3→4→5→5.5→6→7→7.5 の順で並ぶ / 参照ファイルパス（researcher.md・critic.md・perspectives.md・research.md）に誤字がない / 既存Step（2,3,6,7）が壊れていない

- [ ] **Step 4: コミット**

```bash
git add src/config.py
git commit -m "パイプラインタイムアウトを45分に延長"
```

---

## 実装後の運用検証（翌朝）

翌朝8:07のcron実行後に確認する（実装タスクではなく運用確認）:

1. `content/news/{当日}_research.md` が4区分で生成されている
2. note記事本文に取材ノートの数字だけが使われ、視点接続の一文がある（接続対象がある場合）
3. `logs/daily/{当日}_critic.md` に採点が記録されている
4. `docs/perspectives.md` の「ウォッチ中の仮説」が更新されている
5. `logs/cron/{当日}_run.log` にエラーがない
