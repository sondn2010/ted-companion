"""Chuyển callback tiến trình tải giọng đọc thành câu tiếng Việt dễ hiểu cho thanh trạng thái của popup tải.

- total > 0 (byte thật, vd. tải bộ chạy `uv`)      → "Đang tải <nhãn>… 12/17 MB", thanh tiến trình xác định.
- total == 0, nhãn "[n/4] <mô tả>" (cài VieNeu)  → "Bước n/4: <mô tả> …", thanh bận (không xác định).
- total == 0, nhãn thường (Piper/whisper)          → "Đang tải <nhãn>… 12 MB", thanh bận.
"""

import re
from typing import NamedTuple

_STAGE_RE = re.compile(r"^\[(\d+)/(\d+)\]\s*(.*)$")

# Bước dài cần nói rõ thời gian chờ (đo thực tế: bước 3 ~14 phút trên mạng chậm)
_STAGE_TEXT = {
    1: "Tải công cụ cài đặt",
    2: "Tạo môi trường Python",
    3: "Cài thư viện… (có thể mất 10–15 phút, vui lòng không tắt Ted)",
    4: "Tải và thử giọng đọc… (vài phút)",
}


class ProgressView(NamedTuple):
    text: str
    determinate: bool
    permille: int = 0   # 0..1000 khi determinate


def format_download_progress(done: int, total: int, label: str) -> ProgressView:
    if total > 0:
        permille = min(1000, int(done * 1000 / total))
        return ProgressView(f"Đang tải {label}… {done / 1048576:.0f}/{total / 1048576:.0f} MB", True, permille)
    stage = _STAGE_RE.match(label or "")
    if stage:
        number, count, text = int(stage.group(1)), stage.group(2), stage.group(3)
        detail = _STAGE_TEXT.get(number, text)
        if not detail.endswith(")") and not detail.endswith("…"):
            detail += "…"
        return ProgressView(f"Bước {number}/{count}: {detail}", False)
    return ProgressView(f"Đang tải {label}… {done / 1048576:.0f} MB", False)
