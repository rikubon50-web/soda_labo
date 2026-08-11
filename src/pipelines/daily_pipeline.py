"""
SODAデイリーパイプライン（Step 0-7）Python実装。

run_pipeline.sh のClaudeパイプライン部分を完全に置き換える。
Python f-string を使うため、シェル引用符の問題が構造的に起きない。
各フェーズの成功/失敗を独立して記録する。
"""
import logging
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

# プロジェクトルートを sys.path に追加（cron環境でも確実に動くよう絶対パスで）
_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_ROOT))

from src.config import (
    SODA_DIR,
    CRON_LOG_DIR,
    DAILY_LOG_DIR,
    NOTE_DIR,
    PYTHON_BIN,
    SCRIPTS_DIR,
    PIPELINE_RETRIES,
    PIPELINE_WAIT,
    PIPELINE_TIMEOUT,
)
from src.logger import get_logger
from src.services.claude_service import run_claude

logger = logging.getLogger(__name__)


# ─── プロンプト構築 ────────────────────────────────────────────────

def build_pipeline_prompt(today: date) -> str:
    yesterday = today - timedelta(days=1)
    ds       = today.isoformat()
    ds_prev  = yesterday.isoformat()

    return f"""SODAの本日（{ds}）のコンテンツパイプラインを全工程実行する。

## 事前読み込み（Step 1より前に必ず実行）
以下のファイルをRead toolで読み込み、内容を把握した上で各Stepに反映すること。

1. logs/meeting/{ds}_meeting.md — 今日の朝会議の決定事項（採用テーマ・Writerへの指示・改善アクション）
2. logs/daily/{ds_prev}_post_analysis.md — 昨日の投稿分析（何が反応されたか・改善示唆）
3. logs/ideas/{ds_prev}_ideas.md — 昨日のアイデア資産（活用できる素材・切り口）
4. audience/personas.md — 読者像（PlannerとWriterは企画・文章設計時に必ず参照）
5. audience/pain_points.md — 読者のペインポイント（企画の切り口に使う）
6. audience/winning_topics.md — 反応が取れた確定テーマ（あれば優先的に参考にする）
7. docs/voice_guide.md — 声の基準書（WriterとEditorは必ず参照すること）
8. docs/perspectives.md — SODA視点ライブラリ（CEOとWriterは必ず参照すること）

ファイルが存在しない場合はスキップしてよい。

## Step 0: ニュース収集（Step 1の前に必ず実行）
WebSearch toolで以下のクエリを検索し、本日時点の最新AIニュースを把握する。

- 検索クエリ: "AI news today {ds}"
- 検索クエリ: "生成AI ニュース {ds}"
- 検索クエリ: "AI layoffs OR funding OR acquisition news {ds}"
- 検索クエリ: "AI industry news {ds_prev}"

取得した情報から **本日公開・発表されたもの** に絞り、以下を判断基準にトップ3を選ぶ:
1. 読者（AI・副業・発信に関心ある20代）が「それ知らなかった」と感じるか
2. 「結局なにがすごいのか」を3分で説明できる規模感か
3. 自分ごとにできるか（ツール・働き方・副業への影響）

選んだトップ3をメモしてStep 1のCEOに渡すこと。
ニュースが見つからない・古い情報しかない場合はStep 0をスキップしてよい。

## Step 1: CEO — 本日の優先テーマ決定
agents/ceo.md を読み、CEOとして本日の優先テーマを決定する。
**Step 0で取得した最新ニュースから「AI×お金・雇用・構造転換」3テーマに該当するもの1本を最優先のテーマ候補として選ぶこと（基準は agents/ceo.md「テーマ方針」参照）。**
**該当ニュースがない場合は過去3〜7日から「今振り返ると」型で1本選ぶ。**
**朝会議ログ（logs/meeting/{ds}_meeting.md）のCEO最終判断・Writerへの指示を最優先で参照すること。**
**docs/perspectives.md の「ウォッチ中の仮説」に回収予定時期が到来したものがあれば、その回収をその日のテーマ候補として最優先で検討すること。**
出力形式: agents/ceo.md の「優先テーマを出すとき」フォーマット。

## Step 1.5: Researcher — 一次取材（Step 2の前に必ず実行）
agents/researcher.md を読み、Step 1でCEOが採用したテーマ1本を深掘りする。
- 一次情報（公式発表・プレスリリース・元記事）をWebFetchで実際に開いて読む
- 英語ソースを含む追加検索をWebSearchで3〜5本行う
- 反対意見・懐疑的な見方を最低1つ探す（見つからなければ「探したが見つからなかった」と記録）
- 比較に使える過去の数字（前年・前四半期・類似事例）を集める
取材結果を content/news/{ds}_research.md に agents/researcher.md の「取材ノート」フォーマットで保存する。
一次情報が取得できない場合も、確認できた範囲で取材ノートを保存する（4区分の見出しは維持する）。

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
**note記事の事実・数字は content/news/{ds}_research.md（取材ノート）に記載のあるものだけを使うこと。ノートにない数字は書かない。「未確認事項」の内容は本文でも未確認・報道ベースと明示する。取材ノートが存在しない場合のみStep 0の検索結果ベースで執筆してよい。**
**docs/perspectives.md を読み、接続できる持論・伏線があれば本文で明示的に接続すること（agents/writer.md「SODA視点の接続ルール」参照）。**

- note記事 → content/note/{ds}_[タイトル略称].md
  「AI×お金・雇用・構造転換」3テーマ該当ニュースの深掘り1本（agents/writer.md「note記事のジャンル方針」参照）。
  該当ニュースが当日になければ過去3〜7日から「今振り返ると」型で1本選ぶ。
  記事末尾に agents/writer.md の「note記事ハッシュタグルール」に従い #タグ を5つ付与する。

- 短尺動画台本 → content/short_videos/{ds}_[タイトル略称].md
  当日 note 記事と同じニュースを冒頭3秒インパクト型で 30〜45秒に圧縮。

AI それって本当？／Day N シリーズは新規生成しない。

**文章生成前に `docs/voice_guide.md` の「AI臭いパターン一覧」を確認し、該当パターンが出ていないかを照合してからファイルに保存すること。**

## Step 5: Editor — 仕上げ
agents/editor.md を読み、Step4で保存した3ファイルを磨いて上書き保存する。
**必ず以下の編集メモを出力すること（省略禁止）：**
```
【編集メモ】
- チェックリスト実施: トーン確認 ✅/❌ | 構成確認 ✅/❌ | 文章確認 ✅/❌
- 変更点: （変更した内容を箇条書き。変更なしの場合も「変更なし」と明記）
- 残課題: （直しきれなかった点があれば記載。なければ「なし」）
- 自然さ確認: voice_guide照合 ✅/❌ | AI臭いパターン修正箇所（あれば列挙、なければ「なし」）
```

## Step 5.5: Critic — 敵対的批評（Step 6の前に必ず実行）
agents/critic.md を読み、Step 5でEditorが仕上げたnote記事を採点する。
- docs/voice_guide.md の「AI臭いパターン一覧」と照合する
- agents/critic.md の採点基準（各2点×5項目=10点満点）で採点し、直せる欠点を必ず3つ以上、修正指示として挙げる
- 7点未満の場合: Editorが修正指示に従って記事を書き直し、Criticが再採点する。この書き直しは最大2周まで
- 2周後も7点未満なら打ち切り、そのままStep 6に進む（CEOの減点判断に委ねる）
採点結果（各周の点数と指摘）を logs/daily/{ds}_critic.md に保存する。

## Step 6: CEO — 最終公開判断（推敲ループ）
agents/ceo.md の「最終公開判断を出すとき」フォーマットで5段階スコアを出す。
採点時は自然さも評価すること：`docs/voice_guide.md` の「AI臭いパターン一覧」が原稿に残っている場合はスコアを1点減点する。
スコアが3以下の場合はEditorにStep5をやり直させ、再度CEOが採点する。
これをスコアが4以上になるまで繰り返す。ただし最大3回のやり直しで打ち切る（無限ループ防止）。
スコアが確定したら、以下の形式で logs/daily/{ds}_ceo_score.txt に保存する（1行目がスコア数字のみ）：
スコア数字（1行目）
判断理由（2行目以降、2〜3文）
低スコアの主因（スコア3以下の場合のみ。何が足りなかったか1文）

## Step 7: Secretary — 日次ログ記録
agents/secretary.md のログ形式に従い logs/daily/{ds}.md を作成して保存する。

## Step 7.5: Secretary — 視点ライブラリ更新
docs/perspectives.md を更新して上書き保存する。
- 今日のnote記事に新しい仮説・伏線があれば「ウォッチ中の仮説」に追記する（初出日付と回収予定時期を必ず付す）
- 今日の記事で回収（答え合わせ）した仮説があれば、結果（当たり/外れ/部分的）を添えて「回収済みアーカイブ」へ移動する
- 「ウォッチ中の仮説」が15件を超える場合は、古い・弱いものからアーカイブへ移す

## Step 7.6: 本日記事のマガジン判定
本日のnote記事を以下の3誌のうち最も主題が近い1誌に判定し、誌名のみ（1行）を logs/daily/{ds}_magazine.txt に保存する。
- AIとマネーの定点観測（投資・M&A・資金調達・企業価値）
- AIと雇用のゆくえ（レイオフ・働き方・スキル・組織）
- AI業界の構造転換（企業戦略・競争・規制・技術転換）

## 全体ルール
- 全テキストは日本語
- ユーザーへの確認は不要。CEOがすべての判断を行う
- ファイル保存はWrite/Editツールを使って実際に書き込む"""


