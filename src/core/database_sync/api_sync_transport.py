"""SyncTransport qua HTTP tới ted-sync-api (khoá API của người dùng, Bearer). Khoá API nằm trong keyring hệ điều hành.

Mỗi phiên gọi /v1/me trước: biết tài khoản (fingerprint đổi khi dán khoá của người khác) và tên người dùng.
"""

from contextlib import contextmanager
from dataclasses import asdict
from typing import Callable, Iterator, Optional

import httpx
import keyring

from src.core.database_sync.postgres_sync_row_store import SyncRow

_KEYRING_SERVICE = "TedCompanion.DatabaseSync"
_KEYRING_ENTRY = "api_key"
TIMEOUT_SECONDS = 10
PUSH_CHUNK = 500   # giới hạn số dòng mỗi lần đẩy của server


class ApiKeyRejected(RuntimeError):
    """Server trả 401: khoá sai, đã thu hồi hoặc tài khoản bị khoá."""


def load_api_key() -> str:
    return keyring.get_password(_KEYRING_SERVICE, _KEYRING_ENTRY) or ""


def save_api_key(key: str) -> None:
    keyring.set_password(_KEYRING_SERVICE, _KEYRING_ENTRY, key)


def _check(response: httpx.Response) -> httpx.Response:
    if response.status_code == 401:
        raise ApiKeyRejected(response.text)
    response.raise_for_status()
    return response


def _client(api_url: str, api_key: str, factory: Callable[..., httpx.Client]) -> httpx.Client:
    return factory(base_url=api_url, timeout=TIMEOUT_SECONDS, headers={"Authorization": f"Bearer {api_key}"})


def fetch_me(api_url: str, api_key: str, client: Optional[httpx.Client] = None) -> dict:
    """{"user_id", "name"} của khoá này (nút Kiểm tra kết nối)."""
    with client or _client(api_url, api_key, httpx.Client) as c:
        return _check(c.get("/v1/me", headers={"Authorization": f"Bearer {api_key}"})).json()


class _ApiSession:
    def __init__(self, client: httpx.Client, api_url: str):
        self._client = client
        me = _check(client.get("/v1/me")).json()
        self.fingerprint = f"api|{api_url}|{me['user_id']}"
        self.server_user_name: Optional[str] = me.get("name") or None

    def has_any_rows(self) -> bool:
        return bool(self.fetch_since(0, 1))

    def push(self, rows: list[SyncRow]) -> None:
        for start in range(0, len(rows), PUSH_CHUNK):
            payload = [{k: v for k, v in asdict(r).items() if k != "server_seq"} for r in rows[start:start + PUSH_CHUNK]]
            _check(self._client.post("/v1/sync/push", json={"rows": payload}))

    def fetch_since(self, cursor: int, limit: int) -> list[SyncRow]:
        body = _check(self._client.get("/v1/sync/pull", params={"cursor": cursor, "limit": limit})).json()
        return [SyncRow(**row) for row in body["rows"]]


class ApiSyncTransport:
    def __init__(self, api_url: str, api_key_fn: Callable[[], str] = load_api_key,
                 client_factory: Optional[Callable[..., httpx.Client]] = None):
        self._api_url = api_url
        self._api_key_fn = api_key_fn
        self._factory = client_factory or httpx.Client

    @contextmanager
    def session(self) -> Iterator[_ApiSession]:
        with _client(self._api_url, self._api_key_fn(), self._factory) as client:
            yield _ApiSession(client, self._api_url)
