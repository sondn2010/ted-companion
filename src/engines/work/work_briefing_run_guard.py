"""Quy tắc chống chồng chéo cho briefing: mốc briefing gần nhất (KV), khoảng cách tối thiểu, lúc nào không được đọc to, mốc email."""

from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

from src.core.focus_engine import FocusState
from src.engines.work.meeting_overlap_gate import is_in_meeting

LAST_BRIEFING_AT_KEY = "work.last_briefing_at"  # ISO UTC của briefing bắn gần nhất (bất kể slot / bấm tay)
MIN_BRIEFING_GAP = timedelta(minutes=60)  # slot định kỳ không bắn nếu vừa có briefing trong khoảng này
PIPELINE_DEADLINE_SECS = 40.0  # trần cho cả nền: email + Hermes viết lại (TTS không tính)
LATE_RESULT_SECS = 15.0  # quá mốc này mà bubble không còn hiện bản của ta → không hiện lại, không đọc


def read_last_briefing_at(kv) -> Optional[datetime]:
    """Đọc mốc briefing gần nhất (aware UTC); thiếu / hỏng → None."""
    raw = kv.get(LAST_BRIEFING_AT_KEY) if kv is not None else None
    if not raw:
        return None
    try:
        moment = datetime.fromisoformat(raw)
    except (TypeError, ValueError):
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def write_last_briefing_at(kv, now: datetime) -> None:
    kv.set(LAST_BRIEFING_AT_KEY, now.astimezone(timezone.utc).isoformat())


def briefed_recently(now: datetime, last: Optional[datetime]) -> bool:
    """True nếu briefing gần nhất cách `now` < 60 phút (mốc ở tương lai = đồng hồ lệch → coi như không gần)."""
    return last is not None and timedelta(0) <= now - last < MIN_BRIEFING_GAP


def speech_suppressed(ctx, calendar_repo) -> bool:
    """Đang deep work hoặc đang họp → chỉ bubble, không đọc to."""
    focus = getattr(ctx, "focus_engine", None)
    if focus is not None and getattr(focus, "state", None) in (FocusState.DEEP_WORK_RUNNING, FocusState.MEETING_RUNNING):
        return True
    return is_in_meeting(calendar_repo)


def email_since(slot_is_midday: bool, previous_at: Optional[datetime], now: datetime) -> Optional[datetime]:
    """Trưa: email từ lúc briefing trước (nếu hôm nay, giờ local) thay vì cửa sổ cố định; ngược lại None."""
    if not slot_is_midday or previous_at is None:
        return None
    if previous_at.astimezone().date() != now.astimezone().date() or previous_at > now:
        return None
    return previous_at


def mark_briefing_fired(kv, now: datetime, date_keys: Iterable[str]) -> Optional[datetime]:
    """Ghi ngày local vào date_keys + mốc thời điểm; trả mốc trước đó (None nếu chưa có) làm mốc "email từ lần trước"."""
    previous = read_last_briefing_at(kv)
    for key in date_keys:
        kv.set(key, now.date().isoformat())
    write_last_briefing_at(kv, now)
    return previous
