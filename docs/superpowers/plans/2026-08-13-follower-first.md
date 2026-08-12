# フォロワー最適化再設計 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** システム全体を「週次フォロワー純増」に最適化する縮小集中 — cron 11→5本、平日イベント即応制、統合週次レビュー、沈黙検知、汚染浄化。

**Architecture:** daily_pipeline の平日 Step 1 に即応ゲートを追加し、「出さない日」は素材メモのみで終了する分岐を main() 側でも受ける。廃止7ジョブの必須機能は weekly_analysis（改組）と note_metrics（フォロワーログ移設）に吸収。新規 health_check.py（Claude不使用の純Python）が沈黙を検知する。crontab 変更はコード完成後の最終タスク。

**Tech Stack:** Python 3、Claude CLI（run_claude）、既存の note 配信基盤

**Spec:** `docs/superpowers/specs/2026-08-13-follower-first-redesign.md`

## Global Constraints

- 全テキスト・コミットメッセージは日本語
- **土日モード（まとめ・実録）と取材/批評/視点工程・配信骨格（note_post/note_magazine/note_metrics のUI操作部）は変更しない**
- 土日プロンプトは改修前後でバイト一致を維持する（平日のみ変更）
- 廃止スクリプトの削除は参照ゼロ確認後。crontab 変更は最終タスクまで行わない
- **notify_error.py の実発火テスト禁止**（実メール）
- ファイルパス規約（タスク間インターフェース）: 素材メモ=`content/news/{ds}_memo.md`、非公開日マーカー=`logs/daily/{ds}_no_publish.txt`、翌週方針=`docs/weekly_direction.md`、フォロワーログ=`logs/ops/follower_log.jsonl`（`{"date","followers"}` 行形式・同日重複追記禁止）
- 並行作業時のgitルール: `git add` は自タスクの成果物のみファイル名指定（`-A`/`.` 禁止）、index.lock は2秒待ち最大3回リトライ

---

### Task 1: `scripts/health_check.py` 新設（沈黙検知）

**Files:**
- Create: `scripts/health_check.py`

**Interfaces:**
- Produces: コマンド `python3 scripts/health_check.py`（Task 7 が cron 9:00 に登録）
- Consumes: パス規約（Global Constraints）。`.env` の `HEALTHCHECK_URL`（任意）

- [ ] **Step 1: 実装する**

Claude不使用の純Python。前日（`date.today() - timedelta(days=1)`）について確認:

1. `logs/metrics/{昨日}.json` が存在するか（毎日必須）
2. `content/note/{昨日}_*.md` **または** `content/news/{昨日}_memo.md` が存在するか（毎日どちらか必須。土日は記事のみ有効=メモでは合格にしない）
3. 昨日が日曜なら `logs/weekly/{昨日}*.md` が存在するか
4. `logs/ops/follower_log.jsonl` に昨日の行があるか

欠損があれば `notify_error.py` を subprocess で呼び「沈黙検知」として通知（欠損項目を列挙）。全部OKなら、`.env` に `HEALTHCHECK_URL` が定義されていれば `urllib.request` で GET ping（失敗しても無視）、未定義ならスキップ。stdout に判定サマリを出す。オプション: `--date YYYY-MM-DD`（対象日指定・テスト用）と `--dry-run`（通知・pingを行わず判定表示のみ）。

- [ ] **Step 2: 3ケース検証**

Run: `cd /Users/rikubon50/Desktop/SODA_LABO && python3 scripts/health_check.py --date 2026-08-12 --dry-run`（--dry-run は通知せず判定表示のみ。8/12は記事・メトリクスありで合格のはず）と、存在しない日付 `--date 2026-01-01 --dry-run`（欠損列挙が出ること）
Expected: 合格/欠損がそれぞれ正しく表示。notify_error は発火しない

- [ ] **Step 3: コミット**

