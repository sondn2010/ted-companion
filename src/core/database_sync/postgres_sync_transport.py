"""SyncTransport kết nối thẳng PostgreSQL (bảng chung ted_sync_row), mỗi phiên mở 1 kết nối."""

from contextlib import contextmanager
from typing import Callable, Iterator

import psycopg

from src.core.database_sync.postgres_sync_row_store import SyncRow, ensure_schema, fetch_rows_since, push_rows


class _PostgresSession:
    server_user_name = None

    def __init__(self, conn: psycopg.Connection, schema: str, fingerprint: str):
        self._conn = conn
        self._schema = schema
        self.fingerprint = fingerprint

    def has_any_rows(self) -> bool:
        return bool(fetch_rows_since(self._conn, self._schema, 0, 1))

    def push(self, rows: list[SyncRow]) -> None:
        push_rows(self._conn, self._schema, rows)

    def fetch_since(self, cursor: int, limit: int) -> list[SyncRow]:
        return fetch_rows_since(self._conn, self._schema, cursor, limit)


class PostgresSyncTransport:
    """target: "host|port|database" (cùng schema) → định danh server cho fingerprint."""

    def __init__(self, connect: Callable[[], psycopg.Connection], schema: str = "ted_sync", target: str = ""):
        self._connect = connect
        self._schema = schema
        self._fingerprint = f"pg|{target}|{schema}"

    @contextmanager
    def session(self) -> Iterator[_PostgresSession]:
        with self._connect() as conn:
            ensure_schema(conn, self._schema)
            yield _PostgresSession(conn, self._schema, self._fingerprint)
