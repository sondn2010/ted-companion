"""Gate cuộc họp của coach dùng đúng CalendarEventRepository thật của module work (không đoán chữ ký)."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from src.engines.coach.meeting_overlap_provider import in_meeting
from src.engines.work.calendar_event_cache_model_and_repository import CalendarEventCache


def test_in_meeting_true_only_while_timed_event_runs_and_ignores_all_day(memory_engine):
    from sqlmodel import Session

    now = datetime(2026, 10, 19, 3, 0, tzinfo=timezone.utc)
    with Session(memory_engine) as session:
        session.add(CalendarEventCache(
            key="e1", title="Họp", start_at=now - timedelta(minutes=10),
            end_at=now + timedelta(minutes=20), all_day=False, fetched_at=now,
        ))
        session.add(CalendarEventCache(
            key="e2", title="Nghỉ phép", start_at=now - timedelta(hours=3),
            end_at=now + timedelta(hours=21), all_day=True, fetched_at=now,
        ))
        session.commit()
    with_work = SimpleNamespace(find_by_engine=lambda _e: [object()])
    no_work = SimpleNamespace(find_by_engine=lambda _e: [])
    assert in_meeting(memory_engine, now, with_work) is True
    assert in_meeting(memory_engine, now + timedelta(hours=2), with_work) is False
    # cache lịch còn sót nhưng không có module work đang bật → không được làm coach im lặng
    assert in_meeting(memory_engine, now, no_work) is False and in_meeting(memory_engine, now) is False
