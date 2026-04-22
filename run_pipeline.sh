#!/bin/zsh
# SODAデイリーパイプライン自動実行スクリプト

export PATH="/Users/rikubon50/.pyenv/shims:/Users/rikubon50/.pyenv/bin:/Users/rikubon50/.local/bin:/usr/local/bin:/usr/bin:/bin"
ulimit -n 524288

SODA_DIR="/Users/rikubon50/Desktop/SODA_LABO"
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

## 事前読み込み（Step 1より前に必ず実行）
以下のファイルをRead toolで読み込み、内容を把握した上で各Stepに反映すること。

1. logs/meeting/${TODAY}_meeting.md — 今日の朝会議の決定事項（採用テーマ・Writerへの指示・改善アクション）
2. logs/daily/$(date -v-1d +%Y-%m-%d 2>/dev/null || date --date='yesterday' +%Y-%m-%d)_post_analysis.md — 昨日の投稿分析（何が反応されたか・改善示唆）
3. logs/ideas/$(date -v-1d +%Y-%m-%d 2>/dev/null || date --date='yesterday' +%Y-%m-%d)_ideas.md — 昨日のアイデア資産（活用できる素材・切り口）
4. audience/personas.md — 読者像（PlannerとWriterは企画・文章設計時に必ず参照）
5. audience/pain_points.md — 読者のペインポイント（企画の切り口に使う）
6. audience/winning_topics.md — 反応が取れた確定テーマ（あれば優先的に参考にする）

ファイルが存在しない場合はスキップしてよい。

## Step 1: CEO — 本日の優先テーマ決定
agents/ceo.md を読み、CEOとして本日の優先テーマを決定する。
**朝会議ログ（logs/meeting/${TODAY}_meeting.md）のCEO最終判断・Writerへの指示を最優先で参照すること。**
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
**昨日の投稿分析（post_analysis）で反応が高かった表現・フック・構成を参考にすること。**
**アイデア資産（ideas）に使えるネタ・切り口があれば積極的に取り込むこと。**
**朝会議ログのWriterへの指示がある場合は必ず従うこと。**
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
**必ず以下の編集メモを出力すること（省略禁止）：**
\`\`\`
【編集メモ】
- チェックリスト実施: トーン確認 ✅/❌ | 構成確認 ✅/❌ | 文章確認 ✅/❌
- 変更点: （変更した内容を箇条書き。変更なしの場合も「変更なし」と明記）
- 残課題: （直しきれなかった点があれば記載。なければ「なし」）
\`\`\`

## Step 6: CEO — 最終公開判断（推敲ループ）
agents/ceo.md の「最終公開判断を出すとき」フォーマットで5段階スコアを出す。
スコアが3以下の場合はEditorにStep5をやり直させ、再度CEOが採点する。
これをスコアが4以上になるまで繰り返す。ただし最大3回のやり直しで打ち切る（無限ループ防止）。
スコアが確定したら、以下の形式で logs/daily/${TODAY}_ceo_score.txt に保存する（1行目がスコア数字のみ）：
スコア数字（1行目）
判断理由（2行目以降、2〜3文）
低スコアの主因（スコア3以下の場合のみ。何が足りなかったか1文）

## Step 7: Secretary — 日次ログ記録
agents/secretary.md のログ形式に従い logs/daily/${TODAY}.md を作成して保存する。

## 全体ルール
- 全テキストは日本語
- ユーザーへの確認は不要。CEOがすべての判断を行う
- ファイル保存はWrite/Editツールを使って実際に書き込む"

# ─── コンテンツモード判定 & ショー生成 ──────────────────────────
MODE_FILE="$SODA_DIR/logs/daily/${TODAY}_content_mode.json"
SHOW_MODE=$(python3 -c "
import json, sys
try:
    d = json.load(open('$MODE_FILE'))
    print(d.get('mode', 'normal'))
except Exception:
    print('normal')
" 2>/dev/null)
SHOW_THEME=$(python3 -c "
import json, sys
try:
    d = json.load(open('$MODE_FILE'))
    print(d.get('theme', ''))
except Exception:
    print('')
" 2>/dev/null)

if [[ "$SHOW_MODE" != "normal" && -n "$SHOW_MODE" && -n "$SHOW_THEME" ]]; then
  # 既にショーファイルが生成済みなら重複生成しない
  if ls "$SODA_DIR/content/x_posts/${TODAY}_${SHOW_MODE}"*.md 2>/dev/null | head -1 | grep -q .; then
    echo "[$(date)] ショーファイル生成済み（スキップ）: $SHOW_MODE" >> "$LOG_DIR/${TODAY}_run.log"
  else
    echo "[$(date)] ショーモード検出: $SHOW_MODE / テーマ: $SHOW_THEME" >> "$LOG_DIR/${TODAY}_run.log"
    python3 "$SODA_DIR/scripts/run_show_gen.py" --show "$SHOW_MODE" --theme "$SHOW_THEME" \
      >> "$LOG_DIR/${TODAY}_run.log" 2>&1
    SHOW_EXIT=$?
    if [[ $SHOW_EXIT -ne 0 ]]; then
      notify_error "ショーコンテンツ生成($SHOW_MODE)" "run_show_gen.py が失敗しました（theme: $SHOW_THEME）"
    fi
  fi
fi

# ─── コンテンツ生成スキップ判定（ショーが先に生成した場合）────────
if ls "$SODA_DIR/content/x_posts/${TODAY}"_*.md 2>/dev/null | head -1 | grep -q .; then
  echo "[$(date)] X投稿ファイルが既に存在します（ショー生成済み）。Claudeパイプラインをスキップします。" >> "$LOG_DIR/${TODAY}_run.log"
else
  # ─── Claudeパイプライン（Step 1-7）リトライ付き ──────────────
  CLAUDE_EXIT=1
  for RETRY in 1 2 3; do
    echo "[$(date)] Claudeパイプライン試行 $RETRY/3" >> "$LOG_DIR/${TODAY}_run.log"
    echo "$PROMPT" | "$CLAUDE" -p \
      --dangerously-skip-permissions \
      --allowedTools "Read,Write,Edit,Glob,Grep,Bash" \
      >> "$LOG_DIR/${TODAY}_run.log" 2>&1
    CLAUDE_EXIT=$?
    [[ $CLAUDE_EXIT -eq 0 ]] && break
    if [[ $RETRY -lt 3 ]]; then
      echo "[$(date)] 失敗（exit: $CLAUDE_EXIT）。30秒後にリトライ..." >> "$LOG_DIR/${TODAY}_run.log"
      sleep 30
    fi
  done

  echo "[$(date)] Claude パイプライン完了（exit: $CLAUDE_EXIT）" >> "$LOG_DIR/${TODAY}_run.log"

  if [[ $CLAUDE_EXIT -ne 0 ]]; then
    notify_error "Claudeパイプライン（Step1-7）" "3回リトライ後も失敗しました（exit: $CLAUDE_EXIT）"
    echo "[$(date)] Claudeパイプライン失敗のためStep8以降をスキップ" >> "$LOG_DIR/${TODAY}_run.log"
    exit 1
  fi
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
  SCORE=$(head -1 "$SCORE_FILE" | tr -d '[:space:]')
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

# ─── 完了通知 ────────────────────────────────────────────────
SHOW_INFO=""
if [[ -n "$SHOW_MODE" ]]; then
  SHOW_INFO="ショー: ${SHOW_MODE} / テーマ: ${SHOW_THEME}"
fi
python3 "$SODA_DIR/scripts/notify_error.py" --success "$SHOW_INFO" \
  >> "$LOG_DIR/${TODAY}_run.log" 2>&1
