"""Chạy lệnh con của installer VieNeu (uv, warmup): log ra file, huỷ/timeout → diệt CẢ CÂY tiến trình."""

import asyncio
import os
from pathlib import Path
import subprocess
import time
from typing import Optional

from src.core.offline_voice_model_store import DownloadCancelled
from src.core.tts_service import no_console_window_flags

LONG_TIMEOUT_S = 3600   # đo thực tế: cài thư viện ~14 phút trên mạng chậm


def kill_process_tree(proc: subprocess.Popen) -> None:
    """Windows: `taskkill /T /F` (uv sinh tiến trình con build wheel giữ khoá file); nơi khác: kill tiến trình chính."""
    if os.name == "nt" and proc.poll() is None:
        try:
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True, timeout=15,
                           creationflags=no_console_window_flags())
        except (OSError, subprocess.SubprocessError):
            pass   # rơi xuống proc.kill() bên dưới
    try:
        proc.kill()
    except OSError:
        pass
    proc.wait()


def run_logged_command(cmd: list[str], env: dict, log_file: Path, cancel: Optional[asyncio.Event],
                       timeout_s: float = LONG_TIMEOUT_S) -> None:
    """Chạy lệnh con (đồng bộ, gọi qua to_thread): stdout+stderr ghi vào log; huỷ → kill; mã lỗi ≠ 0 → RuntimeError kèm đuôi log."""
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("ab") as log:
        log.write(f"\n$ {' '.join(cmd)}\n".encode("utf-8"))
        log.flush()
        proc = subprocess.Popen(cmd, env=env, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                creationflags=no_console_window_flags())
        deadline = time.monotonic() + timeout_s
        try:
            while proc.poll() is None:
                if cancel is not None and cancel.is_set():
                    raise DownloadCancelled()
                if time.monotonic() > deadline:
                    raise RuntimeError("Lệnh cài đặt quá thời gian chờ.")
                time.sleep(0.3)
        except BaseException:
            kill_process_tree(proc)
            raise
    if proc.returncode != 0:
        tail = log_file.read_text(encoding="utf-8", errors="replace")[-400:]
        raise RuntimeError(f"Lệnh cài đặt lỗi (mã {proc.returncode}). Xem log: {log_file}\n{tail}")
