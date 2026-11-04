"""Hồi quy cho review Eisenhower/briefing: chống briefing dồn dập, kết quả trễ, classifier không đè, schema cắt, builder cap."""

import asyncio
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from sqlmodel import Session

from src.core import models as models_mod
from src.core.focus_engine import FocusState
from src.core.models import Task
from src.engines.work import work_briefing_flow as flow_mod
from src.engines.work import work_briefing_run_guard as guard
from src.engines.work import work_focus_engine_signal_wiring as wiring_mod
from src.engines.work.calendar_event_cache_model_and_repository import CalendarEventCache
from src.engines.work.daily_briefing_builder import BriefingInput, build_local_briefing_text
from src.engines.work.email_digest_contract_schemas import MAX_EMAILS, EmailDigestResponse, EmailItem
from src.engines.work.work_briefing_due_window import MIDDAY, MORNING, due_briefing_slot
from tests.test_work_engine_briefing_and_rocks_tab import _engine, _reply
from tests.test_work_scheduled_briefing_classifier_and_focus_wiring import (
    _add, _capture_speech, _handler, _quadrant, _with_focus,
)


def _at(h, m=0):
    return datetime(2026, 10, 21, h, m).astimezone()


# ---- M3 schema ----
def test_overlong_strings_are_truncated_not_rejected():
    item = EmailItem.model_validate({"from": "a" * 999, "subject": "s" * 999, "summary": "x" * 999, "reason": "r" * 999,
                                     "priority": "low"})
    assert (len(item.sender), len(item.subject), len(item.summary), len(item.reason)) == (200, 300, 500, 120)


def test_too_many_emails_are_sliced_to_max():
    mail = {"from": "a", "priority": "low"}
    digest = EmailDigestResponse.model_validate({"emails": [mail] * (MAX_EMAILS + 20), "total_unread": 99})
    assert len(digest.emails) == MAX_EMAILS


# ---- M4 builder ----
def _digest(important, low, total_unread):
    emails = [EmailItem(sender=f"S{i}", subject=f"T{i}", priority="important") for i in range(important)]
    emails += [EmailItem(sender="L", subject="l", priority="low") for _ in range(low)]
    return EmailDigestResponse(emails=emails, total_unread=total_unread)


def test_important_capped_to_max_items_and_low_count_uses_total_unread():
    inp = BriefingInput()
    inp.apply_email_digest(_digest(important=12, low=1, total_unread=30), max_items=8)
    assert len(inp.important_emails) == 8
    assert inp.low_email_count == 30 - 12  # total_unread - số email quan trọng


def test_low_count_never_negative_and_keeps_listed_low():
    inp = BriefingInput()
    inp.apply_email_digest(_digest(important=2, low=3, total_unread=1))
    assert inp.low_email_count == 3


def test_local_text_lists_at_most_five_emails_rest_as_count():
    inp = BriefingInput()
    inp.apply_email_digest(_digest(important=8, low=0, total_unread=8), max_items=8)
    text = build_local_briefing_text(inp)
    assert "Có 8 email quan trọng" in text and "S4: T4" in text and "S5: T5" not in text and "và 3 email nữa" in text


# ---- H2 due window ----
def test_recent_briefing_blocks_scheduled_slot_until_gap_passes():
    morning_fired_at = _at(11, 58).astimezone(timezone.utc)
    assert due_briefing_slot(_at(12, 0), {}, "2026-10-21", None, morning_fired_at) is None
    assert due_briefing_slot(_at(12, 59), {}, "2026-10-21", None, morning_fired_at) == MIDDAY  # sau 60 phút vẫn trong cửa sổ


def test_briefed_recently_ignores_future_marker():
    assert not guard.briefed_recently(_at(9), _at(10).astimezone(timezone.utc))


def test_show_briefing_records_last_briefing_at_and_blocks_next_timer_slot(memory_engine):
    engine, ctx = _engine(memory_engine)
    engine._clock = lambda: _at(11, 58)
    engine.show_briefing()
    assert guard.read_last_briefing_at(ctx.kv) == _at(11, 58).astimezone(timezone.utc)
    engine._clock = lambda: _at(12, 0)
    assert engine._scheduled_briefing.check_now() is None  # midday chờ
    engine._clock = lambda: _at(13, 0)
    assert engine._scheduled_briefing.check_now() == MIDDAY


