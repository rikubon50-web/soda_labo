# 設計書: X全面撤退とnoteメトリクスへの学習ループ切替

日付: 2026-08-11
状態: 承認待ち

## 背景と目的

スコープ縮小のため、X（旧Twitter）関連の機能を全面撤退し、SODAをnote完結のメディアにする。

判断の根拠:
- Xメトリクス取得は 2026-05-29 を最後に停止しており（`logs/metrics/` 最終ファイル）、学習ループは既に定性評価のみで回っている。Xを消しても定量フィードバックは失われない（既に失われていた）
- note投稿は Playwright + 保存済みセッション（`.browser_profile/note`）で安定稼働しており、同じ仕組みでnoteダッシュボードの計測が可能

決定済みの設計判断:
1. 学習ループの餌は **noteメトリクス（ビュー・スキ）に切替** える
2. note記事末尾CTAは **noteフォロー誘導** に差し替える

## 消すもの

### cron（4本削除・1本差替）

| 時刻 | ジョブ | 処置 |
|------|--------|------|
| 12:00 | `x_post.py --post 2`（昼X投稿） | 削除 |
| 18:00 | `run_cta_review.py`（X CTAレビュー） | 削除 |
| 20:00 | `x_post.py --post 3`（夜X投稿） | 削除 |
| 日曜21:00 | `run_keyword_review.py`（Xキーワードレビュー） | 削除 |
| 22:30 | `fetch_metrics.py`（Xメトリクス取得） | `note_metrics.py` に差替 |

21:15の `run_list_check.py`（リード導線確認）はX専用ではないため残す。

### スクリプト・設定（git履歴に残るため完全削除）

- `scripts/x_post.py`、`scripts/auto_reply.py`、`scripts/remind_reply.py`
- `scripts/run_keyword_review.py`、`scripts/run_cta_review.py`、`scripts/fetch_metrics.py`
- `scripts/run_show_gen.py`、`scripts/shows/` 一式（ショーはaitsm唯一で停止済み、かつX投稿生成が前提の機構）
- `config/reply_keywords.json`
- `docs/x_strategy.md`、`docs/x_profile_copy.md`、`docs/x_reply_api_memo.md`

### daily_pipeline.py から除去するもの

- Step 4 の「X投稿3本」執筆指示（note記事と短尺動画台本は残す）
- Step 8（X朝投稿）と `run_x_post()` 関数
- ショーモード分岐一式（`get_show_mode()`・`run_show_gen()`・`STOPPED_SHOWS`・関連ロジック）
- Step 10 の `run_fetch_metrics()` は note 版の呼び出しに差替
- **二重実行ガードの変更（重要）**: 現在は `content/x_posts/{ds}_*.md` の存在でパイプライン実行済みを判定している。これを `content/note/{ds}_*.md` の存在判定に変更する

### エージェント定義・ガイドから除去するもの

- `agents/writer.md`: 「X投稿のフォーマット（構造解説型 / 標準）」節を削除。note末尾CTA定型文を下記のnoteフォロー版に差替
- `agents/editor.md`: X投稿チェック項目（ハッシュタグ確認等）を削除
- `agents/ceo.md`・`agents/secretary.md`・`agents/REGISTRY.md`: X関連の記述を削除
- `agents/analyst.md`: Xメトリクスアナリスト → noteメトリクスアナリストに書き換え（分析対象: 記事別ビュー・スキ・テーマ/フックとの相関）

## 置き換えるもの

### 1. `scripts/note_metrics.py`（新規）

- `note_post.py` と同じ Playwright + `.browser_profile/note` セッションで note のダッシュボード（アクセス状況ページ）を開き、記事別のビュー・スキ・コメント数を取得する
- 保存先: `logs/metrics/{YYYY-MM-DD}.json`（X版と同じディレクトリ。形式は `{"date": ..., "articles": [{"title", "url", "views", "likes", "comments"}]}`）
- cron 22:30 に登録（旧 fetch_metrics の枠）
- 失敗時は既存の `notify_error.py` 経路で通知し、exit 1（他ジョブに影響しない）

### 2. `scripts/run_post_analysis.py`（書き換え）

- 「X投稿データアナリスト」→「note記事アナリスト」に役割変更
- 入力: 前日のnote記事本文 + `logs/metrics/` のnoteメトリクス（存在すれば）+ 過去7日のメトリクス推移
- メトリクスが未取得の日は現行同様、記事内容の定性評価にフォールバック
- **出力ファイル名は現行維持**: `logs/daily/{ds}_post_analysis.md`（朝会議とデイリーパイプラインが読むため、下流の変更は不要）

### 3. `scripts/run_meeting.py`・`scripts/weekly_analysis.py`（書き換え）

- プロンプト内のX参照（Xメトリクス・X投稿・フォロワー）をnote参照（noteメトリクス・記事・フォロワー/スキ）に書き換え
- ジョブの時刻・頻度は変更しない

### 4. note末尾CTA定型文（`agents/writer.md` の定型文差替）

```
---

**毎日、AIニュースを1本ずつ構造解説しています**

「何が起きたか」だけでなく「なぜ起きているか」まで整理して、毎朝更新中。
フォローすると明日の解説が届きます。
```

（ハッシュタグ5つのルールは現行維持）

## スコープ外（やらないこと）

- 公開済み記事（約90本）に残るXフォローCTAの遡及修正 — リスクの割に益が薄い。放置
- `scripts/daily_report.py` — cron未登録の休眠スクリプト。X参照を含むが今回は触らない（別途整理）
- `logs/tweet_ids/`・過去のXメトリクスJSON — 過去データとして温存
- Xアカウント（@SODA_LABO）自体の削除・非公開化 — ユーザーの手作業領域
- X撤退に伴う `docs/brand.md`・`docs/funnel_status.md` 等の戦略ドキュメント全面改訂 — 実害のあるX参照（エージェントが毎日読むファイル）のみ対象

## エラー処理方針

既存方針を踏襲。note_metrics の失敗は通知のみでパイプラインを止めない。post_analysis はメトリクス欠損時に定性評価へフォールバック（現行の実態と同じ）。

## 検証方法

1. **実装直後**: `crontab -l` でX関連4本の消滅と22:30の差替を確認。`build_pipeline_prompt()` 出力に「X投稿」「x_posts」が含まれないことを assert。`grep -ri "x_post\|X投稿" agents/ src/` で残存参照ゼロを確認（意図的に残すログ・スコープ外ファイルを除く）。`note_metrics.py` を手動実行して JSON が生成されることを確認
2. **翌朝の cron 実行後**: パイプラインがX工程なしで完走し note 公開まで到達すること、`logs/daily/{ds}_post_analysis.md` がnote版フォーマットで生成されることを確認
