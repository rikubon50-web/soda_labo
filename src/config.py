"""
SODA 一元設定。全スクリプトがここから参照する。
"""
import os
from pathlib import Path

from dotenv import load_dotenv

SODA_DIR = Path(__file__).parent.parent
load_dotenv(SODA_DIR / ".env")

# Claude CLI
CLAUDE_BIN       = os.path.expanduser("~/.local/bin/claude")
FALLBACK_MODEL   = "claude-haiku-4-5-20251001"
PIPELINE_TIMEOUT = 2700   # 秒（45分）取材・批評工程の追加分を含む
PIPELINE_RETRIES = 5
PIPELINE_WAIT    = 60     # リトライ間隔（秒）

# Python
PYTHON_BIN = os.environ.get("PYTHON_PATH", "/Users/rikubon50/.pyenv/shims/python3")

# ログディレクトリ
LOG_DIR       = SODA_DIR / "logs"
CRON_LOG_DIR  = LOG_DIR / "cron"
DAILY_LOG_DIR = LOG_DIR / "daily"
ERROR_LOG_DIR = LOG_DIR / "errors"

# コンテンツディレクトリ
CONTENT_DIR      = SODA_DIR / "content"
NOTE_DIR         = CONTENT_DIR / "note"
X_POSTS_DIR      = CONTENT_DIR / "x_posts"
SHORT_VIDEOS_DIR = CONTENT_DIR / "short_videos"

# スクリプト
SCRIPTS_DIR = SODA_DIR / "scripts"

# note 公開スコア閾値
PUBLISH_THRESHOLD = 4
