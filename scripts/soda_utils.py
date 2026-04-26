#!/usr/bin/env python3
"""
SODA 共通ユーティリティ。
新しいスクリプトはここからインポートして使う。

使い方:
  from soda_utils import SODA_DIR, run_claude, notify_error, write_content_mode, read_content_mode
"""

import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

SODA_DIR = Path(__file__).parent.parent
load_dotenv(SODA_DIR / ".env")

# src/ を sys.path に追加（cron 環境でも確実に動くよう絶対パスで）
_src = str(SODA_DIR / "src")
if _src not in sys.path:
    sys.path.insert(0, str(SODA_DIR))

CLAUDE = os.path.expanduser("~/.local/bin/claude")
PYTHON = os.environ.get("PYTHON_PATH", "/Users/rikubon50/.pyenv/shims/python3")

DEFAULT_TOOLS = ["Read", "Write", "Edit", "Glob"]


def run_claude(
    prompt: str,
    tools: list[str] | None = None,
    timeout: int = 1800,
    model: str | None = None,
    max_retries: int = 3,
    retry_wait: int = 30,
) -> subprocess.CompletedProcess:
    """Claude CLI をサブプロセスで実行して CompletedProcess を返す。失敗時は最大 max_retries 回リトライ。
    内部で src.services.claude_service を使用する。
    """
    from src.services.claude_service import run_claude as _run
    result = _run(
        prompt,
        tools=tools,
        timeout=timeout,
        model=model,
        max_retries=max_retries,
        retry_wait=retry_wait,
    )
    # CompletedProcess 互換オブジェクトを返す
    return subprocess.CompletedProcess(
        args=[],
        returncode=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )


def notify_error(step: str, detail: str) -> None:
    """エラーを Gmail で通知する。"""
    subprocess.run(
        [PYTHON, str(SODA_DIR / "scripts" / "notify_error.py"), step, detail],
        cwd=str(SODA_DIR),
    )


# ── コンテンツモード ────────────────────────────────────────────

def write_content_mode(mode: str, **kwargs) -> None:
    """今日のコンテンツモードを JSON ファイルに書き込む。

    例:
      write_content_mode("normal")
      write_content_mode("aitsm", theme="筋トレすると自己肯定感が上がる説")
    """
    today = str(date.today())
    mode_file = SODA_DIR / "logs" / "daily" / f"{today}_content_mode.json"
    mode_file.parent.mkdir(parents=True, exist_ok=True)
    mode_file.write_text(
        json.dumps({"mode": mode, **kwargs}, ensure_ascii=False, indent=2)
    )


def read_content_mode() -> dict:
    """今日のコンテンツモードを返す。ファイルがなければ {"mode": "normal"}。"""
    today = str(date.today())
    mode_file = SODA_DIR / "logs" / "daily" / f"{today}_content_mode.json"
    if mode_file.exists():
        try:
            return json.loads(mode_file.read_text())
        except json.JSONDecodeError:
            pass
    return {"mode": "normal"}
