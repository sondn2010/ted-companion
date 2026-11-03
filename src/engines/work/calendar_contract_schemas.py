"""Hợp đồng JSON `ted-calendar-today`: mọi datetime vào hệ thống đều thành aware UTC (naive = giờ local)."""

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

MAX_EVENTS = 500


def to_utc(moment: datetime) -> datetime:
    """Naive → hiểu là giờ local của máy; aware → đổi sang UTC. Không bao giờ trả datetime naive."""
    return moment.astimezone(timezone.utc)


def _is_date_only(value: Any) -> bool:
    return isinstance(value, str) and len(value.strip()) == 10 and value.strip()[4] == "-"


class CalendarEvent(BaseModel):
    id: str = ""
    title: str = ""
    start: datetime
    end: datetime | None = None
    location: str = ""
    meet_url: str = ""
    all_day: bool = False

    @model_validator(mode="before")
    @classmethod
    def _detect_all_day(cls, data: Any) -> Any:
        if isinstance(data, dict) and _is_date_only(data.get("start")):
            data = {**data, "all_day": True}  # ngày thuần YYYY-MM-DD = sự kiện cả ngày
        return data

    @field_validator("id", "title", "location", "meet_url", mode="before")
    @classmethod
    def _null_to_empty(cls, value: Any) -> Any:
        return "" if value is None else value  # skill trả null cho trường không có

    @field_validator("start", "end", mode="after")
    @classmethod
    def _normalize_utc(cls, value: datetime | None) -> datetime | None:
        return None if value is None else to_utc(value)


class CalendarResponse(BaseModel):
    events: list[CalendarEvent] = Field(default_factory=list, max_length=MAX_EVENTS)