```bash
git add scripts/health_check.py
git commit -m "沈黙検知スクリプトを新設（前日産出物の存在確認+外形監視ping）"
```

---

### Task 2: フォロワーログ追記を `note_metrics.py` に移設

**Files:**
- Modify: `scripts/note_metrics.py`

**Interfaces:**
- Produces: `logs/ops/follower_log.jsonl` への日次追記（22:30。同日重複防止付き）。旧 run_list_check の `append_follower_log` と同形式

- [ ] **Step 1: 実装する**

`main()` の保存成功後（dry-run時は行わない）、`followers` が None でなければ `logs/ops/follower_log.jsonl` に `{"date": 今日, "followers": N}` を追記する。追記前に同日行の有無を確認（既存 run_list_check.py の `append_follower_log` 実装を移植してよい）。

- [ ] **Step 2: 検証**

Run: `python3 -c "import ast; ast.parse(open('scripts/note_metrics.py').read()); print('OK')" && python3 scripts/note_metrics.py --dry-run > /dev/null 2>&1; echo "exit: $?"`（dry-runでは追記されないこと: `wc -l logs/ops/follower_log.jsonl` が実行前後で不変）
Expected: `OK` / `exit: 0` / 行数不変

- [ ] **Step 3: コミット**

```bash
git add scripts/note_metrics.py
git commit -m "フォロワーログ追記をnote_metricsに移設（22:30に確実に記録）"
```

---

### Task 3: 平日イベント即応制（daily_pipeline）

**Files:**
- Modify: `src/pipelines/daily_pipeline.py`（平日プロンプトの Step 1 と main()。土日プロンプトはバイト不変）

**Interfaces:**
- Produces: 出さない日の `content/news/{ds}_memo.md` と `logs/daily/{ds}_no_publish.txt`（Task 1 が検査）
- Consumes: `docs/weekly_direction.md`（Task 4 が生成。存在しない場合スキップ可の扱いで事前読み込みに追加）

- [ ] **Step 0: 改修前の土日プロンプトを保存（回帰基準）**

```bash
cd /Users/rikubon50/Desktop/SODA_LABO && python3 -c "
import sys; sys.path.insert(0,'.')
from datetime import date
from src.pipelines.daily_pipeline import build_pipeline_prompt
open('/tmp/prompt_sat_before.txt','w').write(build_pipeline_prompt(date(2026,8,15)))
open('/tmp/prompt_sun_before.txt','w').write(build_pipeline_prompt(date(2026,8,16)))
print('saved')"
```

- [ ] **Step 1: 事前読み込みリストの入れ替えと廃止ジョブ参照の除去（全曜日共通）**

廃止ジョブの産出物への死んだ参照を残さない（X汚染事件と同型のドリフト防止）。以下をすべて行う:

1. 事前読み込みリストから項目1〜3（`logs/meeting/{ds}_meeting.md`・`logs/daily/{前日}_post_analysis.md`・`logs/ideas/{前日}_ideas.md`）を削除し、番号を詰める
2. 末尾に追加: `docs/weekly_direction.md — 直近の週次レビューが決めた翌週方針（存在すれば。CEOはテーマ判断時に参照）`
3. Step 1 内の「**朝会議ログ（logs/meeting/{ds}_meeting.md）のCEO最終判断・Writerへの指示を最優先で参照すること。**」を「**docs/weekly_direction.md の翌週方針をテーマ判断の指針にすること（存在すれば）。**」に差し替え
4. Step 4 内の「**昨日の投稿分析（post_analysis）で反応が高かった…**」「**アイデア資産（ideas）に…**」「**朝会議ログのWriterへの指示…**」の3行を削除
5. 土日の曜日別ブロック内の「朝会議ログの決定が平日ニュース前提の場合は参考に留め…」の一文を「docs/weekly_direction.md の方針が本日のモードと矛盾する場合は、本日のモードの成果物形式を優先すること。」に差し替え

