"""CRUD bảng DailyWellbeing: phút Ted chạy, phút vắng mặt, số lần nghỉ, nhật ký đi chơi (thủ công)."""

from datetime import date, datetime, timezone
from typing import Dict

from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from src.core.gamification.gamification_table_models import DailyWellbeing

MAX_OUTINGS_PER_DAY = 3  # chặn bấm spam nút "Đi chơi"


class WellbeingDailyRepository:
    def __init__(self, engine: Engine):
        self._engine = engine
        DailyWellbeing.__table__.create(engine, checkfirst=True)

    def _bump(self, day: date, field: str, amount: int) -> None:
        """Cộng dồn `amount` vào cột `field` của ngày `day` (tạo hàng nếu chưa có)."""
        if amount <= 0:
            return
        with Session(self._engine) as s:
            row = s.get(DailyWellbeing, day.isoformat()) or DailyWellbeing(local_date=day.isoformat())
            setattr(row, field, getattr(row, field) + amount)
            row.updated_at = datetime.now(timezone.utc)
            s.add(row)
            s.commit()

    def add_minutes(self, day: date, minutes: int = 1) -> None:
        self._bump(day, "app_on_minutes", minutes)

    def add_away(self, day: date, minutes: int) -> None:
        self._bump(day, "away_minutes", minutes)

    def add_late_night(self, day: date, minutes: int = 1) -> None:
        self._bump(day, "late_night_minutes", minutes)

    def increment_break(self, day: date) -> None:
        self._bump(day, "breaks_taken", 1)

    def log_micro_break(self, day: date, kind: str) -> None:
        """+1 hành động sức khỏe nhỏ đã làm (không XP). Đếm riêng nước / vận động (move, posture) để cá nhân hoá."""
        self._bump(day, "micro_breaks_done", 1)
        if kind == "water":
            self._bump(day, "micro_water_done", 1)
        elif kind in ("move", "posture"):
            self._bump(day, "micro_move_done", 1)

    def log_outing(self, day: date) -> bool:
        """+1 lần đi chơi (không XP). Trả False khi ngày đó đã đạt trần."""
        if self.get(day).outings >= MAX_OUTINGS_PER_DAY:
            return False
        self._bump(day, "outings", 1)
        return True

    def get(self, day: date) -> DailyWellbeing:
        """Hàng của ngày; chưa có → bản ghi toàn 0 (không lưu)."""
        with Session(self._engine) as s:
            return s.get(DailyWellbeing, day.isoformat()) or DailyWellbeing(local_date=day.isoformat())

    def range(self, start: date, end: date) -> Dict[date, DailyWellbeing]:
        with Session(self._engine) as s:
            rows = s.exec(select(DailyWellbeing).where(
                DailyWellbeing.local_date >= start.isoformat(), DailyWellbeing.local_date <= end.isoformat())).all()
        return {date.fromisoformat(r.local_date): r for r in rows}

    def export_range(self, start: date, end: date) -> list:
        """Dữ liệu wellbeing thô (dict thuần, tách biệt XP/stat) để sau này gửi riêng cho Hermes health profile."""
        fields = ("app_on_minutes", "away_minutes", "breaks_taken", "outings", "late_night_minutes",
                  "micro_breaks_done", "micro_water_done", "micro_move_done")
        return [{"local_date": d.isoformat(), **{f: getattr(r, f) for f in fields}}
                for d, r in sorted(self.range(start, end).items())]
