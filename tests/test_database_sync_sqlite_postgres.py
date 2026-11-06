"""Đồng bộ SQLite ⇄ PostgreSQL: trigger ghi outbox (chạy mọi nơi) + 2 máy đồng bộ qua Postgres thật.

Test Postgres cần TED_TEST_PG_URL; thiếu → skip. Postgres test chạy bằng Docker:
  docker run -d --name ted-test-pg -e POSTGRES_PASSWORD=ted -e POSTGRES_DB=ted_test -p 55432:5432 postgres:16-alpine
  TED_TEST_PG_URL=postgresql://postgres:ted@localhost:55432/ted_test
Mỗi test dùng schema riêng và xoá sau khi chạy.
"""

import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from src.core.database_sync.sqlite_change_capture_triggers import INITIAL_CHANGED_AT, install_sync_triggers
from src.core.database_sync.postgres_sync_transport import PostgresSyncTransport
from src.core.database_sync.sqlite_postgres_sync_service import DatabaseSyncService
from src.core.database_sync.synced_table_registry import SYNCED_TABLES
from src.core.gamification.gamification_table_models import BadgeUnlock, XpEvent
from src.core.models import Task

PG_URL = os.environ.get("TED_TEST_PG_URL")


def _make_engine(path):
    import src.core.models  # noqa: F401

    engine = create_engine(f"sqlite:///{path}")
    SQLModel.metadata.create_all(engine)
    return engine


def _outbox(engine):
    with engine.connect() as conn:
        return conn.exec_driver_sql("SELECT table_name, pk, changed_at FROM sync_outbox ORDER BY pk").all()


def _add(engine, *rows):
    with Session(engine) as s:
        for r in rows:
            s.add(r)
        s.commit()


# ---------- SQLite: trigger ----------

def test_every_synced_table_exists_in_model_metadata():
    import src.core.models  # noqa: F401

    assert set(SYNCED_TABLES) <= set(SQLModel.metadata.tables)


def test_triggers_capture_insert_update_and_hard_delete(tmp_path):
    engine = _make_engine(tmp_path / "a.db")
    install_sync_triggers(engine)
    _add(engine, Task(id="t1", title="Viết báo cáo"))
    assert [(t, pk) for t, pk, _ in _outbox(engine)] == [("task", '["t1"]')]
    first_stamp = _outbox(engine)[0][2]

    with engine.begin() as conn:
        conn.exec_driver_sql("DELETE FROM sync_outbox")
        conn.exec_driver_sql("UPDATE task SET title = 'Sửa' WHERE id = 't1'")
    assert [(t, pk) for t, pk, _ in _outbox(engine)] == [("task", '["t1"]')]
    assert _outbox(engine)[0][2] >= first_stamp

    with engine.begin() as conn:
        conn.exec_driver_sql("DELETE FROM sync_outbox")
        conn.exec_driver_sql("DELETE FROM task WHERE id = 't1'")
    assert [(t, pk) for t, pk, _ in _outbox(engine)] == [("task", '["t1"]')]
    engine.dispose()


def test_composite_key_and_local_only_tables(tmp_path):
    engine = _make_engine(tmp_path / "a.db")
    install_sync_triggers(engine)
    _add(engine, BadgeUnlock(badge_id="b1", week_start="2026-10-26"))
    with engine.begin() as conn:
        conn.exec_driver_sql("INSERT INTO appstatekv (key, value, updated_at) VALUES ('win', '1', '2026-10-29')")
    assert [(t, pk) for t, pk, _ in _outbox(engine)] == [("badgeunlock", '["b1","2026-10-26"]')]
    engine.dispose()


def test_applying_remote_flag_suppresses_triggers(tmp_path):
    engine = _make_engine(tmp_path / "a.db")
    install_sync_triggers(engine)
    with engine.begin() as conn:
        conn.exec_driver_sql("INSERT INTO sync_state VALUES ('applying_remote', '1')")
    _add(engine, Task(id="t1", title="Từ máy khác"))
    assert _outbox(engine) == []
    engine.dispose()


def test_first_enable_enqueues_existing_rows_with_initial_stamp(tmp_path):
    engine = _make_engine(tmp_path / "a.db")
    _add(engine, Task(id="old", title="Có từ trước khi bật đồng bộ"))
    DatabaseSyncService(engine, PostgresSyncTransport(lambda: None))
    assert _outbox(engine) == [("task", '["old"]', INITIAL_CHANGED_AT)]
    DatabaseSyncService(engine, PostgresSyncTransport(lambda: None))  # lần mở sau không đưa lại
    assert len(_outbox(engine)) == 1
    engine.dispose()


# ---------- 2 máy qua PostgreSQL ----------

@pytest.fixture
def pg_schema():
    if not PG_URL:
        pytest.skip("TED_TEST_PG_URL chưa đặt")
    import psycopg

    schema = f"ted_sync_test_{uuid4().hex[:8]}"
    yield schema
    with psycopg.connect(PG_URL, autocommit=True) as conn:
        conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')


@pytest.fixture
def two_machines(tmp_path, pg_schema):
    import psycopg

    def connect():
        return psycopg.connect(PG_URL, autocommit=True)

    engines = [_make_engine(tmp_path / "pc_a.db"), _make_engine(tmp_path / "pc_b.db")]
    services = [DatabaseSyncService(e, PostgresSyncTransport(connect, pg_schema)) for e in engines]
    yield engines, services
    for e in engines:
        e.dispose()


def _task(engine, task_id):
    with Session(engine) as s:
        return s.get(Task, task_id)


