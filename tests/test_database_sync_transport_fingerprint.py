"""DatabaseSyncService qua SyncTransport (không cần Postgres): server giả trong bộ nhớ theo đúng luật LWW + server_seq.

Đổi đích đồng bộ (server/tài khoản khác) → đặt lại con trỏ kéo và đẩy lại toàn bộ dữ liệu cục bộ.
"""

from contextlib import contextmanager

from sqlmodel import Session, SQLModel, create_engine, select

from src.core.database_sync.postgres_sync_row_store import SyncRow
from src.core.database_sync.sqlite_change_capture_triggers import get_state, set_state
from src.core.database_sync.sqlite_postgres_sync_service import DatabaseSyncService
from src.core.models import Task


class FakeServer:
    def __init__(self):
        self.rows: dict[tuple[str, str], SyncRow] = {}
        self.seq = 0

    def push(self, rows):
        for r in rows:
            old = self.rows.get((r.table_name, r.pk))
            if old is None or r.changed_at >= old.changed_at:
                self.seq += 1
                self.rows[(r.table_name, r.pk)] = SyncRow(r.table_name, r.pk, r.data, r.deleted, r.changed_at,
                                                          r.device_id, self.seq)

    def fetch_since(self, cursor, limit):
        return sorted((r for r in self.rows.values() if r.server_seq > cursor), key=lambda r: r.server_seq)[:limit]


class FakeSession:
    def __init__(self, server, fingerprint, user_name):
        self._server = server
        self.fingerprint = fingerprint
        self.server_user_name = user_name

    def has_any_rows(self):
        return bool(self._server.rows)

    def push(self, rows):
        self._server.push(rows)

    def fetch_since(self, cursor, limit):
        return self._server.fetch_since(cursor, limit)


class FakeTransport:
    def __init__(self, server=None, fingerprint="fake|X", user_name=None):
        self.server = server or FakeServer()
        self.fingerprint = fingerprint
        self.user_name = user_name

    @contextmanager
    def session(self):
        yield FakeSession(self.server, self.fingerprint, self.user_name)


def _engine(path):
    import src.core.models  # noqa: F401

    engine = create_engine(f"sqlite:///{path}")
    SQLModel.metadata.create_all(engine)
    return engine


def _add_task(engine, task_id, title):
    with Session(engine) as s:
        s.add(Task(id=task_id, title=title))
        s.commit()


def _task_ids(engine):
    with Session(engine) as s:
        return {t.id for t in s.exec(select(Task))}


def _state(engine, key):
    with engine.connect() as conn:
        return get_state(conn, key)


def test_two_devices_sync_through_fake_transport(tmp_path):
    transport = FakeTransport()
    a, b = _engine(tmp_path / "a.db"), _engine(tmp_path / "b.db")
    sync_a, sync_b = DatabaseSyncService(a, transport), DatabaseSyncService(b, transport)
    _add_task(a, "t1", "Viết báo cáo")
    sync_a.sync_once()
    sync_b.sync_once()
    assert "t1" in _task_ids(b)


def test_first_fingerprint_stored_without_reset(tmp_path):
    engine = _engine(tmp_path / "a.db")
    service = DatabaseSyncService(engine, FakeTransport(fingerprint="fake|X"))
    with engine.begin() as conn:   # máy đã đồng bộ từ bản cũ (chưa có fingerprint)
        set_state(conn, "pull_cursor", "7")
        set_state(conn, "first_sync_done", "1")
    service.sync_once()
    assert _state(engine, "pull_cursor") == "7"
    assert _state(engine, "target_fingerprint") == "fake|X"


def test_fingerprint_change_resets_cursor_and_reuploads(tmp_path):
    engine = _engine(tmp_path / "a.db")
    _add_task(engine, "t1", "Một")
    x = FakeTransport(fingerprint="fake|X")
    DatabaseSyncService(engine, x).sync_once()
    other = _engine(tmp_path / "other.db")   # máy khác thêm việc lên server X → con trỏ cục bộ lớn hơn số dòng của Y
    for i in range(3):
        _add_task(other, f"x{i}", "X")
    DatabaseSyncService(other, x).sync_once()
    DatabaseSyncService(engine, x).sync_once()
    assert int(_state(engine, "pull_cursor")) > 1

    y = FakeTransport(fingerprint="fake|Y")
    DatabaseSyncService(engine, y).sync_once()
    assert {pk for _, pk in y.server.rows} >= {'["t1"]', '["x0"]', '["x1"]', '["x2"]'}
    assert _state(engine, "pull_cursor") == str(y.server.seq)
    assert _state(engine, "target_fingerprint") == "fake|Y"


def test_server_user_name_passed_through(tmp_path):
    engine = _engine(tmp_path / "a.db")
    result = DatabaseSyncService(engine, FakeTransport(user_name="An")).sync_once()
    assert result.server_user_name == "An"
