"""Bảng gamification (SQLModel): sổ cái XP, chỉ số wellbeing theo ngày, snapshot tuần, huy hiệu + nhân vật đã mở.

Bảng mới hoàn toàn → create_all tự tạo, không cần migration. meta_json chỉ chứa id/bộ đếm (không lưu nội dung).
"""

from datetime import datetime, timezone
from uuid import uuid4

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class XpEvent(SQLModel, table=True):
    """Một dòng XP (có thể âm = thu hồi). dedupe_key UNIQUE để quét lại không cộng đôi."""

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    dedupe_key: str = Field(sa_column_kwargs={"unique": True})
    ts: datetime = Field(default_factory=_utcnow)           # UTC
    local_date: str = Field(index=True)                     # YYYY-MM-DD theo giờ máy lúc ghi
    source_module: str = Field(index=True)                  # focus/work/thcs/caohoc/duhoc/core
    engine: str                                             # focus/work/coach/core
    kind: str = Field(index=True)
    xp: int = 0
    meta_json: str = "{}"


class DailyWellbeing(SQLModel, table=True):
    local_date: str = Field(primary_key=True)
    app_on_minutes: int = 0
    away_minutes: int = 0
    breaks_taken: int = 0
    outings: int = 0
    late_night_minutes: int = 0                             # phút Ted chạy sau 22:00 (và trước 05:00)
    micro_breaks_done: int = 0                              # số hành động sức khỏe nhỏ sau Deep Work đã bấm "Đã làm"
    micro_water_done: int = 0                               # trong đó: uống nước
    micro_move_done: int = 0                                # trong đó: vận động / đứng dậy / tư thế
    updated_at: datetime = Field(default_factory=_utcnow)


class WeeklySnapshot(SQLModel, table=True):
    week_start: str = Field(primary_key=True)               # thứ Hai ISO
    final_level: int = 1
    peak_level: int = 1
    xp_earned: int = 0                                      # tổng XP dương trong tuần
    final_balance: int = 0                                  # legacy (mô hình cũ), không còn ghi
    final_pct: float = 50.0                                 # % tiến độ cuối tuần (mô hình reset 50%)
    active_days: int = 0
    decay_days: int = 0
    stats_json: str = "{}"                                  # 6 chỉ số tích lũy cuối tuần (bản cũ: trung bình)
    badges_json: str = "[]"                                 # id huy hiệu mở trong tuần
    created_at: datetime = Field(default_factory=_utcnow)


class BadgeUnlock(SQLModel, table=True):
    badge_id: str = Field(primary_key=True)
    week_start: str = Field(primary_key=True)
    unlocked_at: datetime = Field(default_factory=_utcnow)


class SkinUnlock(SQLModel, table=True):
    """Nhân vật bundle đã mở khoá — vĩnh viễn (reset level hằng tuần không bao giờ khoá lại)."""

    character_key: str = Field(primary_key=True)            # "pack/character"
    unlocked_at: datetime = Field(default_factory=_utcnow)
