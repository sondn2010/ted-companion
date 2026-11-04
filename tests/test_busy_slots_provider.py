"""busy_slots cho [TED_SYNC_PLAN]: che tên mặc định, bỏ sự kiện cả ngày, không có module work → None, đọc từ cache thật."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from src.engines.coach.busy_slots_provider import collect_busy_slots, events_to_busy_slots
from src.engines.work.calendar_contract_schemas import CalendarEvent
from src.engines.work.calendar_event_cache_model_and_repository import CalendarEventRepository

TZ = timezone(timedelta(hours=7))
NOW = datetime(2026, 10, 19, 5, 0, tzinfo=timezone.utc)   # 12:00 giờ VN


def _row(title, start, end=None, all_day=False):
    return SimpleNamespace(title=title, start_at=start, end_at=end, all_day=all_day)


def test_titles_masked_by_default_and_shared_on_opt_in():
    rows = [_row("Họp lương", NOW + timedelta(hours=2), NOW + timedelta(hours=3))]
    assert events_to_busy_slots(rows, False, TZ) == [
        {"start": "2026-10-19T14:00+07:00", "end": "2026-10-19T15:00+07:00", "title": "Bận"}]
    assert events_to_busy_slots(rows, True, TZ)[0]["title"] == "Họp lương"


def test_all_day_skipped_and_missing_end_defaults_to_one_hour():
    rows = [_row("Nghỉ lễ", NOW, None, all_day=True), _row("Họp", NOW + timedelta(hours=1), None)]
    slots = events_to_busy_slots(rows, False, TZ)
    assert len(slots) == 1 and slots[0]["start"].endswith("13:00+07:00") and slots[0]["end"].endswith("14:00+07:00")


def _registry(*work_settings):
    manifests = [SimpleNamespace(settings=s) for s in work_settings]
    return SimpleNamespace(find_by_engine=lambda engine: manifests if engine == "work" else [])


def test_no_work_module_returns_none_and_no_registry_returns_none(memory_engine):
    assert collect_busy_slots(_registry(), memory_engine, NOW, TZ) is None
    assert collect_busy_slots(None, memory_engine, NOW, TZ) is None


def test_week_window_from_real_cache_and_share_setting(memory_engine):
    repo = CalendarEventRepository(memory_engine)
    event = lambda i, start: CalendarEvent(id=i, title=f"Họp {i}", start=start, end=start + timedelta(hours=1))
    events = [event("soon", NOW + timedelta(hours=2)), event("day6", NOW + timedelta(days=6)),
              event("day9", NOW + timedelta(days=9)), event("past", NOW - timedelta(hours=5))]
    repo.replace_window(NOW - timedelta(days=1), NOW + timedelta(days=30), events, NOW)
    slots = collect_busy_slots(_registry({}), memory_engine, NOW, TZ)
    assert [s["title"] for s in slots] == ["Bận", "Bận"]                 # soon + day6; day9 ngoài 7 ngày, past đã qua
    shared = collect_busy_slots(_registry({"share_meeting_titles": True}), memory_engine, NOW, TZ)
    assert [s["title"] for s in shared] == ["Họp soon", "Họp day6"]


def test_cache_failure_degrades_to_none():
    broken = SimpleNamespace(find_by_engine=lambda _e: (_ for _ in ()).throw(RuntimeError("boom")))
    assert collect_busy_slots(broken, None, NOW, TZ) is None
