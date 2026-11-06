"""Schemas (tz, cả ngày), repo cache (replace_window, today, overlapping, busy_slots), link họp, tên múi giờ."""

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from src.engines.work.calendar_contract_schemas import CalendarEvent, CalendarResponse
from src.engines.work.calendar_event_cache_model_and_repository import (
    CalendarEventRepository,
    local_day_bounds_utc,
)
from src.engines.work.local_timezone_name import local_timezone_name
from src.engines.work.meeting_link_opener import classify_meeting_url

NOW = datetime(2026, 10, 19, 2, 0, tzinfo=timezone.utc)
FETCHED = datetime(2026, 10, 19, 1, 0, tzinfo=timezone.utc)


def _ev(title="Họp", start=NOW + timedelta(hours=1), **kw) -> CalendarEvent:
    return CalendarEvent(title=title, start=start, **kw)


def test_offset_start_becomes_aware_utc():
    ev = CalendarEvent(title="x", start="2026-10-19T09:00:00+07:00", end="2026-10-19T09:30:00+07:00")
    assert ev.start == datetime(2026, 10, 19, 2, 0, tzinfo=timezone.utc) and ev.start.utcoffset() == timedelta(0)
    assert ev.end.tzinfo is not None


def test_naive_start_is_local_then_utc():
    ev = CalendarEvent(title="x", start="2026-10-19T09:00:00")
    assert ev.start.tzinfo is not None
    assert ev.start == datetime(2026, 10, 19, 9, 0).astimezone(timezone.utc)


def test_date_only_start_is_all_day_and_nulls_become_empty():
    ev = CalendarResponse.model_validate({"events": [
        {"id": None, "title": "Nghỉ lễ", "start": "2026-10-20", "end": "2026-10-21", "location": None, "meet_url": None}
    ]}).events[0]
    assert ev.all_day and ev.id == "" and ev.location == "" and ev.meet_url == ""


def test_missing_start_is_rejected():
    with pytest.raises(ValidationError):
        CalendarResponse.model_validate({"events": [{"title": "x"}]})


def test_replace_window_swaps_only_the_window_atomically(memory_engine):
    repo = CalendarEventRepository(memory_engine)
    day = NOW.replace(hour=0)
    window = (day, day + timedelta(days=2))
    outside = _ev("ngoài cửa sổ", start=day + timedelta(days=5))
    repo.replace_window(day, day + timedelta(days=10), [_ev("cũ"), outside], FETCHED)
    assert repo.replace_window(*window, [_ev("mới"), outside], FETCHED) == 1  # `outside` bị lọc, không ghi đè
    titles = [e.title for e in repo.between(day, day + timedelta(days=10))]
    assert titles == ["mới", "ngoài cửa sổ"]


def test_recurring_events_sharing_id_keep_separate_rows(memory_engine):
    repo = CalendarEventRepository(memory_engine)
    a, b = _ev("Daily", id="r1"), _ev("Daily", start=NOW + timedelta(days=1, hours=1), id="r1")
    assert repo.replace_window(NOW - timedelta(hours=1), NOW + timedelta(days=3), [a, b], FETCHED) == 2


def test_rows_come_back_aware_utc(memory_engine):
    repo = CalendarEventRepository(memory_engine)
    repo.replace_window(NOW - timedelta(hours=1), NOW + timedelta(days=1), [_ev(end=NOW + timedelta(hours=2))], FETCHED)
    row = repo.between(NOW, NOW + timedelta(days=1))[0]
    assert row.start_at.utcoffset() == timedelta(0) and row.end_at.utcoffset() == timedelta(0)


def test_today_uses_local_day_bounds_so_early_morning_meeting_is_kept(memory_engine):
    repo = CalendarEventRepository(memory_engine)
    start_utc, end_utc = local_day_bounds_utc(datetime.now())
    early = _ev("Sáng sớm", start=start_utc + timedelta(minutes=5))
    tomorrow = _ev("Mai", start=end_utc + timedelta(minutes=5))
    repo.replace_window(start_utc - timedelta(days=1), end_utc + timedelta(days=2), [early, tomorrow], FETCHED)
    assert [e.title for e in repo.today()] == ["Sáng sớm"]


def test_overlapping_and_busy_slots_exclude_all_day(memory_engine):
    repo = CalendarEventRepository(memory_engine)
    meeting = _ev("Họp", start=NOW - timedelta(minutes=10), end=NOW + timedelta(minutes=20))
    all_day = _ev("OOO", start=NOW.replace(hour=0), all_day=True, end=NOW + timedelta(days=1))
    later = _ev("Mai", start=NOW + timedelta(days=2))
    far = _ev("Xa", start=NOW + timedelta(days=9))
    repo.replace_window(NOW - timedelta(days=1), NOW + timedelta(days=20), [meeting, all_day, later, far], FETCHED)
    assert [e.title for e in repo.overlapping(NOW, 0)] == ["Họp"]  # cả ngày KHÔNG làm câm coach
    slots = repo.busy_slots(NOW, days_ahead=7)
    assert [s for s, _e in slots] == [meeting.start, later.start]  # không cả ngày, không quá 7 ngày
    assert slots[1][1] - slots[1][0] == timedelta(minutes=60)  # không có end → mặc định 60 phút


def test_overlapping_margin_catches_meeting_about_to_start(memory_engine):
    repo = CalendarEventRepository(memory_engine)
    repo.replace_window(NOW - timedelta(days=1), NOW + timedelta(days=1), [_ev(start=NOW + timedelta(minutes=8))], FETCHED)
    assert repo.overlapping(NOW, 0) == [] and len(repo.overlapping(NOW, 10)) == 1


@pytest.mark.parametrize("url,expected", [
    ("https://meet.google.com/abc-defg", "trusted"),
    ("https://us02web.zoom.us/j/1", "trusted"),
    ("https://evil.example.com/x", "confirm"),
    ("https://meet.google.com.evil.io/x", "confirm"),  # không được khớp đuôi giả
    ("javascript:alert(1)", "blocked"),
    ("file:///C:/Windows/System32/calc.exe", "blocked"),
    ("", "blocked"),
])
def test_meeting_url_classification(url, expected):
    assert classify_meeting_url(url) == expected


def test_local_timezone_name_is_loadable_iana(monkeypatch):
    from zoneinfo import ZoneInfo

    ZoneInfo(local_timezone_name())  # không ném
    assert local_timezone_name("Asia/Ho_Chi_Minh") == "Asia/Ho_Chi_Minh"
    monkeypatch.setenv("TZ", "Not/AZone")
    ZoneInfo(local_timezone_name("also-bad"))  # tên sai bị bỏ qua, vẫn ra tên hợp lệ