注意: これは土日出力も変える意図的変更。Step 0 の回帰基準との比較は「差分が上記の削除・差し替え行のみであること」の確認に変える（Step 4 参照）。

- [ ] **Step 2: 平日 Step 1 に即応ゲートを追加する**

平日の Step 1 ブロック（CEO）の冒頭（`agents/ceo.md を読み、...` の直後）に挿入:

```
**即応ゲート判定（最初に行う）**: Step 0のニュースに「即応深掘りに値する大ニュース」があるかをまず判定する。
基準: 業界構造を変える規模のイベント（大型買収・大規模レイオフ・主要モデル/製品の発表・重大規制）で、翌日整理型の深掘り記事が書けるもの。迷ったら「出さない」。公開は週2〜3本が目安であり、毎日出すことは目標ではない。
- 値するニュースが**ある**場合: そのニュースをテーマに、以降のStepを通常どおりすべて実行する
- **ない**場合: content/news/{ds}_memo.md に「本日の主要動向3行+docs/perspectives.md への接続候補1行」を保存し、logs/daily/{ds}_no_publish.txt に判断理由を1行保存して、**Step 1.5以降をすべてスキップし、その旨を報告して終了する**
```

- [ ] **Step 3: main() に「出さない日」の受けを追加する**

main() の note投稿判定部（`note_files = sorted(NOTE_DIR.glob(...))` の後）を変更。現在は記事がないと `_notify_error("note記事ファイル未作成", ...)` するが、平日かつ `logs/daily/{ds}_no_publish.txt` が存在する場合は正常系として扱う:

```python
    if note_files:
        _log.info(f"note投稿: {note_files[0].name}")
        if run_note_post(note_files[0], run_log):
            _log.info("マガジン追加")
            run_magazine_add(run_log)
    elif (DAILY_LOG_DIR / f"{ds}_no_publish.txt").exists():
        _log.info("即応なし日（素材メモのみ・公開なし）")
    else:
        _notify_error("note記事ファイル未作成", f"content/note/{ds}_*.md が存在しません")
        _log.warning("note記事ファイルが見つかりません")
```

パイプラインの二重実行ガードも同様に: 冒頭の `note_files` 存在チェックに `no_publish.txt` 存在も加える（メモ日で再実行されたとき二重にパイプラインを回さない）。

- [ ] **Step 4: 検証**

```bash
cd /Users/rikubon50/Desktop/SODA_LABO && python3 -c "
import sys, difflib; sys.path.insert(0,'.')
from datetime import date
from src.pipelines.daily_pipeline import build_pipeline_prompt
wk = build_pipeline_prompt(date(2026,8,14))
assert '即応ゲート判定' in wk and '2026-08-14_memo.md' in wk and '2026-08-14_no_publish.txt' in wk
for ng in ['meeting.md', 'post_analysis', 'ideas.md', '朝会議']:
    assert ng not in wk, f'平日に廃止参照残存: {ng}'
sat = build_pipeline_prompt(date(2026,8,15)); sun = build_pipeline_prompt(date(2026,8,16))
assert '即応ゲート' not in sat and '即応ゲート' not in sun, '土日に混入'
# 土日の差分が意図した削除・差し替え行のみであること
ALLOWED = ['meeting', 'post_analysis', 'ideas', '朝会議', 'weekly_direction', '投稿分析', 'アイデア資産']
for cur, path, name in ((sat,'/tmp/prompt_sat_before.txt','土'),(sun,'/tmp/prompt_sun_before.txt','日')):
    before = open(path).read()
    for line in difflib.unified_diff(before.split('\n'), cur.split('\n'), lineterm=''):
        if line.startswith(('+', '-')) and not line.startswith(('+++', '---')) and line[1:].strip():
            assert any(k in line for k in ALLOWED) or line[1:].strip().startswith(tuple('0123456789')), f'{name}に想定外の差分: {line[:80]}'
print('OK')"
```