# ─── 各フェーズの実行 ─────────────────────────────────────────────

def run_content_pipeline(today: date, run_log: Path) -> bool:
    """Step 0-7 の Claude パイプラインを実行する。成功なら True。"""
    prompt = build_pipeline_prompt(today)

    result = run_claude(
        prompt,
        tools=["Read", "Write", "Edit", "Glob", "Grep", "Bash", "WebSearch", "WebFetch"],
        timeout=PIPELINE_TIMEOUT,
        max_retries=PIPELINE_RETRIES,
        retry_wait=PIPELINE_WAIT,
        stream_log=run_log,
    )

    if not result.ok:
        msg = (
            f"Claudeパイプライン失敗 (試行{result.attempt}/{PIPELINE_RETRIES}, "
            f"exit={result.returncode}, {result.elapsed:.0f}秒)\n"
            f"{result.error_summary()}"
        )
        logger.error(msg)
        _notify_error("Claudeパイプライン（Step0-7）", msg, run_log)
        return False

    return True


def run_note_post(note_file: Path, run_log: Path) -> bool:
    """note_post.py で note.com に投稿する。失敗時は send_draft.py でフォールバック。"""
    step = "note投稿"
    try:
        r = subprocess.run(
            [PYTHON_BIN, str(SCRIPTS_DIR / "note_post.py"), str(note_file)],
            capture_output=True, text=True, timeout=300, cwd=str(SODA_DIR),
        )
        _log_append(run_log, r.stdout + r.stderr)
        if r.returncode != 0:
            _notify_error(step, r.stderr[-500:] or "詳細不明", run_log)
            # フォールバック: メール下書き送信
            subprocess.run(
                [PYTHON_BIN, str(SCRIPTS_DIR / "send_draft.py"), str(note_file)],
                cwd=str(SODA_DIR),
            )
            return False
        return True
    except Exception as e:
        _notify_error(step, str(e), run_log)
        return False


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


