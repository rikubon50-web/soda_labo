"""
Claude CLI 呼び出しサービス。

改善点:
- ストリーミング出力（プロセス実行中にリアルタイムでログへ書き込む）
- タイムアウト付きプロセス管理（ハング防止）
- リトライ + フォールバックモデル
- stderr/stdout 分離キャプチャ
- 失敗時に詳細なエラー情報を返す
"""
import subprocess
import threading
import time
import logging
from dataclasses import dataclass
from pathlib import Path

from src.config import (
    CLAUDE_BIN, FALLBACK_MODEL,
    PIPELINE_TIMEOUT, PIPELINE_RETRIES, PIPELINE_WAIT,
    SODA_DIR,
)

logger = logging.getLogger(__name__)


@dataclass
class ClaudeResult:
    returncode: int
    stdout: str
    stderr: str
    attempt: int
    elapsed: float

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    def error_summary(self) -> str:
        lines = []
        if self.stderr:
            lines.append(f"stderr: {self.stderr[-600:]}")
        if self.stdout and not self.ok:
            lines.append(f"stdout末尾: {self.stdout[-200:]}")
        return "\n".join(lines) if lines else "（出力なし）"


def run_claude(
    prompt: str,
    tools: list[str] | None = None,
    timeout: int = PIPELINE_TIMEOUT,
    model: str | None = None,
    fallback_model: str = FALLBACK_MODEL,
    max_retries: int = PIPELINE_RETRIES,
    retry_wait: int = PIPELINE_WAIT,
    stream_log: Path | None = None,
) -> ClaudeResult:
    """
    Claude CLI をサブプロセスで実行する。

    stream_log が指定されれば、stdout をリアルタイムでそのファイルに追記する。
    失敗時は最大 max_retries 回リトライ。
    """
    tool_list = tools or ["Read", "Write", "Edit", "Glob"]
    cmd = [
        CLAUDE_BIN, "-p",
        "--dangerously-skip-permissions",
        "--allowedTools", ",".join(tool_list),
        "--fallback-model", fallback_model,
    ]
    if model:
        cmd += ["--model", model]

    last_result = ClaudeResult(returncode=1, stdout="", stderr="", attempt=0, elapsed=0.0)

    for attempt in range(1, max_retries + 1):
        logger.info(f"Claude 試行 {attempt}/{max_retries} (timeout={timeout}s)")
        t0 = time.monotonic()

        try:
            result = _run_with_stream(cmd, prompt, timeout, stream_log)
            elapsed = time.monotonic() - t0
            last_result = ClaudeResult(
                returncode=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                attempt=attempt,
                elapsed=elapsed,
            )

            if last_result.ok:
                logger.info(f"Claude 完了 (試行{attempt}, {elapsed:.0f}秒, stdout={len(last_result.stdout)}字)")
                return last_result

            logger.warning(
                f"Claude 失敗 (試行{attempt}, exit={result.returncode}, {elapsed:.0f}秒)\n"
                f"{last_result.error_summary()}"
            )

        except subprocess.TimeoutExpired as e:
            elapsed = time.monotonic() - t0
            logger.error(f"Claude タイムアウト (試行{attempt}, {elapsed:.0f}秒経過)")
            _log_append(stream_log, f"[試行{attempt} タイムアウト: {timeout}秒]\n")
            last_result = ClaudeResult(
                returncode=1, stdout="", stderr="TimeoutExpired",
                attempt=attempt, elapsed=elapsed,
            )

        if attempt < max_retries:
            logger.info(f"  {retry_wait}秒後にリトライ...")
            _log_append(stream_log, f"[試行{attempt} 失敗。{retry_wait}秒後にリトライ]\n")
            time.sleep(retry_wait)

    return last_result


def _run_with_stream(
    cmd: list[str],
    prompt: str,
    timeout: int,
    stream_log: Path | None,
) -> subprocess.CompletedProcess:
    """
    subprocess.Popen でストリーミング実行。
    stdout をリアルタイムで stream_log に書き込みつつ、完了後に全文字列も返す。
    timeout 超過でプロセスを kill して TimeoutExpired を raise する。
    """
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(SODA_DIR),
    )

    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []

    def _read_stdout():
        log_fh = open(stream_log, "a", encoding="utf-8") if stream_log else None
        try:
            for line in proc.stdout:
                stdout_chunks.append(line)
                if log_fh:
                    log_fh.write(line)
                    log_fh.flush()
        finally:
            if log_fh:
                log_fh.close()

    def _read_stderr():
        for line in proc.stderr:
            stderr_chunks.append(line)

    t_out = threading.Thread(target=_read_stdout, daemon=True)
    t_err = threading.Thread(target=_read_stderr, daemon=True)
    t_out.start()
    t_err.start()

    try:
        proc.stdin.write(prompt)
        proc.stdin.close()
        t_out.join(timeout=timeout)
        t_err.join(timeout=5)
    except BrokenPipeError:
        pass

    if t_out.is_alive():
        proc.kill()
        t_out.join()
        t_err.join()
        raise subprocess.TimeoutExpired(cmd, timeout)

    proc.wait()
    return subprocess.CompletedProcess(
        cmd,
        returncode=proc.returncode,
        stdout="".join(stdout_chunks),
        stderr="".join(stderr_chunks),
    )


def _log_append(path: Path | None, text: str) -> None:
    if not path:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(text)