Expected: `OK`（土日の差分は廃止参照の除去と weekly_direction 関連、事前読み込みの番号振り直しのみ）

- [ ] **Step 5: コミット**

```bash
git add src/pipelines/daily_pipeline.py
git commit -m "平日をイベント即応制に（即応ゲート+出さない日の素材メモ分岐）"
```

---

### Task 4: 統合週次レビュー（weekly_analysis 改組）

**Files:**
- Modify: `scripts/weekly_analysis.py`

**Interfaces:**
- Produces: `docs/weekly_direction.md`（翌週方針。Task 3 のパイプラインが読む）、`audience/winning_topics.md` の更新指示、`audience/personas.md` への検証メモ追記指示
- Consumes: `logs/ops/follower_log.jsonl`、`logs/metrics/`、廃止対象ジョブが担っていた機能（このタスクで吸収）

- [ ] **Step 1: プロンプトを6機能構成に改組する**

既存のプロンプト（分析観点+データ）を以下の6セクション構成に書き換える。データ組み立て（メトリクス・フォロワーログ・会議ログ等の収集関数）は既存を流用し、廃止ジョブ依存のセクション（商品タネバンク・アイデアバンク・リード導線チェック）は削除する:

```
あなたはSODAの週次レビュー担当（Analyst兼CEO）です。以下のデータから週次レビューを行い、結果を保存してください。

## 出力1: 週次数字レビュー（logs/weekly/{today}.md に保存）
- 冒頭に必ず「今週のフォロワー純増: +N（X人→Y人）」を書く（北極星KPI）
- 記事別ビュー・スキ、土日記事vs平日記事の比較、商品化トリガー判定（フォロワー50以上 or 実録記事週300ビュー以上で「★商品化トリガー到達」）
- 導線チェック: 今週公開した各記事がマガジンに入っているか・フォローCTAがあるか（logs/daily/*_magazine.txt とcontent/note/の末尾で確認）

## 出力2: 翌週方針（docs/weekly_direction.md に上書き保存）
- 来週のテーマ方向1〜3個（今週数字の学びから。CEOが毎朝の即応ゲート判定・土日テーマ選定で参照する）
- 今週の「出す/出さない」判断の振り返り（メモ日リストと公開記事の反応を突き合わせ、ゲート基準の調整提案）
- WebSearchで note.com/contests と noteのお題企画を確認し、来週相乗りできるものがあれば記載（なければ「該当なし」）

## 出力3: 資産ファイルの更新
- audience/winning_topics.md: 今週の記事で**実測100ビュー以上**のものだけを勝ちパターンとして追記（100未満は絶対に「勝ち」と記録しない。過去の数字インフレの再発防止）
- audience/personas.md: 実測データがターゲット仮説（27〜35歳の発信・副業・AI活用層）を支持/反証するかの検証メモを1〜3行追記
```

`run_claude` の呼び出しに `tools=["Read", "Write", "Edit", "Glob", "Grep", "WebSearch"]` を明示する（既存呼び出しにtools指定がなければ追加。WebSearchとWrite/Editが必須）。

- [ ] **Step 2: 検証**

Run: `python3 scripts/weekly_analysis.py --dry-run > /tmp/weekly_prompt.txt 2>&1; echo "exit: $?" && grep -c "フォロワー純増\|weekly_direction.md\|100ビュー以上\|note.com/contests" /tmp/weekly_prompt.txt && grep -c "商品タネバンク\|アイデア資産バンク\|リード導線" /tmp/weekly_prompt.txt; echo "(2つ目のgrepは0が期待値)"`
Expected: exit 0 / 1つ目 4 / 2つ目 0

- [ ] **Step 3: コミット**

```bash
git add scripts/weekly_analysis.py
git commit -m "週次レビューを統合改組（北極星KPI・翌週方針・勝ちパターン機械基準・コンテスト確認）"
```

---

### Task 5: 汚染浄化とドキュメント同期

