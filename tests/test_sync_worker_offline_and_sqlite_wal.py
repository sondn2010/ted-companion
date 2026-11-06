"""
sync_worker: dừng khi Hermes offline (qua HermesUnavailableError, không so khớp chuỗi) và
KHÔNG đánh dấu synced cho phiên chưa gửi được. Dùng SQLite in-memory qua conftest.memory_engine.
Kèm kiểm tra PRAGMA của engine SQLite thật (WAL, busy_timeout) trong models.py.
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
from sqlmodel import Session

from src.bridge import sync_worker as sync_module
from src.bridge.hermes_client import HermesBrainClient
from src.bridge.sync_worker import HermesSyncWorker
from src.core.connection_registry_and_settings_migration import HermesConnection
from src.core.models import DatabaseManager, FocusSession, db

OK_BODY = {
    "id": "x", "object": "chat.completion", "created": 0, "model": "hermes-agent",
    "choices": [{"index": 0, "message": {"role": "assistant", "content": "đã ghi nhận"}, "finish_reason": "stop"}],
}


def _memory_db(engine) -> DatabaseManager:
    mgr = DatabaseManager.__new__(DatabaseManager)  # bỏ __init__ để không đụng DB thật
    mgr.engine = engine
    return mgr


def _seed_sessions(engine, count: int):
    with Session(engine) as session:
        for i in range(count):
            session.add(FocusSession(
                intent_statement=f"việc {i}", planned_minutes=25, actual_minutes=25,
                ended_at=datetime.now(timezone.utc),
            ))
        session.commit()


def _client_scripted(outcomes: list[str]) -> tuple[HermesBrainClient, list[str]]:
    """outcomes: 'ok' trả 200, 'offline' ném lỗi kết nối. Ghi lại số request thực tế."""
    queue, calls = list(outcomes), []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append("request")
        if queue.pop(0) == "offline":
            raise httpx.ConnectError("refused", request=request)
        return httpx.Response(200, json=OK_BODY)

    conn = HermesConnection(id="local", name="Local", base_url="http://hermes.test/v1", api_key="k")
    return HermesBrainClient(conn, http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler))), calls


def _wire(monkeypatch, mgr: DatabaseManager, client: HermesBrainClient):
    monkeypatch.setattr(sync_module, "db", mgr)
    monkeypatch.setattr(sync_module, "hermes_client_pool", SimpleNamespace(for_module=lambda _m: client))


async def test_offline_on_first_session_stops_and_keeps_all_unsynced(memory_engine, monkeypatch):
    mgr = _memory_db(memory_engine)
    _seed_sessions(memory_engine, 3)
    client, calls = _client_scripted(["offline"])
    _wire(monkeypatch, mgr, client)

    synced = await HermesSyncWorker().sync_completed_sessions()

    assert synced == 0
    assert len(calls) == 1  # dừng ngay, không thử các phiên còn lại
    assert len(mgr.get_unsynced_sessions()) == 3


async def test_offline_midway_marks_only_delivered_sessions(memory_engine, monkeypatch):
    mgr = _memory_db(memory_engine)
    _seed_sessions(memory_engine, 3)
    client, calls = _client_scripted(["ok", "offline"])
    _wire(monkeypatch, mgr, client)

    synced = await HermesSyncWorker().sync_completed_sessions()

    assert synced == 1
    assert len(calls) == 2
    assert len(mgr.get_unsynced_sessions()) == 2


async def test_all_delivered_marks_every_session_synced(memory_engine, monkeypatch):
    mgr = _memory_db(memory_engine)
    _seed_sessions(memory_engine, 2)
    client, _ = _client_scripted(["ok", "ok"])
    _wire(monkeypatch, mgr, client)

    assert await HermesSyncWorker().sync_completed_sessions() == 2
    assert mgr.get_unsynced_sessions() == []


def test_sqlite_engine_runs_in_wal_mode_with_busy_timeout():
    with db.engine.connect() as conn:
        assert conn.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"
        assert conn.exec_driver_sql("PRAGMA busy_timeout").scalar() == 5000
        assert conn.exec_driver_sql("PRAGMA synchronous").scalar() == 1  # NORMAL
