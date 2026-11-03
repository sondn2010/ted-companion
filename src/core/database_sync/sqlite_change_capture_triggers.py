"""Ghi nhận mọi thay đổi trên bảng đồng bộ bằng trigger SQLite → bảng sync_outbox.

Không cần sửa repository nào: INSERT/UPDATE/DELETE (kể cả xoá cứng) đều tự vào outbox.
Lúc áp dữ liệu kéo từ server về, đặt cờ sync_state.applying_remote = '1' trong CÙNG transaction
để trigger bỏ qua (không đẩy ngược lại); kết nối khác không thấy cờ chưa commit nên vẫn được ghi nhận.
"""

from sqlalchemy.engine import Connection, Engine

from src.core.database_sync.synced_table_registry import SYNCED_TABLES, primary_key_columns

# Mốc thời gian cho lần đưa toàn bộ dữ liệu cũ vào outbox: cũ hơn mọi thay đổi thật,
# nên khi máy thứ 2 tham gia, bản trên server thắng còn dòng chỉ có ở máy này vẫn được đẩy lên.
INITIAL_CHANGED_AT = "1970-01-01T00:00:00.000Z"

_NOW = "strftime('%Y-%m-%dT%H:%M:%fZ', 'now')"
_NOT_APPLYING = "NOT EXISTS (SELECT 1 FROM sync_state WHERE key = 'applying_remote' AND value = '1')"

_STATE_DDL = (
    "CREATE TABLE IF NOT EXISTS sync_outbox (table_name TEXT NOT NULL, pk TEXT NOT NULL, "
    "changed_at TEXT NOT NULL, PRIMARY KEY (table_name, pk))",
    "CREATE TABLE IF NOT EXISTS sync_state (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
)


def pk_json_expr(row_alias: str, pk_cols: list[str]) -> str:
    return "json_array(" + ", ".join(f'{row_alias}."{c}"' for c in pk_cols) + ")"


def _outbox_insert(table: str, pk_expr: str) -> str:
    return f"INSERT OR REPLACE INTO sync_outbox (table_name, pk, changed_at) VALUES ('{table}', {pk_expr}, {_NOW});"


def _trigger_ddl(table: str) -> list[str]:
    pk_cols = primary_key_columns(table)
    new_pk, old_pk = pk_json_expr("NEW", pk_cols), pk_json_expr("OLD", pk_cols)
    head = 'CREATE TRIGGER IF NOT EXISTS "sync_{t}_{op}" AFTER {OP} ON "{t}" WHEN ' + _NOT_APPLYING + " BEGIN "
    return [
        head.format(t=table, op="ins", OP="INSERT") + _outbox_insert(table, new_pk) + " END",
        # Đổi khoá chính: khoá cũ không còn dòng → lúc đẩy lên được coi là đã xoá
        head.format(t=table, op="upd", OP="UPDATE")
        + _outbox_insert(table, old_pk) + " " + _outbox_insert(table, new_pk) + " END",
        head.format(t=table, op="del", OP="DELETE") + _outbox_insert(table, old_pk) + " END",
    ]


def install_sync_triggers(engine: Engine) -> None:
    """Tạo sync_outbox, sync_state và trigger cho mọi bảng đồng bộ (idempotent)."""
    with engine.begin() as conn:
        for ddl in _STATE_DDL:
            conn.exec_driver_sql(ddl)
        for table in SYNCED_TABLES:
            for ddl in _trigger_ddl(table):
                conn.exec_driver_sql(ddl)


def enqueue_all_existing_rows(conn: Connection) -> None:
    """Đưa mọi dòng hiện có vào outbox với mốc INITIAL_CHANGED_AT (lần bật đồng bộ đầu tiên)."""
    for table in SYNCED_TABLES:
        pk = pk_json_expr(f'"{table}"', primary_key_columns(table))
        conn.exec_driver_sql(
            f"INSERT OR IGNORE INTO sync_outbox (table_name, pk, changed_at) "
            f"SELECT '{table}', {pk}, '{INITIAL_CHANGED_AT}' FROM \"{table}\""
        )


def get_state(conn: Connection, key: str) -> str | None:
    row = conn.exec_driver_sql("SELECT value FROM sync_state WHERE key = ?", (key,)).first()
    return None if row is None else row[0]


def set_state(conn: Connection, key: str, value: str) -> None:
    conn.exec_driver_sql("INSERT OR REPLACE INTO sync_state (key, value) VALUES (?, ?)", (key, value))
