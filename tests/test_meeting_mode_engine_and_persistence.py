"""Hub phase 13: chế độ Họp / Học nhóm trong FocusEngine — start/stop, đếm lên, nhắc bị chặn, lưu DB, DB cũ, gợi ý chủ đề."""

import sqlite3
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import inspect
from sqlmodel import Session, SQLModel, create_engine, select

from qt_offscreen_app_helper import get_qapp
from src.config import settings
from src.core.focus_engine import FocusEngine, FocusState
from src.core.i18n import tr
from src.core.meeting_mode.meeting_session_table_model_and_repository import (
    KIND_TEACHER, KIND_TEAM_MEETING, TOPIC_MAX_CHARS, MeetingSession, MeetingSessionRepository)
from src.core.meeting_mode.meeting_topic_prefill import current_calendar_event_title, meeting_prefill
from src.core.models import FocusSession


@pytest.fixture
def eng(memory_engine):
    get_qapp()
    audio = SimpleNamespace(play_chime=lambda: None)
    engine = FocusEngine(audio)
    engine.meeting_repo = MeetingSessionRepository(memory_engine)
    engine.ipc_timer.stop()
    yield engine
    engine.tick_timer.stop()


def _rows(memory_engine):
    with Session(memory_engine) as s:
        return s.exec(select(MeetingSession)).all()


def _tick(engine, seconds):
    for _ in range(seconds):
        engine._on_second_tick()


def test_start_sets_meeting_state_with_focus_art_and_topic_title(eng):
    states, started = [], []
    eng.state_changed.connect(lambda st, mood: states.append((st, mood)))
    eng.meeting_started.connect(lambda k, t: started.append((k, t)))
    eng.start_meeting("  Sprint   planning ", KIND_TEAM_MEETING)
    assert eng.state == FocusState.MEETING_RUNNING and eng.in_meeting
    assert eng.current_mood == "FOCUS"                       # dùng chung hình FOCUS
    assert eng.active_task_title == "Sprint planning"
    assert states[-1] == (FocusState.MEETING_RUNNING, "FOCUS") and started == [(KIND_TEAM_MEETING, "Sprint planning")]
    assert len(_rows(eng.meeting_repo._engine)) == 1


def test_skip_topic_uses_kind_label_as_title(eng):
    eng.start_meeting("", KIND_TEACHER)
    assert eng.active_task_title == tr("meeting_kind_teacher")
    assert eng.meeting_topic == "" and eng.meeting_kind == KIND_TEACHER


def test_timer_counts_up_never_auto_completes_and_no_mindful_ping(eng, monkeypatch):
    monkeypatch.setattr(settings, "mindful_ping_mins", 1)
    pings = []
    eng.mindful_ping_triggered.connect(pings.append)
    eng.start_meeting("Họp dài")
    _tick(eng, 130)
    assert eng.elapsed_seconds == 130 and eng.state == FocusState.MEETING_RUNNING
    assert eng.remaining_seconds == 0 and pings == []         # không countdown, không mindful ping


def test_stop_saves_minutes_emits_completed_and_returns_idle(eng):
    done, session_done = [], []
    eng.meeting_completed.connect(lambda k, m: done.append((k, m)))
    eng.session_completed.connect(lambda *a: session_done.append(a))
    eng.start_meeting("Học nhóm Toán", "team_study")
    _tick(eng, 600)
    eng.stop_session(completed=False)                        # mọi lối "dừng" đều dừng được họp
    assert eng.state == FocusState.IDLE and done == [("team_study", 10)] and session_done == []
    row = _rows(eng.meeting_repo._engine)[0]
    assert (row.actual_minutes, row.kind, row.topic) == (10, "team_study", "Học nhóm Toán") and row.ended_at is not None


def test_very_short_meeting_is_discarded(eng):
    done = []
    eng.meeting_completed.connect(lambda *a: done.append(a))
    eng.start_meeting("bấm nhầm")
    _tick(eng, 10)
    eng.stop_meeting()
    assert eng.state == FocusState.IDLE and done == [] and _rows(eng.meeting_repo._engine) == []


def test_meeting_never_creates_focus_session_rows(eng, memory_engine):
    eng.start_meeting("Họp")
    _tick(eng, 120)
    eng.stop_meeting()
    with Session(memory_engine) as s:
        assert s.exec(select(FocusSession)).all() == []


