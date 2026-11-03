"""Cache lịch trong SQLite: lưu UTC, đọc ra luôn là datetime aware UTC (TypeDecorator) → không bao giờ so sánh naive/aware."""

import hashlib
from datetime import datetime, time, timedelta, timezone
from typing import Optional

from sqlalchemy import Column, DateTime
from sqlalchemy.engine import Engine
from sqlalchemy.types import TypeDecorator
from sqlmodel import Field, Session, SQLModel, col, delete, select

from src.engines.work.calendar_contract_schemas import CalendarEvent, to_utc

DEFAULT_DURATION_MINS = 60  # sự kiện không có giờ kết thúc


class UtcDateTime(TypeDecorator):
    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return None if value is None else to_utc(value).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        return None if value is None else value.replace(tzinfo=timezone.utc)


class CalendarEventCache(SQLModel, table=True):
    key: str = Field(primary_key=True)  # f"{id or sha1(title+start)}|{start_iso}" (lịch lặp chung id)
    event_id: str = ""
    title: str = ""
    start_at: datetime = Field(sa_column=Column(UtcDateTime, index=True, nullable=False))
    end_at: Optional[datetime] = Field(default=None, sa_column=Column(UtcDateTime, nullable=True))
    location: str = ""
    meet_url: str = ""
    all_day: bool = False
    fetched_at: datetime = Field(sa_column=Column(UtcDateTime, nullable=False))


def event_key(event: CalendarEvent) -> str:
    start_iso = event.start.isoformat()
    ident = event.id or hashlib.sha1(f"{event.title}{start_iso}".encode("utf-8")).hexdigest()
    return f"{ident}|{start_iso}"


def event_end(event: CalendarEventCache) -> datetime:
    return event.end_at or event.start_at + timedelta(minutes=DEFAULT_DURATION_MINS)


def local_day_bounds_utc(now_local: Optional[datetime] = None) -> tuple[datetime, datetime]:
    """[00:00 local hôm nay, 00:00 local hôm sau) → UTC (naive đầu vào được hiểu là giờ local)."""
    local = (now_local or datetime.now()).astimezone()
    start = datetime.combine(local.date(), time.min, tzinfo=local.tzinfo)
    end = datetime.combine(local.date() + timedelta(days=1), time.min, tzinfo=local.tzinfo)
    return to_utc(start), to_utc(end)


_tables_ready_for: set[int] = set()   # id(engine) đã tạo bảng: repo được dựng mỗi tick → chỉ tạo 1 lần/engine


class CalendarEventRepository:
    def __init__(self, engine: Engine):
        self._engine = engine
        if id(engine) not in _tables_ready_for:
            CalendarEventCache.__table__.create(engine, checkfirst=True)
            _tables_ready_for.add(id(engine))

    def prune(self, keep_from_utc: datetime, keep_until_utc: datetime) -> int:
        """Xoá hàng có start_at < keep_from (đã qua) hoặc >= keep_until (ngoài cửa sổ hiện hành, vd. đã giảm số ngày)."""
        with Session(self._engine) as session:
            result = session.exec(delete(CalendarEventCache).where(
                (col(CalendarEventCache.start_at) < keep_from_utc) | (col(CalendarEventCache.start_at) >= keep_until_utc)))
            session.commit()
            return result.rowcount or 0

    def has_upcoming_timed(self, now_utc: datetime) -> bool:
        """Còn họp có giờ chưa kết thúc trong cache? (cổng chống xoá cache khi Hermes trả danh sách rỗng đáng ngờ)"""
        now_utc = to_utc(now_utc)
        rows = self.between(now_utc - timedelta(hours=24), now_utc + timedelta(days=60))
        return any(not e.all_day and event_end(e) > now_utc for e in rows)

    def replace_window(self, start_utc: datetime, end_utc: datetime, events: list[CalendarEvent],
                       fetched_at: datetime) -> int:
        """Một transaction: xoá hàng cache có start_at trong [start, end) rồi chèn lại; trả số hàng đã lưu."""
        rows = {}
        for ev in events:
            if not (start_utc <= ev.start < end_utc):
                continue  # ngoài cửa sổ đã yêu cầu → bỏ, không để dữ liệu rác sống mãi
            rows[event_key(ev)] = CalendarEventCache(
                key=event_key(ev), event_id=ev.id, title=ev.title, start_at=ev.start, end_at=ev.end,
                location=ev.location, meet_url=ev.meet_url, all_day=ev.all_day, fetched_at=fetched_at)
        with Session(self._engine) as session:
            session.exec(delete(CalendarEventCache).where(
                col(CalendarEventCache.start_at) >= start_utc, col(CalendarEventCache.start_at) < end_utc))
            session.add_all(rows.values())
            session.commit()  # lỗi giữa chừng → rollback, cache cũ còn nguyên
        return len(rows)

    def between(self, start_utc: datetime, end_utc: datetime) -> list[CalendarEventCache]:
        """Sự kiện có start_at trong [start, end), sớm nhất trước."""
        with Session(self._engine) as session:
            stmt = (select(CalendarEventCache)
                    .where(col(CalendarEventCache.start_at) >= start_utc, col(CalendarEventCache.start_at) < end_utc)
                    .order_by(col(CalendarEventCache.start_at)))
            return list(session.exec(stmt).all())

    def today(self, now_local: Optional[datetime] = None) -> list[CalendarEventCache]:
        """Hôm nay theo giờ local: 00:00 local → 00:00 hôm sau (đổi sang UTC nên họp sáng UTC+7 không bị rớt)."""
        start_utc, end_utc = local_day_bounds_utc(now_local)
        return self.between(start_utc, end_utc)

    def overlapping(self, now_utc: datetime, margin_mins: int = 0) -> list[CalendarEventCache]:
        """Họp (KHÔNG cả ngày) đang diễn ra ± margin: cổng cho scheduler của coach. Sự kiện cả ngày không chặn."""
        now_utc = to_utc(now_utc)
        margin = timedelta(minutes=margin_mins)
        window = self.between(now_utc - timedelta(hours=24), now_utc + margin + timedelta(seconds=1))
        return [e for e in window if not e.all_day and event_end(e) + margin >= now_utc]

    def busy_slots(self, now_utc: Optional[datetime] = None, days_ahead: int = 7) -> list[tuple[datetime, datetime]]:
        """Khoảng bận (start, end) aware UTC trong `days_ahead` ngày tới, bỏ sự kiện cả ngày — cho `[TED_SYNC_PLAN]`."""
        now_utc = to_utc(now_utc or datetime.now(timezone.utc))
        events = self.between(now_utc - timedelta(hours=24), now_utc + timedelta(days=days_ahead))
        return [(e.start_at, event_end(e)) for e in events if not e.all_day and event_end(e) > now_utc]