# ---- M5 midday lookback ----
def test_midday_email_since_is_previous_briefing_only_if_today():
    now = _at(12, 0)
    morning = _at(8, 5).astimezone(timezone.utc)
    assert guard.email_since(True, morning, now) == morning
    assert guard.email_since(False, morning, now) is None
    assert guard.email_since(True, morning - timedelta(days=1), now) is None
    assert guard.email_since(True, None, now) is None


async def test_midday_digest_prompt_uses_morning_time_as_since(memory_engine, monkeypatch):
    _capture_speech(monkeypatch)
    calls = []
    engine, ctx = _engine(memory_engine, _handler(calls))
    morning = _at(8, 5)
    inp = engine._briefing.gather(MIDDAY)
    ctx.bubble.show_message("local", timeout_ms=12000)
    await engine._briefing.run_background(inp, "local", email_from=morning)
    prompt = next(c for c in calls if c.startswith("[TED_EMAIL_DIGEST]"))
    assert morning.isoformat(timespec="minutes") in prompt


# ---- H2 generation / H3 late result ----
async def test_older_pipeline_drops_silently_when_newer_briefing_started(memory_engine, monkeypatch):
    spoken = _capture_speech(monkeypatch)
    engine, ctx = _engine(memory_engine, _handler())
    flow = engine._briefing
    flow._generation = 1
    inp = flow.gather(MORNING)
    ctx.bubble.show_message("local", timeout_ms=12000)
    task = asyncio.ensure_future(flow.run_background(inp, "local", generation=1))
    flow._generation = 2  # briefing mới bắt đầu trong lúc pipeline cũ đang chờ
    await task
    assert spoken == [] and ctx.bubble.current_text() == "local"


async def test_late_hermes_result_after_bubble_hidden_does_not_reshow_or_speak(memory_engine, monkeypatch):
    spoken = _capture_speech(monkeypatch)
    engine, ctx = _engine(memory_engine, lambda r: _reply("[MOOD:CHEER] bản Hermes"))
    flow = engine._briefing
    assert ctx.bubble.is_busy() is False
    assert await flow._hermes_text(BriefingInput(), "local", elapsed=guard.LATE_RESULT_SECS + 1) == ""
    assert not ctx.bubble.is_busy()
    assert await flow._hermes_text(BriefingInput(), "local", elapsed=1.0) == "bản Hermes"  # chưa trễ → hiện lại như cũ
    assert spoken == []


async def test_late_pipeline_with_bubble_replaced_does_not_speak(memory_engine, monkeypatch):
    spoken = _capture_speech(monkeypatch)
    engine, ctx = _engine(memory_engine, _handler())
    inp = engine._briefing.gather(MORNING)
    ctx.bubble.show_message("tin khác", timeout_ms=12000)  # bubble không còn là briefing
    await engine._briefing.run_background(inp, "local")
    assert spoken == [] and ctx.bubble.current_text() == "tin khác"


async def test_no_speech_while_deep_work_running_but_bubble_still_updates(memory_engine, monkeypatch):
    spoken = _capture_speech(monkeypatch)
    engine, ctx = _with_focus(memory_engine)
    ctx.focus_engine.state = FocusState.DEEP_WORK_RUNNING
    inp = engine._briefing.gather(MORNING)
    ctx.bubble.show_message("local", timeout_ms=12000)
    await engine._briefing.run_background(inp, "local")
    assert spoken == [] and ctx.bubble.current_text().startswith("Em chào anh")
    ctx.focus_engine.state = FocusState.IDLE
    await engine._briefing.run_background(inp, ctx.bubble.current_text())
    assert len(spoken) == 1


async def test_pipeline_has_overall_deadline_and_keeps_local_text(memory_engine, monkeypatch):
    spoken = _capture_speech(monkeypatch)
    monkeypatch.setattr(flow_mod, "PIPELINE_DEADLINE_SECS", 0.05)

    async def slow_fetch(*args, **kwargs):
        await asyncio.sleep(5)

    monkeypatch.setattr(flow_mod, "fetch_email_digest", slow_fetch)
    engine, ctx = _engine(memory_engine, _handler())
    inp = engine._briefing.gather(MORNING)
    ctx.bubble.show_message("local", timeout_ms=12000)
    began = time.monotonic()
    await engine._briefing.run_background(inp, "local")
    assert time.monotonic() - began < 2 and spoken == ["local"]


