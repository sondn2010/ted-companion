"""Một vòng đồng bộ: đẩy sync_outbox lên server (PostgreSQL hoặc HTTP API) rồi kéo các dòng mới hơn con trỏ về SQLite.

Xung đột = thay đổi mới nhất thắng theo từng dòng (changed_at). Chạy trên luồng nền, KHÔNG gọi từ luồng GUI.
"""

import json
import logging
from dataclasses import dataclass
from typing import Optional
from uuid import uuid4

from sqlalchemy.engine import Connection, Engine

from src.core.database_sync.postgres_sync_row_store import SyncRow
from src.core.database_sync.sync_transport import SyncSession, SyncTransport
from src.core.database_sync.sqlite_change_capture_triggers import (
    enqueue_all_existing_rows,
    get_state,
    install_sync_triggers,
    set_state,
)
from src.core.database_sync.synced_table_registry import SYNCED_TABLES, primary_key_columns
from src.core.models import WELCOME_TASK_TITLES

logger = logging.getLogger("ted")

BATCH_SIZE = 500


@dataclass
class SyncResult:
    pushed: int = 0
    pulled: int = 0
    skipped: int = 0   # dòng kéo về vướng ràng buộc UNIQUE/NOT NULL cục bộ → giữ bản cục bộ
    server_user_name: Optional[str] = None   # tên tài khoản phía server (chế độ API)