**Files:**
- Modify: `audience/winning_topics.md`（X遺物削除・100ビュー基準で書き直し）、`audience/personas.md`（ターゲット修正）、`docs/content_strategy.md`（全面改訂）、`CLAUDE.md`（想定読者・制作ルール同期）、`funnel/email/` 内のX誘導文言除去
- Move: `experiments/` の2026-04から放置の4ファイル → `experiments/archive/`

- [ ] **Step 1: winning_topics.md を書き直す**

X時代の「確定勝ちパターン（構造解説型テンプレート等、実在しない scripts/x_post.py・docs/x_strategy.md への参照を含む）」を全削除し、次の骨格に:

```markdown
# 勝ちトピック

**記録基準（2026-08-13改訂）**: 実測100ビュー以上の記事のみ「勝ち」として記録する。100未満の記事をここに書くことを禁止する（過去に8ビューを「バズ」と記録した数字インフレの再発防止）。週次レビューが自動更新する。

## 実測勝ちパターン

- Kimi K3、公開後24時間で整理する（2026-07-28公開・実測131ビュー）: 大ニュース翌日の「整理・深掘り」型。イベント即応制の根拠
```

- [ ] **Step 2: personas.md のターゲットを修正する**

主ペルソナを「27〜35歳の発信・副業・AI活用層（実測ベースの検証中仮説。2026-08-13の監査で、従来の20代仮説は114日間未検証・反応実態と乖離と判定）」に更新。旧「20代」記述は「参考: 旧仮説」として残す（削除しない — 検証履歴として価値がある）。

- [ ] **Step 3: content_strategy.md を全面改訂する**

新戦略に書き換え: 北極星=週次フォロワー純増 / 曜日編成表（平日=イベント即応制・週2〜3本目安、土=週間まとめ、日=実録）/ ターゲット=27〜35歳発信・副業層 / 商品ロードマップ（現行のトリガー・価格を維持）/ 検証=2026-11月中旬に「実録中央値がニュースの3倍 or スキ30 or フォロワー25」未達なら戦略見直し（反証可能な数値で固定）/ 手動運用メモ（コンテストは週次レビューが自動確認に変更）。

- [ ] **Step 4: CLAUDE.md を同期する**

「想定読者」セクションを新ターゲットに更新（27〜35歳の発信・副業・AI活用層を主に、若手も副として残す）。「運用方針」の「毎日少なくとも1つは前進する」は維持しつつ、「制作ルール」に「公開は量より発見性。伸びる型（即応深掘り・週間まとめ・実録）以外は公開しない」を追加。

- [ ] **Step 5: funnel/email のX文言除去と experiments のアーカイブ**

`grep -rn "X\b\|Twitter\|@SODA_LABO" funnel/` でヒットした誘導文言を除去または note 誘導に差し替え。`experiments/` 配下で2026-04月以降更新のないファイルを `experiments/archive/` に `git mv`。

- [ ] **Step 6: 検証**

Run: `grep -rn "x_post\|x_strategy\|構造解説型テンプレート" audience/ ; echo "exit:$?" && grep -c "100ビュー" audience/winning_topics.md && grep -c "27〜35歳" audience/personas.md docs/content_strategy.md CLAUDE.md`
Expected: `exit:1`（X遺物ゼロ）、各ファイルに新基準・新ターゲットあり

- [ ] **Step 7: コミット**

```bash
git add audience/winning_topics.md audience/personas.md docs/content_strategy.md CLAUDE.md funnel/ experiments/
git commit -m "汚染浄化とターゲット修正（winning_topics機械基準・27-35歳層・戦略文書改訂）"
```

---

### Task 6: 廃止スクリプト7本の削除

**Files:**
- Delete: `scripts/run_meeting.py`、`scripts/run_post_analysis.py`、`scripts/run_idea_mining.py`、`scripts/run_product_memo.py`、`scripts/run_product_meeting.py`、`scripts/run_lead_funnel_check.py`、`scripts/run_list_check.py`

