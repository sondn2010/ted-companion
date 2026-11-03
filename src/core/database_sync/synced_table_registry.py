"""Danh sách bảng được đồng bộ giữa các máy (SQLite ⇄ PostgreSQL).

Bảng KHÔNG có trong danh sách = chỉ lưu cục bộ: appstatekv (vị trí cửa sổ, phím tắt), calendareventcache,
dailyactivityrecord + dailywellbeing (số liệu theo từng máy), plansnapshot (cache kế hoạch từ Hermes),
progressreportoutbox (đồng bộ thì cả 2 máy cùng gửi báo cáo).
"""

from sqlmodel import SQLModel

SYNCED_TABLES = (
    "task",
    "focussession",
    "dailyjournal",
    "rock",
    "untanglesession",
    "meetingsession",
    "quizitem",
    "reviewstate",
    "attempt",
    "agendadone",
    "writingsubmission",
    "xpevent",
    "weeklysnapshot",
    "badgeunlock",
    "skinunlock",
)


def primary_key_columns(table: str) -> list[str]:
    """Cột khoá chính theo thứ tự khai báo model (trigger và lúc áp dữ liệu kéo về dùng cùng thứ tự)."""
    import src.core.models  # noqa: F401  (đăng ký mọi bảng vào metadata)

    return [c.name for c in SQLModel.metadata.tables[table].primary_key.columns]
