"""Cột datetime SQLite luôn là UTC-aware: ghi từ datetime aware (chặn naive), đọc ra datetime aware UTC."""

from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlalchemy.types import TypeDecorator


class UtcDateTime(TypeDecorator):
    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            # Red Team #6: datetime naive so sánh với aware gây TypeError → cấm ngay từ lúc ghi
            raise ValueError("Chỉ chấp nhận datetime có tzinfo (aware)")
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        return None if value is None else value.replace(tzinfo=timezone.utc)


def require_aware(value: datetime, name: str = "now") -> datetime:
    if value.tzinfo is None:
        raise ValueError(f"{name} phải là datetime có tzinfo (aware)")
    return value
