"""Bảng lưu trữ thống kê hoạt động sử dụng máy tính hằng ngày trong SQLite cục bộ."""

from datetime import date, datetime, timezone
from typing import Dict, Optional
from sqlmodel import Field, SQLModel


class DailyActivityRecord(SQLModel, table=True):
    date: str = Field(default_factory=lambda: date.today().isoformat(), primary_key=True)
    learner: str = Field(default="user", index=True)
    study_seconds: int = Field(default=0)
    distraction_seconds: int = Field(default=0)
    neutral_seconds: int = Field(default=0)
    unsafe_attempts: int = Field(default=0)
    self_corrected_count: int = Field(default=0)
    breach_count: int = Field(default=0)
    top_apps_json: str = Field(default="{}")
    synced_to_hermes: bool = Field(default=False)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
