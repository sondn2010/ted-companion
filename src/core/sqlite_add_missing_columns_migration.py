"""Nâng cấp SQLite tại chỗ: create_all không ALTER, nên thêm cột còn thiếu bằng PRAGMA + ALTER TABLE."""

import logging
import re
from typing import Mapping

from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger("ted")

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def ensure_columns(engine: Engine, table: str, columns: Mapping[str, str]) -> list[str]:
    """Thêm các cột chưa có vào bảng (idempotent). Trả danh sách cột vừa thêm.

    columns: {tên_cột: "KIỂU + ràng buộc"} do code gọi cung cấp (không phải input người dùng).
    Bảng chưa tồn tại → bỏ qua (create_all sẽ tạo đủ cột).
    """
    if not _IDENT_RE.match(table) or not all(_IDENT_RE.match(c) for c in columns):
        raise ValueError("Tên bảng/cột không hợp lệ")
    added: list[str] = []
    with engine.begin() as conn:
        existing = {row[1] for row in conn.execute(text(f'PRAGMA table_info("{table}")'))}
        if not existing:
            return added
        for name, ddl in columns.items():
            if name in existing:
                continue
            conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{name}" {ddl}'))
            added.append(name)
    if added:
        logger.info("Đã thêm cột %s vào bảng %s", ", ".join(added), table)
    return added