def test_insert_update_delete_propagate_between_machines(two_machines):
    (a, b), (sync_a, sync_b) = two_machines
    _add(a, Task(id="t1", title="Việc trên máy A"))
    assert sync_a.sync_once().pushed == 1
    assert sync_b.sync_once().pulled == 1
    assert _task(b, "t1").title == "Việc trên máy A"
    assert _outbox(b) == []  # dòng kéo về không bị đẩy ngược lên

    with b.begin() as conn:
        conn.exec_driver_sql("UPDATE task SET title = 'Sửa trên máy B' WHERE id = 't1'")
    sync_b.sync_once()
    sync_a.sync_once()
    assert _task(a, "t1").title == "Sửa trên máy B"

    with a.begin() as conn:
        conn.exec_driver_sql("DELETE FROM task WHERE id = 't1'")
    sync_a.sync_once()
    sync_b.sync_once()
    assert _task(b, "t1") is None


def test_newest_change_wins_on_conflict(two_machines):
    (a, b), (sync_a, sync_b) = two_machines
    _add(a, Task(id="t1", title="Gốc"))
    sync_a.sync_once()
    sync_b.sync_once()

    with a.begin() as conn:
        conn.exec_driver_sql("UPDATE task SET title = 'A sửa trước' WHERE id = 't1'")
    with b.begin() as conn:
        conn.exec_driver_sql("UPDATE task SET title = 'B sửa sau' WHERE id = 't1'")
        conn.exec_driver_sql("UPDATE sync_outbox SET changed_at = '2999-01-01T00:00:00.000Z'")  # chắc chắn mới hơn
    sync_a.sync_once()
    sync_b.sync_once()  # B mới hơn → bản của A trên server không ghi đè B
    sync_a.sync_once()
    assert _task(a, "t1").title == _task(b, "t1").title == "B sửa sau"


def test_composite_key_row_syncs(two_machines):
    (a, b), (sync_a, sync_b) = two_machines
    _add(a, BadgeUnlock(badge_id="b1", week_start="2026-10-26", unlocked_at=datetime(2026, 10, 27, tzinfo=timezone.utc)))
    sync_a.sync_once()
    sync_b.sync_once()
    with Session(b) as s:
        assert s.exec(select(BadgeUnlock)).one().badge_id == "b1"


def test_unique_conflict_keeps_local_row_and_counts_skip(two_machines):
    (a, b), (sync_a, sync_b) = two_machines
    common = dict(dedupe_key="focus:2026-10-29", local_date="2026-10-29", source_module="focus", engine="focus", kind="k", xp=10)
    _add(a, XpEvent(id="xa", **common))
    _add(b, XpEvent(id="xb", **common))
    sync_a.sync_once()
    assert sync_b.sync_once().skipped == 1
    with Session(b) as s:
        assert [x.id for x in s.exec(select(XpEvent)).all()] == ["xb"]


def test_joining_machine_keeps_server_version_and_adds_its_own_rows(tmp_path, pg_schema):
    import psycopg

    def connect():
        return psycopg.connect(PG_URL, autocommit=True)

    a = _make_engine(tmp_path / "pc_a.db")
    sync_a = DatabaseSyncService(a, PostgresSyncTransport(connect, pg_schema))
    _add(a, Task(id="shared", title="Bản mới trên máy A"))
    sync_a.sync_once()

    b = _make_engine(tmp_path / "pc_b.db")  # máy B có dữ liệu từ trước khi bật đồng bộ
    _add(b, Task(id="shared", title="Bản cũ trên máy B"), Task(id="only_b", title="Chỉ máy B có"))
    sync_b = DatabaseSyncService(b, PostgresSyncTransport(connect, pg_schema))
    sync_b.sync_once()
    sync_a.sync_once()

    assert _task(b, "shared").title == "Bản mới trên máy A"
    assert _task(a, "only_b").title == "Chỉ máy B có"
    a.dispose()
    b.dispose()


def test_joining_machine_drops_untouched_welcome_tasks_but_first_machine_keeps_them(tmp_path, pg_schema):
    import psycopg

    from src.core.models import WELCOME_TASK_TITLES

    def connect():
        return psycopg.connect(PG_URL, autocommit=True)

    def welcome_tasks(title=WELCOME_TASK_TITLES[0]):
        return [Task(id=f"w{uuid4().hex[:6]}", title=title), Task(id=f"w{uuid4().hex[:6]}", title=WELCOME_TASK_TITLES[1])]

    a = _make_engine(tmp_path / "pc_a.db")
    _add(a, *welcome_tasks())
    sync_a = DatabaseSyncService(a, PostgresSyncTransport(connect, pg_schema))
    sync_a.sync_once()  # máy đầu tiên: server rỗng → giữ task mẫu

    b = _make_engine(tmp_path / "pc_b.db")
    started = welcome_tasks()
    started[0].completed_pomodoros = 1  # task mẫu đã làm dở → giữ
    kept_id, dropped_id = started[0].id, started[1].id
    _add(b, *started)
    sync_b = DatabaseSyncService(b, PostgresSyncTransport(connect, pg_schema))
    sync_b.sync_once()
    sync_a.sync_once()

    with Session(b) as s:
        ids_b = {t.id for t in s.exec(select(Task)).all()}
    with Session(a) as s:
        ids_a = {t.id for t in s.exec(select(Task)).all()}
    assert dropped_id not in ids_b and kept_id in ids_b
    assert ids_a == ids_b and len(ids_a) == 3
    a.dispose()
    b.dispose()