def run_note_metrics(run_log: Path) -> bool:
    """note_metrics.py でnoteメトリクスを取得する。"""
    try:
        r = subprocess.run(
            [PYTHON_BIN, str(SCRIPTS_DIR / "note_metrics.py")],
            capture_output=True, text=True, timeout=180, cwd=str(SODA_DIR),
        )
        _log_append(run_log, r.stdout + r.stderr)
        if r.returncode != 0:
            _notify_error("noteメトリクス取得", r.stderr[-300:] or "詳細不明", run_log)
            return False
        return True
    except Exception as e:
        _notify_error("noteメトリクス取得", str(e), run_log)
        return False


# ─── 通知 ──────────────────────────────────────────────────────────

def _notify_error(step: str, detail: str, run_log: Path | None = None) -> None:
    subprocess.run(
        [PYTHON_BIN, str(SCRIPTS_DIR / "notify_error.py"), step, detail],
        cwd=str(SODA_DIR),
    )


def _notify_success(detail: str = "") -> None:
    subprocess.run(
        [PYTHON_BIN, str(SCRIPTS_DIR / "notify_error.py"), "--success", detail],
        cwd=str(SODA_DIR),
    )


def _check_ceo_score(today: date) -> None:
    """CEOスコアが低い場合に通知する。"""
    score_file = DAILY_LOG_DIR / f"{today.isoformat()}_ceo_score.txt"
    if not score_file.exists():
        return
    try:
        score = int(score_file.read_text().splitlines()[0].strip())
        if score < 4:
            _notify_error(
                "CEOスコア低評価",
                f"3回推敲後もスコア{score}（基準4以上）に達しませんでした。手動確認・修正・公開してください。",
            )
    except (ValueError, IndexError):
        pass


def _log_append(path: Path | None, text: str) -> None:
    if not path or not text:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(text)


# ─── メインエントリ ────────────────────────────────────────────────

def main() -> int:
    today    = date.today()
    ds       = today.isoformat()
    run_log  = CRON_LOG_DIR / f"{ds}_run.log"

    CRON_LOG_DIR.mkdir(parents=True, exist_ok=True)
    DAILY_LOG_DIR.mkdir(parents=True, exist_ok=True)

    _log = get_logger("daily_pipeline", run_log)

    # ─ コンテンツパイプライン（Step 0-7）──────────────────────────
    note_files = sorted(NOTE_DIR.glob(f"{ds}_*.md"))
    if note_files:
        _log.info(f"note記事ファイル存在。Claudeパイプラインをスキップ: {note_files[0].name}")
    else:
        _log.info("Claudeパイプライン開始（Step 0-7）")
        ok = run_content_pipeline(today, run_log)
        if not ok:
            _log.error("Claudeパイプライン失敗。note投稿をスキップ")
            return 1
        note_files = sorted(NOTE_DIR.glob(f"{ds}_*.md"))

    # ─ note投稿 ──────────────────────────────────────────────────
    if note_files:
        _log.info(f"note投稿: {note_files[0].name}")
        if run_note_post(note_files[0], run_log):
            _log.info("マガジン追加")
            run_magazine_add(run_log)
    else:
        _notify_error("note記事ファイル未作成", f"content/note/{ds}_*.md が存在しません")
        _log.warning("note記事ファイルが見つかりません")

    # ─ CEOスコア確認 ─────────────────────────────────────────────
    _check_ceo_score(today)

    # ─ noteメトリクス取得 ────────────────────────────────────────
    _log.info("noteメトリクス取得")
    run_note_metrics(run_log)

    # ─ 成功通知 ──────────────────────────────────────────────────
    _notify_success()
    _log.info("全工程完了")
    return 0


if __name__ == "__main__":
    sys.exit(main())
