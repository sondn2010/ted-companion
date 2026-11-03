"""
Chạy coroutine nền trên event loop qasync, ghi mọi exception vào $TED_HOME/ted.log
thay vì để "Task exception was never retrieved" bị nuốt mất.
"""

import asyncio
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Coroutine

logger = logging.getLogger("ted")

# Event loop chỉ giữ weak reference tới task → giữ tham chiếu mạnh tới khi task xong
_running_tasks: set = set()


def configure_ted_file_logging(data_dir: Path) -> None:
    """Gắn RotatingFileHandler (1MB × 3) cho logger "ted". Gọi 1 lần từ main.py."""
    log_file = data_dir / "ted.log"
    if any(isinstance(h, RotatingFileHandler) for h in logger.handlers):
        return
    handler = RotatingFileHandler(log_file, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def _log_task_failure(task: asyncio.Future) -> None:
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        name = task.get_name() if hasattr(task, "get_name") else "task"
        logger.error("Tác vụ nền '%s' lỗi", name, exc_info=exc)


def spawn_background_task(coro: Coroutine, name: str) -> asyncio.Future:
    task = asyncio.ensure_future(coro)
    if hasattr(task, "set_name"):
        task.set_name(name)
    _running_tasks.add(task)
    task.add_done_callback(_running_tasks.discard)
    task.add_done_callback(_log_task_failure)
    return task
