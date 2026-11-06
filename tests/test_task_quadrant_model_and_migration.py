"""Task.quadrant/matrix_order: migration DB cũ, set/reorder, next_important_tasks; FocusEngine phát session_started/task_added."""

from types import SimpleNamespace

import pytest
from sqlalchemy import text
from sqlmodel import Session, create_engine

from src.core import focus_engine as focus_module
from src.core.focus_engine import FocusEngine
from src.core.models import DatabaseManager, Task, TASK_ADDED_COLUMNS
from src.core.sqlite_add_missing_columns_migration import ensure_columns


@pytest.fixture
def mgr(memory_engine):
    m = DatabaseManager.__new__(DatabaseManager)  # bỏ __init__ để không đụng DB thật
    m.engine = memory_engine
    return m


def _columns(engine) -> dict:
    with engine.connect() as conn:
        return {r[1]: r for r in conn.execute(text('PRAGMA table_info("task")'))}


def test_migration_adds_columns_to_legacy_db_idempotently(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE task (id TEXT PRIMARY KEY, title TEXT NOT NULL, status TEXT)"))
        conn.execute(text("INSERT INTO task (id, title, status) VALUES ('a', 'cũ', 'todo')"))

    assert sorted(ensure_columns(engine, "task", TASK_ADDED_COLUMNS)) == ["matrix_order", "notes", "quadrant"]
    assert ensure_columns(engine, "task", TASK_ADDED_COLUMNS) == []  # lần 2: không làm gì

    with Session(engine) as s:
        row = s.exec(text("SELECT quadrant, matrix_order, title FROM task")).one()
    assert (row[0], row[1], row[2]) == (None, 0.0, "cũ")
    engine.dispose()


def test_migration_skips_missing_table_and_rejects_bad_identifier(memory_engine):
    assert ensure_columns(create_engine("sqlite://"), "task", TASK_ADDED_COLUMNS) == []
    with pytest.raises(ValueError):
        ensure_columns(memory_engine, "task; DROP TABLE task", {"x": "INTEGER"})


def test_set_quadrant_validates_and_updates(mgr):
    t = mgr.add_task("A")
    assert t.quadrant is None and t.matrix_order == 0.0
    out = mgr.set_task_quadrant(t.id, 1, order=2.5)
    assert (out.quadrant, out.matrix_order, out.synced_to_hermes) == (1, 2.5, False)
    assert mgr.set_task_quadrant(t.id, None).quadrant is None
    assert mgr.set_task_quadrant("khong-co", 2) is None
    for bad in (0, 5, True):
        with pytest.raises(ValueError):
            mgr.set_task_quadrant(t.id, bad)
    with pytest.raises(ValueError):
        mgr.add_task("B", quadrant=9)
    assert mgr.add_task("C", quadrant=3).quadrant == 3


def test_next_important_orders_q1_before_q2_then_matrix_order(mgr):
    q2 = mgr.add_task("q2", quadrant=2)
    q1b = mgr.add_task("q1b", quadrant=1)
    q1a = mgr.add_task("q1a", quadrant=1)
    mgr.reorder_quadrant(1, [q1a.id, q1b.id])
    assert [t.title for t in mgr.next_important_tasks()] == ["q1a", "q1b", "q2"]
    assert [t.title for t in mgr.next_important_tasks(limit=1)] == ["q1a"]
    assert q2.id


def test_next_important_excludes_done_archived_and_other_quadrants_includes_parked(mgr):
    done = mgr.add_task("done", quadrant=1)
    mgr.mark_task_done(done.id)
    arch = mgr.add_task("arch", quadrant=1)
    with Session(mgr.engine) as s:
        t = s.get(Task, arch.id)
        t.status = "archived"
        s.add(t)
        s.commit()
    mgr.add_task("q3", quadrant=3)
    mgr.add_task("q4", quadrant=4)
    mgr.add_task("none")
    parked = mgr.add_task("ý tưởng", category="parked_idea", quadrant=2)
    busy = mgr.add_task("busy", quadrant=2)
    mgr.set_task_quadrant(busy.id, 2, order=-1)
    assert [t.title for t in mgr.next_important_tasks()] == ["busy", "ý tưởng"]
    assert parked.id


def test_reorder_ignores_unknown_ids_and_wrong_column(mgr):
    a, b = mgr.add_task("a", quadrant=1), mgr.add_task("b", quadrant=2)
    mgr.reorder_quadrant(1, ["khong-co", b.id, a.id])
    with Session(mgr.engine) as s:
        assert s.get(Task, a.id).matrix_order == 2.0
        assert s.get(Task, b.id).matrix_order == 0.0  # khác cột → giữ nguyên


@pytest.fixture
def focus(mgr, monkeypatch):
    monkeypatch.setattr(focus_module, "db", mgr)
    audio = SimpleNamespace(play_chime=lambda: None, toggle_ambient=lambda: None, is_ambient_playing=False)
    engine = FocusEngine(audio_manager=audio)
    yield engine
    engine.tick_timer.stop()
    engine.ipc_timer.stop()


def test_session_started_emitted_on_start_not_on_resume(focus):
    seen = []
    focus.session_started.connect(lambda tid, title: seen.append((tid, title)))
    focus.start_focus_session("Viết báo cáo", 25, task_id="t1")
    focus.start_focus_session("Không task", 25)
    assert seen == [("t1", "Viết báo cáo"), ("", "Không task")]
    focus.pause_or_resume()  # pause
    focus.pause_or_resume()  # resume
    assert len(seen) == 2


def test_task_added_emitted_with_new_parked_idea(focus, mgr):
    seen = []
    focus.task_added.connect(lambda tid, title: seen.append((tid, title)))
    focus.record_distraction("  gọi điện cho khách ")
    focus.record_distraction("   ")
    focus.record_distraction(None)
    assert len(seen) == 1 and seen[0][1] == "gọi điện cho khách"
    with Session(mgr.engine) as s:
        assert s.get(Task, seen[0][0]).category == "parked_idea"