def test_pause_is_ignored_and_start_twice_is_noop(eng):
    eng.start_meeting("Họp")
    eng.pause_or_resume()
    assert eng.state == FocusState.MEETING_RUNNING
    first = eng.current_meeting_id
    eng.start_meeting("Họp khác")
    assert eng.current_meeting_id == first and len(_rows(eng.meeting_repo._engine)) == 1


def test_meeting_replaces_deep_work_and_deep_work_replaces_meeting(eng):
    eng.start_focus_session("Việc", 25)
    assert eng.state == FocusState.DEEP_WORK_RUNNING
    eng.start_meeting("Họp")
    assert eng.state == FocusState.MEETING_RUNNING
    _tick(eng, 60)
    eng.start_focus_session("Việc 2", 25)                     # Deep Work thay thế họp → họp được lưu
    assert eng.state == FocusState.DEEP_WORK_RUNNING
    assert [r.actual_minutes for r in _rows(eng.meeting_repo._engine)] == [1]
    eng.stop_session(completed=False)


def test_toggle_request_signal_reaches_listener(eng):
    got = []
    eng.meeting_toggle_requested.connect(lambda: got.append(1))
    eng.request_meeting_toggle()
    assert got == [1]


def test_topic_is_trimmed_to_limit_and_unknown_kind_becomes_other(memory_engine):
    repo = MeetingSessionRepository(memory_engine)
    mid = repo.start("không-biết", "x" * (TOPIC_MAX_CHARS + 50))
    row = _rows(memory_engine)[0]
    assert row.id == mid and row.kind == "other" and len(row.topic) == TOPIC_MAX_CHARS


# ---- gợi ý chủ đề ----
def test_prefill_uses_last_used_without_calendar(memory_engine):
    repo = MeetingSessionRepository(memory_engine)
    assert meeting_prefill(memory_engine) == ("", KIND_TEAM_MEETING)
    repo.start("teacher", "Giải tích")
    assert meeting_prefill(memory_engine) == ("Giải tích", "teacher")


def test_prefill_prefers_current_calendar_event_title(memory_engine):
    from src.engines.work.calendar_event_cache_model_and_repository import CalendarEventCache
    now = datetime(2026, 10, 22, 9, 30, tzinfo=timezone.utc)
    with Session(memory_engine) as s:
        s.add(CalendarEventCache(key="a|1", title="Daily standup", start_at=now - timedelta(minutes=10),
                                 end_at=now + timedelta(minutes=20), fetched_at=now))
        s.add(CalendarEventCache(key="b|1", title="Đã xong", start_at=now - timedelta(hours=3),
                                 end_at=now - timedelta(hours=2), fetched_at=now))
        s.commit()
    MeetingSessionRepository(memory_engine).start("other", "chủ đề cũ")
    assert current_calendar_event_title(memory_engine, now) == "Daily standup"
    assert meeting_prefill(memory_engine, now)[0] == "Daily standup"


# ---- DB cũ ----
OLD_SCHEMA = """
CREATE TABLE focussession (id VARCHAR PRIMARY KEY, task_id VARCHAR, intent_statement VARCHAR NOT NULL,
    planned_minutes INTEGER NOT NULL, actual_minutes INTEGER NOT NULL, distraction_count INTEGER NOT NULL,
    focus_rating INTEGER, started_at DATETIME NOT NULL, ended_at DATETIME, synced_to_hermes BOOLEAN NOT NULL);
INSERT INTO focussession VALUES ('f1',NULL,'cũ',25,25,0,5,'2026-10-01 00:00:00','2026-10-01 00:25:00',0);
"""


def test_old_database_gains_meeting_table_and_keeps_focus_rows(tmp_path):
    db = tmp_path / "old.db"
    con = sqlite3.connect(db)
    con.executescript(OLD_SCHEMA)
    con.commit()
    con.close()
    import src.core.models  # noqa: F401  (đăng ký mọi bảng)
    engine = create_engine(f"sqlite:///{db}")
    SQLModel.metadata.create_all(engine)
    assert "meetingsession" in inspect(engine).get_table_names()
    with Session(engine) as s:
        assert s.exec(select(FocusSession)).one().intent_statement == "cũ"
    repo = MeetingSessionRepository(engine)            # idempotent trên DB đã có bảng
    repo.finish(repo.start("team_meeting", "ok"), 5)
    assert [r.actual_minutes for r in _rows(engine)] == [5]
    engine.dispose()
