"""Regression review: M7 (rỗng đáng ngờ không xoá cache), L4 (prune), L5 (tạo bảng 1 lần)."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine

from src.engines.work import calendar_event_cache_model_and_repository as repo_mod
from src.engines.work.calendar_contract_schemas import CalendarEvent
from src.engines.work.calendar_event_cache_model_and_repository import CalendarEventRepository
from tests.test_work_calendar_sync_and_reminder_service import _events_json, _seed, _setup, _tomorrow_noon


def _event_dict(noon):
    return {"id": "a", "title": "Mới", "start": noon.isoformat(), "end": None, "location": None, "meet_url": None,
            "all_day": False}


async def test_single_empty_reply_keeps_cache_second_empty_clears(memory_engine):
    engine, ctx, _ = _setup(memory_engine, [_events_json()])
    noon = _tomorrow_noon()
    _seed(engine, title="Giữ", start=noon)
    rng = (noon - timedelta(hours=1), noon + timedelta(hours=1))
    assert await engine.calendar_sync.sync() is False
    assert [r.title for r in engine.calendar_repo.between(*rng)] == ["Giữ"]
    assert ctx.kv.get("work.calendar_empty_streak") == "1"
    assert await engine.calendar_sync.sync() is True        # lần rỗng thứ 2 liên tiếp → tin
    assert engine.calendar_repo.between(*rng) == []


async def test_non_empty_reply_resets_empty_streak(memory_engine):
    engine, ctx, _ = _setup(memory_engine, [_events_json(_event_dict(_tomorrow_noon()))])
    ctx.kv.set("work.calendar_empty_streak", "1")
    assert await engine.calendar_sync.sync() is True
    assert ctx.kv.get("work.calendar_empty_streak") == "0"


async def test_empty_reply_with_empty_cache_is_accepted_immediately(memory_engine):
    engine, _ctx, _ = _setup(memory_engine, [_events_json()])
    assert await engine.calendar_sync.sync() is True


async def test_sync_prunes_past_and_out_of_window_rows(memory_engine):
    engine, _ctx, _ = _setup(memory_engine, [_events_json(_event_dict(_tomorrow_noon()))])
    now = datetime.now(timezone.utc)
    for title, start in (("cũ", now - timedelta(days=5)), ("xa", now + timedelta(days=30))):
        e = CalendarEvent(title=title, start=start, end=start + timedelta(hours=1))
        engine.calendar_repo.replace_window(start - timedelta(hours=1), start + timedelta(hours=2), [e], now)
    assert await engine.calendar_sync.sync() is True
    titles = [r.title for r in engine.calendar_repo.between(now - timedelta(days=40), now + timedelta(days=40))]
    assert titles == ["Mới"]


def test_table_created_once_per_engine(monkeypatch):
    engine = create_engine("sqlite://")
    calls = []
    real = repo_mod.CalendarEventCache.__table__.create

    def spy(*a, **k):
        calls.append(1)
        return real(*a, **k)

    monkeypatch.setattr(repo_mod.CalendarEventCache.__table__, "create", spy, raising=False)
    CalendarEventRepository(engine)
    CalendarEventRepository(engine)
    assert len(calls) == 1
