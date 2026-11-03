"""Logic thuần (không I/O) chọn slot briefing: sáng [08:00,12:00) / trưa [12:00,17:00), mỗi slot tối đa 1 lần/ngày local."""

from datetime import datetime, time
from typing import Mapping, Optional

from src.engines.work.work_briefing_run_guard import briefed_recently

MORNING = "morning"
MIDDAY = "midday"

_DEFAULTS = {
    "morning_briefing_time": "08:00",
    "morning_briefing_cutoff": "12:00",
    "midday_briefing_time": "12:00",
    "midday_briefing_cutoff": "17:00",
}


def parse_hhmm(value: object, fallback: str) -> time:
    """"HH:MM" → time; sai định dạng → dùng fallback."""
    for candidate in (value, fallback):
        try:
            hours, minutes = str(candidate).strip().split(":")
            return time(int(hours), int(minutes))
        except (ValueError, TypeError):
            continue
    raise ValueError(f"fallback giờ không hợp lệ: {fallback!r}")


def _window(settings: Mapping, prefix: str) -> tuple[time, time]:
    start_key, end_key = f"{prefix}_briefing_time", f"{prefix}_briefing_cutoff"
    return parse_hhmm(settings.get(start_key), _DEFAULTS[start_key]), parse_hhmm(settings.get(end_key), _DEFAULTS[end_key])


def due_briefing_slot(
    now: datetime,
    settings: Mapping,
    last_morning_date: Optional[str],
    last_midday_date: Optional[str],
    last_briefing_at: Optional[datetime] = None,
) -> Optional[str]:
    """Slot đến hạn (chưa bắn hôm nay, giờ local nằm trong [start, cutoff)); không có → None. `now` là giờ local.
    Vừa có briefing < 60 phút (last_briefing_at, aware) → chưa đến hạn; slot sau sẽ bắn khi qua mốc đó (còn trong cửa sổ)."""
    if briefed_recently(now, last_briefing_at):
        return None
    today, clock = now.date().isoformat(), now.time().replace(second=0, microsecond=0)
    for slot, last in ((MORNING, last_morning_date), (MIDDAY, last_midday_date)):
        start, cutoff = _window(settings, slot)
        if start <= clock < cutoff and last != today:
            return slot
    return None


def slot_for_time(now: datetime, settings: Mapping) -> str:
    """Click/menu thủ công: trước giờ bắt đầu slot trưa = sáng, từ đó trở đi = trưa."""
    midday_start, _ = _window(settings, MIDDAY)
    return MORNING if now.time().replace(second=0, microsecond=0) < midday_start else MIDDAY


def slot_boundary(settings: Mapping) -> time:
    """Mốc chia họp sáng/chiều (= giờ bắt đầu slot trưa)."""
    return _window(settings, MIDDAY)[0]
