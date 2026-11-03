"""Bảng chung ted_sync_row trên PostgreSQL: mỗi dòng SQLite = 1 bản ghi jsonb, khoá (table_name, pk).

Không mirror schema từng bảng → Ted thêm cột/bảng không cần migration phía Postgres;
API cho app mobile sau này đọc/ghi đúng bảng này.
"""

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

_SCHEMA_RE = re.compile(r"^[a-z_][a-z0-9_]*$")


@dataclass
class SyncRow:
    table_name: str
    pk: str                      # json_array các giá trị khoá chính, vd '["abc"]'
    data: Optional[dict]         # None khi deleted
    deleted: bool
    changed_at: str              # ISO UTC mili giây 'YYYY-MM-DDTHH:MM:SS.mmmZ' (so sánh chuỗi được)
    device_id: str
    server_seq: int = 0


def to_iso_ms(moment: datetime) -> str:
    moment = moment.astimezone(timezone.utc)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"


def _table(schema: str) -> sql.Composed:
    if not _SCHEMA_RE.match(schema):
        raise ValueError(f"Tên schema không hợp lệ: {schema!r}")
    return sql.SQL("{}.ted_sync_row").format(sql.Identifier(schema))


def ensure_schema(conn: psycopg.Connection, schema: str) -> None:
    table = _table(schema)
    with conn.transaction():
        conn.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema)))
        conn.execute(sql.SQL(
            "CREATE TABLE IF NOT EXISTS {} ("
            " table_name text NOT NULL, pk text NOT NULL, data jsonb, deleted boolean NOT NULL DEFAULT false,"
            " changed_at timestamptz NOT NULL, device_id text NOT NULL, server_seq bigserial,"
            " PRIMARY KEY (table_name, pk))"
        ).format(table))
        conn.execute(sql.SQL("CREATE INDEX IF NOT EXISTS ted_sync_row_seq ON {} (server_seq)").format(table))


def push_rows(conn: psycopg.Connection, schema: str, rows: list[SyncRow]) -> None:
    """Upsert, thay đổi mới hơn (hoặc bằng) thắng. Mỗi lần ghi nhận server_seq mới để máy khác kéo về."""
    table = _table(schema)
    upsert = sql.SQL(
        "INSERT INTO {t} (table_name, pk, data, deleted, changed_at, device_id) VALUES (%s, %s, %s, %s, %s, %s) "
        "ON CONFLICT (table_name, pk) DO UPDATE SET data = EXCLUDED.data, deleted = EXCLUDED.deleted, "
        "changed_at = EXCLUDED.changed_at, device_id = EXCLUDED.device_id, "
        "server_seq = nextval(pg_get_serial_sequence({qualified}, 'server_seq')) "
        "WHERE EXCLUDED.changed_at >= {t}.changed_at"
    ).format(t=table, qualified=sql.Literal(f"{schema}.ted_sync_row"))
    with conn.transaction():
        # Xếp hàng các lần đẩy: server_seq commit đúng thứ tự → con trỏ kéo về không bỏ sót dòng
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"ted_sync:{schema}",))
        with conn.cursor() as cur:
            cur.executemany(upsert, [
                (r.table_name, r.pk, None if r.data is None else Jsonb(r.data), r.deleted, r.changed_at, r.device_id)
                for r in rows
            ])


def fetch_rows_since(conn: psycopg.Connection, schema: str, cursor: int, limit: int) -> list[SyncRow]:
    query = sql.SQL(
        "SELECT table_name, pk, data, deleted, changed_at, device_id, server_seq FROM {} "
        "WHERE server_seq > %s ORDER BY server_seq LIMIT %s"
    ).format(_table(schema))
    with conn.transaction():
        records = conn.execute(query, (cursor, limit)).fetchall()
    return [
        SyncRow(table_name=t, pk=pk, data=data, deleted=deleted, changed_at=to_iso_ms(changed),
                device_id=device, server_seq=seq)
        for t, pk, data, deleted, changed, device, seq in records
    ]
