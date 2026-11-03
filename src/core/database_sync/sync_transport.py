"""Giao tiếp giữa DatabaseSyncService và server đồng bộ: PostgreSQL trực tiếp hoặc HTTP API (ted-sync-api).

Một phiên (session) = một vòng đồng bộ. fingerprint định danh server + tài khoản: đổi fingerprint → service
đặt lại con trỏ kéo và đẩy lại toàn bộ dữ liệu cục bộ.
"""

from typing import ContextManager, Optional, Protocol

from src.core.database_sync.postgres_sync_row_store import SyncRow


class SyncSession(Protocol):
    fingerprint: str
    server_user_name: Optional[str]   # tên người dùng phía server (chỉ API); None với Postgres

    def has_any_rows(self) -> bool: ...

    def push(self, rows: list[SyncRow]) -> None: ...

    def fetch_since(self, cursor: int, limit: int) -> list[SyncRow]: ...


class SyncTransport(Protocol):
    def session(self) -> ContextManager[SyncSession]: ...
