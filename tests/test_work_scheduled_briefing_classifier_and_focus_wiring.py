"""Briefing sáng/trưa (email, đọc to 1 lần, bỏ đọc khi họp), timer, phân loại ý tưởng đã đỗ, nhắc việc khi bắt đầu phiên."""

import asyncio
import json
from datetime import date, datetime, timedelta, timezone

import httpx
from PySide6.QtCore import QObject, Signal
from sqlmodel import Session, select

from src.core.background_task_spawner import _running_tasks
from src.core.models import DatabaseManager, Task
from src.engines.work import work_briefing_flow as flow_mod
from src.engines.work import work_focus_engine_signal_wiring as wiring_mod
from src.engines.work.calendar_event_cache_model_and_repository import CalendarEventCache
from src.engines.work.work_module_engine import LAST_BRIEFING_KEY, LAST_MIDDAY_BRIEFING_KEY
from tests.test_work_engine_briefing_and_rocks_tab import _engine, _reply

EMAIL_JSON = json.dumps({"emails": [
    {"from": "Sếp", "subject": "Duyệt ngân sách", "summary": "gấp", "priority": "important", "reason": "sếp"},
    {"from": "News", "subject": "Bản tin", "priority": "low"},
], "total_unread": 2})


def _handler(calls=None):
    def handler(request):
        prompt = json.loads(request.content)["messages"][-1]["content"]
        if calls is not None:
            calls.append(prompt)
        if prompt.startswith("[TED_EMAIL_DIGEST]"):
            return _reply(f"<json>{EMAIL_JSON}</json>")
        if prompt.startswith("[TED_EISENHOWER]"):
            return _reply('<json>{"quadrant": 2, "reason": "quan trọng"}</json>')
        return _reply("[MOOD:CHEER] Em chào anh, có email của sếp nha!")
    return handler


def _capture_speech(monkeypatch):
    spoken = []

    async def fake_speak(text, *args, **kwargs):
        spoken.append(text)

    monkeypatch.setattr(flow_mod.tts_service, "speak", fake_speak)
    return spoken


async def _run(engine, ctx, slot="morning"):
    inp = engine._briefing.gather(slot)
    ctx.bubble.show_message("local", timeout_ms=12000)
    await engine._briefing.run_background(inp, "local")
    return inp


def _add_meeting_now(memory_engine):
    now = datetime.now(timezone.utc)
    with Session(memory_engine) as s:
        s.add(CalendarEventCache(key="m", title="Họp", start_at=now - timedelta(minutes=5),
                                 end_at=now + timedelta(minutes=30), fetched_at=now))
        s.commit()


async def test_email_ok_rewrites_bubble_and_speaks_once_without_mood_tag(memory_engine, monkeypatch):
    spoken = _capture_speech(monkeypatch)
    calls = []
    engine, ctx = _engine(memory_engine, _handler(calls))
    inp = await _run(engine, ctx)
    assert inp.important_emails and inp.low_email_count == 1
    assert spoken == ["Em chào anh, có email của sếp nha!"]
    assert ctx.bubble.current_text() == spoken[0]
    briefing_prompt = next(c for c in calls if c.startswith("[TED_BRIEFING]"))
    assert "Sếp | Duyệt ngân sách" in briefing_prompt and "morning" in briefing_prompt


async def test_email_failure_keeps_local_line_and_speaks_local_when_hermes_down(memory_engine, monkeypatch):
    spoken = _capture_speech(monkeypatch)
    engine, ctx = _engine(memory_engine)  # mọi request HTTP 500
    inp = await _run(engine, ctx)
    assert inp.email_failed
    assert "Em chưa đọc được email." in ctx.bubble.current_text()
    assert spoken == [ctx.bubble.current_text()] and "[MOOD" not in spoken[0]


async def test_email_disabled_skips_digest_request(memory_engine, monkeypatch):
    _capture_speech(monkeypatch)
    calls = []
    engine, ctx = _engine(memory_engine, _handler(calls))
    engine.manifest.settings["email_digest_enabled"] = False
    await _run(engine, ctx)
    assert calls and not any(c.startswith("[TED_EMAIL_DIGEST]") for c in calls)


async def test_speech_skipped_in_meeting_but_bubble_still_shown(memory_engine, monkeypatch):
    spoken = _capture_speech(monkeypatch)
    _add_meeting_now(memory_engine)
    engine, ctx = _engine(memory_engine, _handler())
    await _run(engine, ctx)
    assert spoken == [] and ctx.bubble.current_text().startswith("Em chào anh")


async def test_speech_skipped_when_speak_briefing_disabled(memory_engine, monkeypatch):
    spoken = _capture_speech(monkeypatch)
    engine, ctx = _engine(memory_engine, _handler())
    engine.manifest.settings["speak_briefing"] = False
    await _run(engine, ctx)
    assert spoken == []


def _at_hour(hour):
    return lambda: datetime.combine(date.today(), datetime.min.time()).replace(hour=hour).astimezone()


