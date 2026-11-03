"""Quy tắc nhắc họp (thuần, không I/O). Mỗi mốc bắn đúng 1 lần, mở app muộn không bắn mốc đã qua."""

from datetime import datetime, timedelta
from typing import Any

from src.engines.work.calendar_contract_schemas import to_utc


def fired_key(event_key: str, offset: int) -> str:
    return f"{event_key}|{offset}"


def compute_due_reminders(events, now: datetime, offsets: list[int], fired: set[str]) -> list[tuple[Any, int, set[str]]]:
    """
    Với mỗi sự kiện có giờ (không cả ngày, start > now): passed = mốc đã tới; bắn mốc NHỎ NHẤT trong passed nếu
    chưa bắn, đồng thời đánh dấu mọi mốc passed. Trả [(event, offset_bắn, các_key_cần_đánh_dấu)].
    """
    now = to_utc(now)
    due = []
    for ev in events:
        start = to_utc(ev.start_at)
        if ev.all_day or start <= now:
            continue
        passed = [o for o in sorted(offsets, reverse=True) if now >= start - timedelta(minutes=o)]
        if not passed:
            continue
        smallest = min(passed)
        if fired_key(ev.key, smallest) in fired:
            continue
        due.append((ev, smallest, {fired_key(ev.key, o) for o in passed}))
    return due


def minutes_until(start: datetime, now: datetime) -> int:
    """Số phút còn lại làm tròn lên (tối thiểu 1) để hiển thị."""
    secs = int((to_utc(start) - to_utc(now)).total_seconds())
    return max(1, -(-secs // 60))
