#!/bin/zsh
# SODAデイリーパイプライン自動実行スクリプト

export PATH="/Users/rikubon50/.pyenv/shims:/Users/rikubon50/.pyenv/bin:/Users/rikubon50/.local/bin:/usr/local/bin:/usr/bin:/bin"

SODA_DIR="/Users/rikubon50/Desktop/SODA"
CLAUDE="/Users/rikubon50/.local/bin/claude"
LOG_DIR="$SODA_DIR/logs/cron"
TODAY=$(date +%Y-%m-%d)

mkdir -p "$LOG_DIR"

cd "$SODA_DIR" || exit 1

# エラー通知関数
notify_error() {
  local step="$1"
  local detail="$2"
  python3 "$SODA_DIR/scripts/notify_error.py" "$step" "$detail" \
    >> "$LOG_DIR/${TODAY}_run.log" 2>&1
}

PROMPT="SODAの本日（${TODAY}）のコンテンツパイプラインを全工程実行する。

## Step 1: CEO — 本日の優先テーマ決定
agents/ceo.md を読み、CEOとして本日の優先テーマを決定する。
content/note/ の直近ファイルを確認してDay Nシリーズの継続判断を行う。
出力形式: agents/ceo.md の「優先テーマを出すとき」フォーマット。

## Step 2: Planner — 企画案5本
agents/planner.md を読み、CEOのテーマに基づいて企画案を5本出す。
出力形式: agents/planner.md の「企画案」フォーマット。

## Step 3: CEO — 企画採否判断
agents/ceo.md の5基準でPlannerの企画案を評価し、採用・保留・棄却を決定する。
出力形式: agents/ceo.md の「企画採否を出すとき」フォーマット。

## Step 4: Writer — 下書き制作
agents/writer.md を読み、採用企画をもとに以下を下書きしてファイルに保存する。
- note記事 → content/note/${TODAY}_[タイトル略称].md
  （Day Nシリーズなら content/drafts/template_day-n_note.md を参照）
  note記事の末尾に agents/writer.md の「note記事ハッシュタグルール」に従い #タグ を5つ付与する。
- X投稿3本 → content/x_posts/${TODAY}_[テーマ略称].md
  （Day Nシリーズなら content/drafts/template_day-n_x.md を参照）
  各投稿の末尾に agents/writer.md の「X投稿ハッシュタグルール」に従い #タグ を5つ付与する（140字制限厳守）。
- 短尺動画台本 → content/short_videos/${TODAY}_[タイトル略称].md
  （Day Nシリーズなら content/drafts/template_day-n_video.md を参照）

## Step 5: Editor — 仕上げ
agents/editor.md を読み、Step4で保存した3ファイルを磨いて上書き保存する。

## Step 6: CEO — 最終公開判断（推敲ループ）
agents/ceo.md の「最終公開判断を出すとき」フォーマットで5段階スコアを出す。
スコアが3以下の場合はEditorにStep5をやり直させ、再度CEOが採点する。
これをスコアが4以上になるまで繰り返す。ただし最大3回のやり直しで打ち切る（無限ループ防止）。
スコアが確定したら、その数字（1〜5の整数のみ）を logs/daily/${TODAY}_ceo_score.txt に1行で保存する。

## Step 7: Secretary — 日次ログ記録
agents/secretary.md のログ形式に従い logs/daily/${TODAY}.md を作成して保存する。

## 全体ルール
- 全テキストは日本語
- ユーザーへの確認は不要。CEOがすべての判断を行う
- ファイル保存はWrite/Editツールを使って実際に書き込む"

# ─── Claudeパイプライン（Step 1-7）───────────────────────────
"$CLAUDE" -p \
  --dangerously-skip-permissions \
  --allowedTools "Read,Write,Edit,Glob,Grep,Bash" \
  "$PROMPT" \
  >> "$LOG_DIR/${TODAY}_run.log" 2>&1
CLAUDE_EXIT=$?

echo "[$(date)] Claude パイプライン完了（exit: $CLAUDE_EXIT）" >> "$LOG_DIR/${TODAY}_run.log"

if [[ $CLAUDE_EXIT -ne 0 ]]; then
  notify_error "Claudeパイプライン（Step1-7）" "Claudeの実行が失敗しました（exit: $CLAUDE_EXIT）"