def test_show_briefing_marks_keys_by_slot_and_never_double(memory_engine):
    engine, ctx = _engine(memory_engine)
    day = date.today().isoformat()
    engine._clock = _at_hour(9)
    engine.show_briefing()
    assert ctx.kv.get(LAST_BRIEFING_KEY) == day and ctx.kv.get(LAST_MIDDAY_BRIEFING_KEY) is None
    assert engine._scheduled_briefing.check_now() is None  # sáng đã bắn
    engine._clock = _at_hour(13)
    assert engine._scheduled_briefing.check_now() == "midday"
    assert ctx.kv.get(LAST_MIDDAY_BRIEFING_KEY) == day
    assert engine._scheduled_briefing.check_now() is None  # đã bắn → không lặp
    assert engine.on_pet_click() is False


def test_timer_start_stop_is_idempotent(memory_engine):
    engine, _ = _engine(memory_engine)
    engine.start()
    engine.start()
    engine.stop()
    engine.stop()
    assert engine._scheduled_briefing._timer is None


class _FakeFocus(QObject):
    task_added = Signal(str, str)
    session_started = Signal(str, str)
    tasks_updated = Signal()


def _with_focus(memory_engine, handler=None):
    engine, ctx = _engine(memory_engine, handler or _handler())
    ctx.focus_engine = _FakeFocus()
    return engine, ctx


def _add(memory_engine, **kwargs) -> str:
    with Session(memory_engine) as s:
        task = Task(**kwargs)
        s.add(task)
        s.commit()
        return task.id


def _quadrant(memory_engine, task_id):
    with Session(memory_engine) as s:
        return s.get(Task, task_id).quadrant


async def test_classifier_sets_quadrant_refreshes_ui_and_acks(memory_engine):
    engine, ctx = _with_focus(memory_engine)
    refreshed = []
    ctx.focus_engine.tasks_updated.connect(lambda: refreshed.append(1))
    tid = _add(memory_engine, title="Học Rust", category="parked_idea")
    assert await engine._focus_wiring.classifier.classify(tid, "Học Rust") is True
    assert _quadrant(memory_engine, tid) == 2 and refreshed == [1]
    assert "Q2" in ctx.bubble.current_text()


async def test_classifier_does_not_overwrite_user_choice_and_offline_stays_unsorted(memory_engine):
    engine, _ = _with_focus(memory_engine)
    moved = _add(memory_engine, title="a", category="parked_idea", quadrant=4)
    assert await engine._focus_wiring.classifier.classify(moved, "a") is False
    assert _quadrant(memory_engine, moved) == 4
    offline, _ = _with_focus(memory_engine, lambda r: httpx.Response(500, json={"error": "down"}))
    tid = _add(memory_engine, title="b", category="parked_idea")
    assert await offline._focus_wiring.classifier.classify(tid, "b") is False
    assert _quadrant(memory_engine, tid) is None


async def test_task_added_signal_classifies_in_background_until_stop(memory_engine):
    engine, ctx = _with_focus(memory_engine)
    engine.start()
    tid = _add(memory_engine, title="Ý tưởng", category="parked_idea")
    ctx.focus_engine.task_added.emit(tid, "Ý tưởng")
    await asyncio.gather(*list(_running_tasks))
    assert _quadrant(memory_engine, tid) == 2
    engine.stop()
    other = _add(memory_engine, title="Sau stop", category="parked_idea")
    ctx.focus_engine.task_added.emit(other, "Sau stop")  # đã ngắt kết nối
    assert _quadrant(memory_engine, other) is None
    engine.stop()


def test_session_started_announces_next_task_and_mutes_speech_in_meeting(memory_engine, monkeypatch):
    calls = []
    monkeypatch.setattr(wiring_mod, "announce", lambda ctx, text, speak=True, **_: calls.append((text, speak)))
    engine, ctx = _with_focus(memory_engine)
    _add(memory_engine, title="Nộp thuế", quadrant=1)
    engine.start()
    engine.start()  # không connect 2 lần
    ctx.focus_engine.session_started.emit("", "Dọn mail")
    assert len(calls) == 1 and "Q1 còn Nộp thuế" in calls[0][0] and calls[0][1] is True
    _add_meeting_now(memory_engine)
    ctx.focus_engine.session_started.emit("", "Dọn mail")
    assert len(calls) == 2 and calls[1][1] is False
    engine.stop()
    ctx.focus_engine.session_started.emit("", "x")
    assert len(calls) == 2


def test_database_manager_for_engine_uses_given_engine(memory_engine):
    _add(memory_engine, title="Q2 task", quadrant=2)
    manager = DatabaseManager.for_engine(memory_engine)
    assert [t.title for t in manager.next_important_tasks()] == ["Q2 task"]
    assert len(list(Session(memory_engine).exec(select(Task)))) == 1  # không seed task chào mừng