class DatabaseSyncService:
    def __init__(self, engine: Engine, transport: SyncTransport):
        self._engine = engine
        self._transport = transport
        self._columns: dict[str, set[str]] = {}
        install_sync_triggers(engine)
        with engine.begin() as conn:
            self.device_id = get_state(conn, "device_id") or str(uuid4())
            set_state(conn, "device_id", self.device_id)
            if get_state(conn, "initial_enqueued") is None:
                enqueue_all_existing_rows(conn)
                set_state(conn, "initial_enqueued", "1")

    def sync_once(self) -> SyncResult:
        result = SyncResult()
        with self._transport.session() as remote:
            result.server_user_name = remote.server_user_name
            self._check_target(remote.fingerprint)
            with self._engine.connect() as conn:
                first_sync = get_state(conn, "first_sync_done") is None
            if first_sync and remote.has_any_rows():
                self._drop_untouched_welcome_tasks()  # máy tham gia sau: không đẩy task mẫu thứ 2 lên
            result.pushed = self._push(remote)
            if first_sync:
                with self._engine.begin() as conn:
                    set_state(conn, "first_sync_done", "1")
            self._pull(remote, result)
        return result

    def _check_target(self, fingerprint: str) -> None:
        """Đổi server/tài khoản → đẩy lại mọi dòng (mốc 1970: bản trên server thắng) và kéo lại từ đầu.

        Bản cũ chưa lưu fingerprint → chỉ ghi lại, không đặt lại."""
        with self._engine.begin() as conn:
            current = get_state(conn, "target_fingerprint")
            if current is not None and current != fingerprint:
                logger.info("Đích đồng bộ đã đổi → đặt lại con trỏ và đẩy lại dữ liệu cục bộ")
                conn.exec_driver_sql("DELETE FROM sync_state WHERE key IN ('pull_cursor', 'first_sync_done')")
                enqueue_all_existing_rows(conn)
            if current != fingerprint:
                set_state(conn, "target_fingerprint", fingerprint)

    def _drop_untouched_welcome_tasks(self) -> None:
        marks = ", ".join("?" * len(WELCOME_TASK_TITLES))
        untouched = (f"title IN ({marks}) AND status = 'todo' AND completed_pomodoros = 0 "
                     "AND notes = '' AND quadrant IS NULL")
        with self._engine.begin() as conn:
            ids = [r[0] for r in conn.exec_driver_sql(f"SELECT id FROM task WHERE {untouched}", WELCOME_TASK_TITLES)]
            set_state(conn, "applying_remote", "1")
            for task_id in ids:
                conn.exec_driver_sql("DELETE FROM task WHERE id = ?", (task_id,))
                conn.exec_driver_sql("DELETE FROM sync_outbox WHERE table_name = 'task' AND pk = ?",
                                     (json.dumps([task_id]),))
            set_state(conn, "applying_remote", "0")

    # ---- đẩy lên ----
    def _push(self, remote: SyncSession) -> int:
        pushed = 0
        while True:
            with self._engine.connect() as conn:
                pending = conn.exec_driver_sql(
                    "SELECT table_name, pk, changed_at FROM sync_outbox ORDER BY changed_at LIMIT ?", (BATCH_SIZE,)
                ).all()
                rows = [self._read_local(conn, t, pk, changed) for t, pk, changed in pending if t in SYNCED_TABLES]
            if not pending:
                return pushed
            remote.push(rows)
            with self._engine.begin() as conn:
                # Chỉ xoá mục chưa bị sửa tiếp trong lúc đang đẩy (changed_at còn khớp)
                conn.exec_driver_sql(
                    "DELETE FROM sync_outbox WHERE table_name = ? AND pk = ? AND changed_at = ?",
                    [tuple(p) for p in pending],
                )
            pushed += len(rows)

    def _read_local(self, conn: Connection, table: str, pk: str, changed_at: str) -> SyncRow:
        where, values = self._pk_where(table, pk)
        record = conn.exec_driver_sql(f'SELECT * FROM "{table}" WHERE {where}', values).mappings().first()
        return SyncRow(table_name=table, pk=pk, data=None if record is None else dict(record),
                       deleted=record is None, changed_at=changed_at, device_id=self.device_id)

    # ---- kéo về ----
    def _pull(self, remote: SyncSession, result: SyncResult) -> None:
        while True:
            with self._engine.connect() as conn:
                cursor = int(get_state(conn, "pull_cursor") or 0)
            rows = remote.fetch_since(cursor, BATCH_SIZE)
            if not rows:
                return
            with self._engine.begin() as conn:
                set_state(conn, "applying_remote", "1")
                for row in rows:
                    if row.device_id != self.device_id and row.table_name in SYNCED_TABLES:
                        self._apply_remote(conn, row, result)
                set_state(conn, "applying_remote", "0")
                set_state(conn, "pull_cursor", str(rows[-1].server_seq))

    def _apply_remote(self, conn: Connection, row: SyncRow, result: SyncResult) -> None:
        local = conn.exec_driver_sql(
            "SELECT changed_at FROM sync_outbox WHERE table_name = ? AND pk = ?", (row.table_name, row.pk)
        ).first()
        if local is not None and local[0] > row.changed_at:
            return  # sửa cục bộ mới hơn → giữ, lần đẩy sau sẽ ghi đè server
        if row.deleted:
            where, values = self._pk_where(row.table_name, row.pk)
            conn.exec_driver_sql(f'DELETE FROM "{row.table_name}" WHERE {where}', values)
        elif not self._upsert_local(conn, row.table_name, row.data):
            result.skipped += 1
            logger.warning("Bỏ qua dòng đồng bộ %s %s: vướng ràng buộc cục bộ", row.table_name, row.pk)
            return
        if local is not None:
            conn.exec_driver_sql("DELETE FROM sync_outbox WHERE table_name = ? AND pk = ?", (row.table_name, row.pk))
        result.pulled += 1

    def _upsert_local(self, conn: Connection, table: str, data: dict) -> bool:
        """UPDATE theo khoá, chưa có thì INSERT. OR IGNORE: vướng UNIQUE khác (vd xpevent.dedupe_key) → False."""
        local_cols = self._local_columns(conn, table)
        cols = [c for c in data if c in local_cols]  # bản Ted khác phiên bản: bỏ cột cục bộ không có
        pk_cols = primary_key_columns(table)
        where = " AND ".join(f'"{c}" = ?' for c in pk_cols)
        pk_values = tuple(data[c] for c in pk_cols)
        exists = conn.exec_driver_sql(f'SELECT 1 FROM "{table}" WHERE {where}', pk_values).first()
        if exists:
            others = [c for c in cols if c not in pk_cols]
            if not others:
                return True
            assignments = ", ".join(f'"{c}" = ?' for c in others)
            done = conn.exec_driver_sql(
                f'UPDATE OR IGNORE "{table}" SET {assignments} WHERE {where}',
                tuple(data[c] for c in others) + pk_values,
            )
        else:
            names = ", ".join(f'"{c}"' for c in cols)
            done = conn.exec_driver_sql(
                f'INSERT OR IGNORE INTO "{table}" ({names}) VALUES ({", ".join("?" * len(cols))})',
                tuple(data[c] for c in cols),
            )
        return done.rowcount == 1

    def _local_columns(self, conn: Connection, table: str) -> set[str]:
        if table not in self._columns:
            self._columns[table] = {r[1] for r in conn.exec_driver_sql(f'PRAGMA table_info("{table}")')}
        return self._columns[table]

    @staticmethod
    def _pk_where(table: str, pk: str) -> tuple[str, tuple]:
        pk_cols = primary_key_columns(table)
        return " AND ".join(f'"{c}" = ?' for c in pk_cols), tuple(json.loads(pk))