async def test_email_fetch_has_its_own_budget(memory_engine, monkeypatch):
    from src.engines.work import email_digest_fetcher as fetcher

    monkeypatch.setattr(fetcher, "EMAIL_DIGEST_BUDGET_SECS", 0.05)

    async def slow_request(*args, **kwargs):
        await asyncio.sleep(5)

    monkeypatch.setattr(fetcher, "request_json", slow_request)
    engine, _ = _engine(memory_engine)
    client = engine._briefing._client()
    assert await fetcher.fetch_email_digest(engine.manifest, client, MORNING) is None


# ---- M1 classifier ----
def _park(memory_engine, **kwargs):
    return _add(memory_engine, title="Ý tưởng", category="parked_idea", **kwargs)


async def test_classifier_does_not_write_if_user_touched_task_after_parking(memory_engine):
    engine, _ = _with_focus(memory_engine)
    classifier = engine._focus_wiring.classifier
    tid = _park(memory_engine)
    parked_at = classifier._updated_at(tid)
    # Người dùng kéo/sắp xếp lại trong Unsorted (set_task_quadrant(None) bump updated_at)
    models_mod.DatabaseManager.for_engine(memory_engine).set_task_quadrant(tid, None, order=3)
    assert await classifier.classify(tid, "Ý tưởng", parked_updated_at=parked_at) is False
    assert _quadrant(memory_engine, tid) is None


async def test_classifier_writes_if_untouched_and_puts_idea_at_end_of_quadrant(memory_engine):
    engine, _ = _with_focus(memory_engine)  # handler luôn trả Q2
    classifier = engine._focus_wiring.classifier
    _add(memory_engine, title="a", quadrant=2, matrix_order=0.0)
    _add(memory_engine, title="b", quadrant=2, matrix_order=4.0)
    tid = _park(memory_engine)
    assert await classifier.classify(tid, "Ý tưởng", parked_updated_at=classifier._updated_at(tid)) is True
    with Session(memory_engine) as s:
        assert s.get(Task, tid).quadrant == 2 and s.get(Task, tid).matrix_order == 5.0


def test_reorder_and_move_bump_updated_at(memory_engine):
    manager = models_mod.DatabaseManager.for_engine(memory_engine)
    tid = _add(memory_engine, title="x")
    before = manager.list_tasks()[0].updated_at
    manager.reorder_quadrant(None, [tid])
    after = manager.list_tasks()[0].updated_at
    assert after > before


# ---- M2 wiring ----
def test_session_started_without_q1_q2_is_bubble_only(memory_engine, monkeypatch):
    calls = []
    monkeypatch.setattr(wiring_mod, "announce", lambda ctx, text, speak=True, **_: calls.append(speak))
    engine, ctx = _with_focus(memory_engine)
    engine.start()
    ctx.focus_engine.session_started.emit("", "Dọn mail")
    assert calls == [False]
    engine.stop()


# ---- L4 ended meetings ----
def test_catch_up_briefing_skips_meetings_already_ended(memory_engine):
    engine, _ = _engine(memory_engine)
    now = datetime.now(timezone.utc)
    with Session(memory_engine) as s:
        s.add(CalendarEventCache(key="old", title="Họp đã xong", start_at=now - timedelta(hours=3),
                                 end_at=now - timedelta(hours=2), fetched_at=now))
        s.add(CalendarEventCache(key="new", title="Họp sắp tới", start_at=now + timedelta(minutes=30),
                                 end_at=now + timedelta(hours=1), fetched_at=now))
        s.commit()
    titles = [t for _, t in flow_mod.today_calendar_events(memory_engine, only_unfinished=True)]
    assert "Họp đã xong" not in titles and "Họp sắp tới" in titles


# ---- L7 migration failure ----
def test_migration_failure_is_logged_and_does_not_crash_startup(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(models_mod, "settings", SimpleNamespace(db_path=tmp_path / "t.db"))

    def boom(*args, **kwargs):
        raise RuntimeError("database is locked")

    monkeypatch.setattr(models_mod, "ensure_columns", boom)
    manager = models_mod.DatabaseManager()
    try:
        assert manager.list_tasks() is not None
    finally:
        manager.engine.dispose()
    assert "Nâng cấp cột" in caplog.text