fi

# ─── Step 8: X朝投稿（1本目）────────────────────────────────
X_FILE=$(ls "$SODA_DIR/content/x_posts/${TODAY}"_*.md 2>/dev/null | head -1)
if [[ -f "$X_FILE" ]]; then
  echo "[$(date)] X朝投稿開始: $X_FILE" >> "$LOG_DIR/${TODAY}_run.log"
  python3 "$SODA_DIR/scripts/x_post.py" "$X_FILE" --post 1 \
    >> "$LOG_DIR/${TODAY}_run.log" 2>&1
  X_EXIT=$?
  echo "[$(date)] X朝投稿完了（exit: $X_EXIT）" >> "$LOG_DIR/${TODAY}_run.log"
  if [[ $X_EXIT -ne 0 ]]; then
    notify_error "X朝投稿" "x_post.py --post 1 が失敗しました（exit: $X_EXIT）\nファイル: $X_FILE"
  fi
else
  echo "[$(date)] X投稿ファイルが見つかりません（スキップ）" >> "$LOG_DIR/${TODAY}_run.log"
  notify_error "X投稿ファイル未作成" "content/x_posts/${TODAY}_*.md が存在しません。Claudeがファイルを生成しなかった可能性があります。"
fi

# ─── Step 9: note.com 投稿 ──────────────────────────────────
NOTE_FILE=$(ls "$SODA_DIR/content/note/${TODAY}"_*.md 2>/dev/null | head -1)
if [[ -f "$NOTE_FILE" ]]; then
  echo "[$(date)] note投稿開始: $NOTE_FILE" >> "$LOG_DIR/${TODAY}_run.log"
  python3 "$SODA_DIR/scripts/note_post.py" "$NOTE_FILE" \
    >> "$LOG_DIR/${TODAY}_run.log" 2>&1
  NOTE_EXIT=$?
  echo "[$(date)] note投稿完了（exit: $NOTE_EXIT）" >> "$LOG_DIR/${TODAY}_run.log"

  if [[ $NOTE_EXIT -ne 0 ]]; then
    notify_error "note投稿" "note_post.py が失敗しました（exit: $NOTE_EXIT）\nファイル: $NOTE_FILE"
    python3 "$SODA_DIR/scripts/send_draft.py" "$NOTE_FILE" \
      >> "$LOG_DIR/${TODAY}_run.log" 2>&1
  fi
else
  echo "[$(date)] note記事ファイルが見つかりません（スキップ）" >> "$LOG_DIR/${TODAY}_run.log"
  notify_error "note記事ファイル未作成" "content/note/${TODAY}_*.md が存在しません。Claudeがファイルを生成しなかった可能性があります。"
fi

echo "[$(date)] 全工程完了" >> "$LOG_DIR/${TODAY}_run.log"

# ─── CEOスコア低評価通知 ────────────────────────────────────
SCORE_FILE="$SODA_DIR/logs/daily/${TODAY}_ceo_score.txt"
if [[ -f "$SCORE_FILE" ]]; then
  SCORE=$(cat "$SCORE_FILE" | tr -d '[:space:]')
  if [[ -n "$SCORE" ]] && [[ "$SCORE" -lt 4 ]]; then
    notify_error "CEOスコア低評価" "3回推敲後もスコア${SCORE}（基準4以上）に達しませんでした。下書き保存済みです。手動で確認・修正・公開してください。"
  fi
fi

# ─── Step 10: Xメトリクス取得 ───────────────────────────────
echo "[$(date)] メトリクス取得開始" >> "$LOG_DIR/${TODAY}_run.log"
python3 "$SODA_DIR/scripts/fetch_metrics.py" --days 1 \
  >> "$LOG_DIR/${TODAY}_run.log" 2>&1
METRICS_EXIT=$?
echo "[$(date)] メトリクス取得完了（exit: $METRICS_EXIT）" >> "$LOG_DIR/${TODAY}_run.log"
if [[ $METRICS_EXIT -ne 0 ]]; then
  notify_error "Xメトリクス取得" "fetch_metrics.py が失敗しました（exit: $METRICS_EXIT）"
fi