- [ ] **Step 1: 生存参照チェック**

Run: `grep -rln "run_meeting\|run_post_analysis\|run_idea_mining\|run_product_memo\|run_product_meeting\|run_lead_funnel_check\|run_list_check" scripts/ src/ agents/ docs/content_strategy.md --include="*.py" --include="*.md" | grep -v "daily_report.py"`
Expected: 削除対象自身のみ。**daily_pipeline.py のプロンプト内に `logs/meeting/{ds}_meeting.md` 等の廃止ジョブ産出物への参照が残っていないかも確認**し、残っていれば「ファイルが存在しない場合はスキップしてよい」の既存文言で無害か判断（無害なら残置可・レポートに記載。パイプラインが会議ログを必須としていれば NEEDS_CONTEXT 報告）

- [ ] **Step 2: 削除とコミット**

```bash
git rm scripts/run_meeting.py scripts/run_post_analysis.py scripts/run_idea_mining.py \
  scripts/run_product_memo.py scripts/run_product_meeting.py scripts/run_lead_funnel_check.py \
  scripts/run_list_check.py
git commit -m "演劇ジョブ7本を削除（機能は週次レビューとnote_metricsに吸収済み）"
```

Run: `python3 -c "import sys; sys.path.insert(0,'.'); from src.pipelines.daily_pipeline import build_pipeline_prompt; print('import OK')"`

---

### Task 7: crontab 更新と最終検証

**Files:**
- Modify: ユーザーcrontab。バックアップを `logs/ops/crontab_backup_2026-08-13.txt` に保存

- [ ] **Step 1: バックアップ**

```bash
mkdir -p logs/ops && crontab -l > logs/ops/crontab_backup_2026-08-13.txt && wc -l logs/ops/crontab_backup_2026-08-13.txt
```

- [ ] **Step 2: 編集（目視→適用の2段階）**

削除7行: run_meeting(7:30)・run_post_analysis(8:45)・run_idea_mining(9:00)・run_product_memo(21:00)・run_product_meeting(水20:00)・run_lead_funnel_check(金19:00)・run_list_check(21:15)。
追加1行: `0 9 * * * /Users/rikubon50/.pyenv/shims/python3 /Users/rikubon50/Desktop/SODA_LABO/scripts/health_check.py >> /Users/rikubon50/Desktop/SODA_LABO/logs/cron/health_check.log 2>&1`
まず `crontab -l | grep -v ... ` の出力を目視確認してから `| crontab -` 付きで適用する。

- [ ] **Step 3: 検証**

Run: `crontab -l | grep -c "run_meeting\|post_analysis\|idea_mining\|product_memo\|product_meeting\|lead_funnel\|list_check"; crontab -l | grep -c "run_daily\|note_metrics\|weekly_analysis\|health_check\|cleanup_logs"; crontab -l | wc -l`
Expected: `0` / `5` / `6行`（BASH_ENV行+5ジョブ）

- [ ] **Step 4: 全体最終検証**

Task 3 Step 4・Task 4 Step 2 の検証を再実行。`python3 scripts/health_check.py --date 2026-08-12 --dry-run` 正常。

- [ ] **Step 5: コミット**

```bash
git add logs/ops/crontab_backup_2026-08-13.txt
git commit -m "crontabを5本構成に（演劇ジョブ7本削除・沈黙検知追加）"
```

---

## 実装後の運用検証

1. 明朝8:07（平日）: 即応ゲートが判定し、出す日は通常公開/出さない日は `{ds}_memo.md`+`{ds}_no_publish.txt` が生成される
2. 明朝9:00: health_check が前日分を検査して正常終了
3. 8/15(土)・8/16(日): まとめ・実録が現行どおり動く（回帰なし）
4. 8/16(日)21:30: 統合週次レビュー初回 — 「フォロワー純増」冒頭表示・weekly_direction.md 生成・コンテスト確認
