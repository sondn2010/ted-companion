"""Module tiện ích tìm kiếm và lọc kết nối Não AI (dùng chung cho bảng Quản lý kết nối & Dialog chọn Não AI)."""

from typing import Iterable
from PySide6.QtCore import Qt
from src.core.connection_registry_and_settings_migration import HermesConnection


def connection_matches_query(conn: HermesConnection, query: str) -> bool:
    """Kiểm tra một kết nối Não AI có khớp với từ khóa tìm kiếm (tên, model, URL, ID) hay không."""
    q = query.strip().lower()
    if not q:
        return True
    haystack = f"{conn.name} {conn.model} {conn.base_url} {conn.id}".lower()
    return all(token in haystack for token in q.split())


def filter_connection_table_rows(
    table,
    connections: Iterable[HermesConnection],
    query: str,
    id_col: int = 0,
) -> int:
    """
    Ẩn/hiện các dòng trong table widget dựa trên từ khóa tìm kiếm.
    Duyệt qua từng dòng, lấy conn_id từ ItemDataRole.UserRole ở cột id_col.
    Trả về số lượng dòng đang hiển thị.
    """
    visible_count = 0
    q = query.strip().lower()
    conn_by_id = {c.id: c for c in connections}

    for r in range(table.rowCount()):
        item = table.item(r, id_col)
        conn_id = item.data(Qt.ItemDataRole.UserRole) if item else ""
        conn = conn_by_id.get(conn_id)
        if not conn:
            table.setRowHidden(r, False)
            visible_count += 1
            continue
        matches = connection_matches_query(conn, q)
        table.setRowHidden(r, not matches)
        if matches:
            visible_count += 1

    return visible_count
