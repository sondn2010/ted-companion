"""
Workaround Python 3.15 (PEP 810 lazy import) + PySide6.

Nguyên nhân gốc: sau `import shiboken6`, đọc tên từ module `concurrent.futures` qua module khác
(vd asyncio.base_events.concurrent.futures.ThreadPoolExecutor) trả về đối tượng <lazy_import> chưa resolve
→ run_in_executor / asyncio.to_thread (openai) lỗi "'lazy_import' object is not callable".
Import trực tiếp các tên bên dưới ở đây sẽ ép resolve. PHẢI import module này TRƯỚC PySide6 / src.*.
"""

from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor  # noqa: F401

try:  # chỉ có từ Python 3.14+
    from concurrent.futures import InterpreterPoolExecutor  # noqa: F401
except ImportError:
    pass
