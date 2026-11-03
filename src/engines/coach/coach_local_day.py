"""Ranh giới "ngày địa phương" (zoneinfo) quy về UTC; mọi truy vấn theo ngày đều đi qua đây."""

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


def day_bounds_utc(day: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    """[đầu ngày, đầu ngày kế) theo giờ địa phương, trả về UTC-aware."""
    start = datetime.combine(day, time.min, tzinfo=tz)
    end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=tz)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def local_date(moment: datetime, tz: ZoneInfo) -> date:
    return moment.astimezone(tz).date()
