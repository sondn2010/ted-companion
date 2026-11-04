"""Chế độ API sync: ApiSyncTransport nói chuyện với ted-sync-api qua HTTP (giả bằng httpx.MockTransport)."""

import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest

from tests.qt_offscreen_app_helper import get_qapp

from src.config import settings
from src.core.database_sync.api_sync_transport import ApiKeyRejected, ApiSyncTransport, fetch_me
from src.core.database_sync.database_sync_config import DatabaseSyncConfig, build_export
from src.core.database_sync.database_sync_controller import DatabaseSyncController
from src.core.database_sync.postgres_sync_row_store import SyncRow
from src.core.database_sync.sqlite_postgres_sync_service import SyncResult
from src.core.i18n import tr

URL = "https://x.test"
KEY = "ted_secret_key"
ROW = SyncRow("task", '["t1"]', {"id": "t1"}, False, "2026-10-29T10:00:00.000Z", "dev-a")


def _transport(handler):
    def factory(**kwargs):
        return httpx.Client(transport=httpx.MockTransport(handler), **kwargs)

    return ApiSyncTransport(URL, lambda: KEY, client_factory=factory)


def _me_then(handler=None):
    def wrapped(request: httpx.Request):
        if request.url.path == "/v1/me":
            return httpx.Response(200, json={"user_id": "u1", "name": "An"})
        return handler(request)

    return wrapped


def test_session_fingerprint_and_name():
    with _transport(_me_then()).session() as s:
        assert s.fingerprint == "api|https://x.test|u1"
        assert s.server_user_name == "An"


def test_push_sends_bearer_and_rows():
    seen = []

    def handler(request):
        seen.append((request.headers["authorization"], request.url.path, json.loads(request.content)))
        return httpx.Response(200, json={"accepted": 1})

    with _transport(_me_then(handler)).session() as s:
        s.push([ROW])
    auth, path, body = seen[0]
    assert auth == f"Bearer {KEY}" and path == "/v1/sync/push"
    assert body["rows"][0] == {"table_name": "task", "pk": '["t1"]', "data": {"id": "t1"}, "deleted": False,
                               "changed_at": "2026-10-29T10:00:00.000Z", "device_id": "dev-a"}


def test_push_chunks_at_500_rows():
    sizes = []

    def handler(request):
        sizes.append(len(json.loads(request.content)["rows"]))
        return httpx.Response(200, json={"accepted": sizes[-1]})

    with _transport(_me_then(handler)).session() as s:
        s.push([ROW] * 1201)
    assert sizes == [500, 500, 201]


def test_fetch_maps_rows_and_has_any_rows():
    pulled = {**ROW.__dict__, "server_seq": 9}

    def handler(request):
        assert request.url.path == "/v1/sync/pull"
        rows = [pulled] if request.url.params["cursor"] == "0" else []
        return httpx.Response(200, json={"rows": rows, "next_cursor": 9})

    with _transport(_me_then(handler)).session() as s:
        assert s.fetch_since(0, 500) == [SyncRow(**pulled)]
        assert s.has_any_rows()
        assert s.fetch_since(9, 500) == []


def test_401_raises_api_key_rejected():
    with pytest.raises(ApiKeyRejected):
        with _transport(lambda r: httpx.Response(401, json={"detail": "invalid_api_key"})).session():
            pass


def test_connect_error_surfaces():
    def handler(request):
        raise httpx.ConnectError("unreachable", request=request)

    with pytest.raises(httpx.ConnectError):
        with _transport(handler).session():
            pass


def test_fetch_me_uses_key():
    def handler(request):
        assert request.headers["authorization"] == "Bearer k2"
        return httpx.Response(200, json={"user_id": "u9", "name": "Binh"})

    client = httpx.Client(base_url=URL, transport=httpx.MockTransport(handler))
    assert fetch_me(URL, "k2", client=client) == {"user_id": "u9", "name": "Binh"}


# ---- cấu hình ----

def test_api_url_normalized():
    config = DatabaseSyncConfig(mode="api_sync", api_url="  https://x.test/ ")
    assert config.api_url == "https://x.test"
    assert config.enabled
    assert not DatabaseSyncConfig(mode="api_sync").enabled


def test_export_includes_api_url_never_key():
    exported = build_export(DatabaseSyncConfig(mode="api_sync", api_url=URL))
    assert exported["database"]["api_url"] == URL
    assert not [k for k in exported["database"] if "key" in k or "password" in k]


# ---- controller: tên từ server, lỗi khoá ----

@pytest.fixture
def controller(monkeypatch):
    get_qapp()
    monkeypatch.setattr(settings, "save", lambda: None)
    return DatabaseSyncController()


def test_controller_fills_empty_user_name(controller, monkeypatch):
    monkeypatch.setattr(settings, "user_name", "")
    service = SimpleNamespace(sync_once=lambda: SyncResult(server_user_name="An"))
    asyncio.run(controller._run(service))
    assert settings.user_name == "An"


def test_controller_keeps_existing_user_name(controller, monkeypatch):
    monkeypatch.setattr(settings, "user_name", "Minh")
    asyncio.run(controller._run(SimpleNamespace(sync_once=lambda: SyncResult(server_user_name="An"))))
    assert settings.user_name == "Minh"


def test_controller_reports_rejected_key(controller):
    def boom():
        raise ApiKeyRejected("invalid_api_key")

    asyncio.run(controller._run(SimpleNamespace(sync_once=boom)))
    assert controller.status_text == tr("db_sync_api_key_rejected")
