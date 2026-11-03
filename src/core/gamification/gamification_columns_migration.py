"""Nâng cấp DB dev cũ: bảng gamification đã tạo ở phase trước có thể thiếu cột thêm sau (vd. late_night_minutes).

create_all không ALTER → suy DDL từ chính model rồi gọi ensure_columns (idempotent, rẻ khi đủ cột).
"""

import logging

from sqlalchemy.engine import Engine

from src.core.gamification.gamification_table_models import BadgeUnlock, DailyWellbeing, SkinUnlock, WeeklySnapshot, XpEvent
from src.core.sqlite_add_missing_columns_migration import ensure_columns

logger = logging.getLogger("ted")

_MODELS = (XpEvent, DailyWellbeing, WeeklySnapshot, BadgeUnlock, SkinUnlock)


def _ddl_of(column) -> str:
    """Kiểu SQL + NOT NULL DEFAULT khi model có default là hằng số; ngược lại cột cho phép NULL."""
    sql_type = str(column.type)
    default = getattr(column.default, "arg", None) if column.default is not None else None
    if isinstance(default, bool):
        return f"{sql_type} NOT NULL DEFAULT {int(default)}"
    if isinstance(default, (int, float)):
        return f"{sql_type} NOT NULL DEFAULT {default}"
    if isinstance(default, str):
        return f"{sql_type} NOT NULL DEFAULT '{default.replace(chr(39), chr(39) * 2)}'"
    return sql_type


def ensure_gamification_columns(engine: Engine) -> None:
    """Không bao giờ raise: lỗi (vd. DB bị khoá) chỉ log, lần mở sau thử lại."""
    for model in _MODELS:
        table = model.__table__
        columns = {c.name: _ddl_of(c) for c in table.columns if not c.primary_key}
        try:
            ensure_columns(engine, table.name, columns)
        except Exception:  # noqa: BLE001
            logger.exception("Nâng cấp cột bảng %s thất bại, bỏ qua", table.name)
