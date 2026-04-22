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
import time
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

SODA_DIR = Path(__file__).parent.parent
load_dotenv(SODA_DIR / ".env")

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
    """Claude CLI をサブプロセスで実行して CompletedProcess を返す。失敗時は最大 max_retries 回リトライ。"""
    tool_list = tools if tools is not None else DEFAULT_TOOLS
    cmd = [
        CLAUDE, "-p",
        "--dangerously-skip-permissions",
        "--allowedTools", ",".join(tool_list),
    ]
    if model:
        cmd += ["--model", model]

    result = None
    for attempt in range(1, max_retries + 1):
        result = subprocess.run(
            cmd,
            input=prompt,
            cwd=str(SODA_DIR),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode == 0:
            return result
        if attempt < max_retries:
            print(f"[リトライ {attempt}/{max_retries}] {retry_wait}秒後に再試行...")
            time.sleep(retry_wait)
    return result


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
