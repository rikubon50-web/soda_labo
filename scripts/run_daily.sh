#!/bin/zsh
# SODAデイリーパイプライン cron エントリーポイント
# 旧: run_pipeline.sh → 新: src/pipelines/daily_pipeline.py
#
# cronからは次の1行で実行:
#   7 8 * * * bash -c "ulimit -n 524288 && /Users/rikubon50/Desktop/SODA_LABO/scripts/run_daily.sh"

set -euo pipefail

SODA_DIR="$(cd "$(dirname "$0")/.." && pwd)"

# .env 読み込み（OAuth トークン等を確実に渡す）
if [[ -f "$SODA_DIR/.env" ]]; then
    set -a
    source "$SODA_DIR/.env"
    set +a
fi

export PATH="/Users/rikubon50/.pyenv/shims:/Users/rikubon50/.pyenv/bin:/Users/rikubon50/.local/bin:/usr/local/bin:/usr/bin:/bin"
ulimit -n 524288

PYTHON="${PYTHON_PATH:-/Users/rikubon50/.pyenv/shims/python3}"

exec "$PYTHON" "$SODA_DIR/src/pipelines/daily_pipeline.py" "$@"
