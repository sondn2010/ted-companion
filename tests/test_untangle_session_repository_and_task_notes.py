"""Phase 03: Task.notes (migration + append/update), UntangleSession repo, truy vấn baseline, tín hiệu hoàn tất 1 lần."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, text
from sqlmodel import Session, SQLModel

from src.core.idea_untangle.focus_history_baseline_queries import (
    consecutive_sessions_on_task_today, daily_same_task_session_counts, distraction_rate_baseline,
    historical_overrun_ratios, task_focus_minutes_total)
from src.core.idea_untangle.idea_untangle_service_and_completion_signal import IdeaUntangleService
from src.core.idea_untangle.untangle_session_repository import (
    MAX_TRANSCRIPT_CHARS, UntangleSessionRepository, cap_transcript)
from src.core.models import TASK_ADDED_COLUMNS, DatabaseManager, FocusSession, Task
from src.core.sqlite_add_missing_columns_migration import ensure_columns


@pytest.fixture
def engine(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 't.db'}")
    SQLModel.metadata.create_all(eng)
    return eng


@pytest.fixture
def manager(engine):
    return DatabaseManager.for_engine(engine)


def _task(engine, **kw) -> Task:
    with Session(engine) as s:
        t = Task(title=kw.pop("title", "t"), **kw)
        s.add(t)
        s.commit()
        s.refresh(t)
        return t


def test_old_db_without_notes_column_gains_it_keeping_rows(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE task (id VARCHAR PRIMARY KEY, title VARCHAR, quadrant INTEGER, matrix_order FLOAT NOT NULL DEFAULT 0.0)"))
        c.execute(text("INSERT INTO task (id, title) VALUES ('a', 'cũ')"))
    ensure_columns(eng, "task", TASK_ADDED_COLUMNS)
    ensure_columns(eng, "task", TASK_ADDED_COLUMNS)  # idempotent
    with eng.connect() as c:
        assert c.execute(text("SELECT title, notes FROM task")).one() == ("cũ", "")


def test_append_notes_twice_keeps_both_and_marks_unsynced(engine, manager):
    task = _task(engine, synced_to_hermes=True)
    manager.append_task_notes(task.id, "ý một")
    updated = manager.append_task_notes(task.id, "ý hai")
    assert "ý một" in updated.notes and "ý hai" in updated.notes and "🧶" in updated.notes
    assert not updated.notes.startswith("\n") and updated.synced_to_hermes is False
    assert manager.append_task_notes("không-có", "x") is None


def test_append_notes_caps_length_dropping_oldest_head(engine, manager):
    task = _task(engine)
    manager.append_task_notes(task.id, "ĐẦU" + "a" * 7990)
    result = manager.append_task_notes(task.id, "CUỐI")
    assert len(result.notes) == 8000 and result.notes.endswith("CUỐI") and "ĐẦU" not in result.notes


def test_update_task_notes_none_keeps_and_value_replaces(engine, manager):
    task = _task(engine, notes="giữ")
    kwargs = dict(title="t", category="deep_work", estimated_pomodoros=1, quadrant=None, status="todo",
                  scheduled_date="2026-10-22")
    assert manager.update_task(task.id, **kwargs).notes == "giữ"
    assert manager.update_task(task.id, notes="mới", **kwargs).notes == "mới"


def test_session_complete_keeps_first_completed_at_and_cap(engine):
    repo = UntangleSessionRepository(engine)
    row = repo.create_session("work", "work", None, "đề", "algorithm", "bogus")
    assert row.trigger == "menu" and row.task_id is None
    assert repo.complete_session(row.id, '{"a":1}') is True
    first_at = repo.get(row.id).completed_at
    assert repo.complete_session(row.id) is False
    assert repo.get(row.id).completed_at == first_at and repo.get(row.id).critique_json == '{"a":1}'
    assert repo.complete_session("nope") is None
    turns = [{"role": "user", "text": "x" * 5000} for _ in range(50)]
    assert len(cap_transcript(turns)) <= 4 and sum(len(t["text"]) for t in cap_transcript(turns)) <= MAX_TRANSCRIPT_CHARS
    assert repo.save_transcript(row.id, turns) is True


def test_recent_for_task_newest_first_and_limit(engine):
    repo = UntangleSessionRepository(engine)
    for _ in range(4):
        repo.create_session("work", "work", "t1", "x", "other", "hotkey")
    repo.create_session("work", "work", "t2", "x", "other", "hotkey")
    assert len(repo.recent_for_task("t1")) == 3 and len(repo.recent_for_task("t1", 10)) == 4


def test_service_emits_once_with_task_and_kind(engine, qtbot=None):
    service = IdeaUntangleService(UntangleSessionRepository(engine))
    row = service.repo.create_session("thcs", "coach", None, "x", "math_problem", "menu")
    seen = []
    service.session_completed.connect(lambda *a: seen.append(a))
    assert service.complete(row.id) is True and service.complete(row.id) is False
    assert seen == [(row.id, "", "math_problem")]
    assert service.complete("missing") is False


def _focus(engine, task_id, minutes, distractions=0, started=None):
    with Session(engine) as s:
        s.add(FocusSession(task_id=task_id, actual_minutes=minutes, distraction_count=distractions,
                           started_at=started or datetime.now(timezone.utc)))
        s.commit()


def test_baseline_queries(engine):
    done = _task(engine, status="done", estimated_pomodoros=2)
    other = _task(engine)
    _focus(engine, done.id, 50, 2, datetime.now(timezone.utc) - timedelta(days=3))
    _focus(engine, done.id, 25, 0, datetime.now(timezone.utc) - timedelta(days=3, minutes=-1))
    _focus(engine, other.id, 25)
    _focus(engine, other.id, 25)
    assert task_focus_minutes_total(engine, done.id) == 75
    assert consecutive_sessions_on_task_today(engine, other.id) == 2
    assert consecutive_sessions_on_task_today(engine, done.id) == 0
    assert historical_overrun_ratios(engine) == [pytest.approx(75 / 50)]
    assert sorted(daily_same_task_session_counts(engine)) == [2, 2]
    assert sorted(round(x, 2) for x in distraction_rate_baseline(engine)) == [0.0, 0.0, 0.0, 1.0]


def test_baseline_same_task_counts_ignore_sessions_older_than_window(engine):
    t = _task(engine)
    _focus(engine, t.id, 25)
    _focus(engine, t.id, 25, started=datetime.now(timezone.utc) - timedelta(days=90))   # ngoài cửa sổ 30 ngày
    assert daily_same_task_session_counts(engine) == [1]
    assert daily_same_task_session_counts(engine, days=120) == [1, 1]


def test_overrun_ratios_single_query_skips_tasks_without_focus_and_respects_limit(engine):
    with_focus = _task(engine, status="done", estimated_pomodoros=1)
    _task(engine, status="done")   # xong nhưng chưa có phiên focus → bỏ qua
    _focus(engine, with_focus.id, 50)
    assert historical_overrun_ratios(engine) == [pytest.approx(50 / 25)]
    assert len(historical_overrun_ratios(engine, limit=1)) == 1


def test_notes_to_save_keeps_untangle_append_made_while_form_open():
    from src.core.task_notes_merge_on_save import notes_to_save
    tail = "\n\n— 🧶 x\nmới"   # mục Gỡ Rối nối thêm khi form đang mở
    assert notes_to_save("a", "a", "a", "a" + tail) is None   # không sửa ô ghi chú → giữ nguyên DB
    assert notes_to_save("a", "a", "a sửa", "a" + tail) == "a sửa" + tail   # có sửa + DB được nối → gộp
    assert notes_to_save("a", "a", "b", "a") == "b"   # DB không đổi → bản sửa
    assert notes_to_save("a", "a", "b", "z") == "b"   # DB bị thay hẳn → ưu tiên người dùng
