"""Hợp đồng JSON của báo cáo tăng trưởng (Ted → Hermes). Reply dùng lại ProgressReportSavedReply của coach."""

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.engines.coach.coach_quiz_writing_report_schemas import ProgressReportSavedReply

DATE_RE = r"^\d{4}-\d{2}-\d{2}$"
LEARNER_RE = r"^[a-z0-9_-]+$"   # learner đi vào đường dẫn file trên Hermes → slug chặt (chống path traversal)

__all__ = ["GrowthReport", "ProgressReportSavedReply"]


class GrowthReport(BaseModel):
    """extra=forbid: khóa lạ trong SKILL.md mẫu hoặc builder → test đỏ ngay."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["daily", "weekly"]
    report_kind: Literal["learning", "general"]
    learner: str = Field(pattern=LEARNER_RE)
    date: Optional[str] = Field(default=None, pattern=DATE_RE)
    week_start: Optional[str] = Field(default=None, pattern=DATE_RE)
    level: Optional[int] = None
    pct: Optional[float] = None
    xp_day: Optional[int] = None
    decayed: Optional[bool] = None
    final_level: Optional[int] = None
    final_pct: Optional[float] = None
    peak_level: Optional[int] = None
    xp_earned: Optional[int] = None
    coach_xp: Optional[int] = None
    active_days: Optional[int] = None
    decay_days: Optional[int] = None
    stats: Optional[Dict[str, int]] = None
    stats_end: Optional[Dict[str, int]] = None
    counts: Optional[Dict[str, int]] = None
    badges_new: Optional[List[str]] = None
    badges: Optional[List[str]] = None
    badges_total: int = 0
    wellbeing: Optional[Dict[str, int]] = None   # khối tách riêng, chỉ có ở report_kind=general

    @model_validator(mode="after")
    def _check_shape(self) -> "GrowthReport":
        if self.kind == "daily" and not self.date:
            raise ValueError("daily cần date")
        if self.kind == "weekly" and not self.week_start:
            raise ValueError("weekly cần week_start")
        if self.report_kind == "learning" and self.wellbeing is not None:
            raise ValueError("báo cáo learning không được chứa wellbeing")
        return self
