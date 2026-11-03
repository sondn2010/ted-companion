"""Hợp đồng JSON của [TED_SYNC_PLAN] (nguồn chuẩn: skill ted-plan-sync). Parse khoan dung, từng mục lỗi bị bỏ riêng."""

import logging
import re
from datetime import date
from typing import Annotated, Any, Literal, Optional, TypeVar

from pydantic import BaseModel, BeforeValidator, Field, ValidationError, field_validator, model_validator

logger = logging.getLogger("ted")

M = TypeVar("M", bound=BaseModel)

WINDOW_RE = re.compile(r"^\d{2}:\d{2}-\d{2}:\d{2}$")
CLOCK_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def lenient_list_of(model: type[M]) -> BeforeValidator:
    """Mỗi phần tử validate riêng; phần tử lỗi bị bỏ (log) để 1 mục xấu không làm mất cả bản sync."""

    def _validate(value: Any) -> Any:
        if not isinstance(value, list):
            return value
        kept = []
        for entry in value:
            try:
                kept.append(model.model_validate(entry))
            except ValidationError as exc:
                logger.warning("Bỏ mục %s không hợp lệ: %s", model.__name__, str(exc)[:200])
        return kept

    return BeforeValidator(_validate)


def _id_to_str(value: Any) -> Any:
    # Skill mẫu dùng id số (item_id: 123), Ted dùng uuid chuỗi → chấp nhận cả hai, so sánh dạng chuỗi
    return str(value) if isinstance(value, int) and not isinstance(value, bool) else value


CoercedStr = Annotated[str, BeforeValidator(_id_to_str)]


class Policy(BaseModel):
    review_interval_mins: int
    daily_cap: int
    new_per_day: int
    quiet_hours: list[str] = []
    study_windows: list[str] = []
    leitner_days: list[float]
    rationale: str = ""

    @field_validator("leitner_days")
    @classmethod
    def _six_increasing(cls, days: list[float]) -> list[float]:
        if len(days) != 6 or any(b <= a for a, b in zip(days, days[1:])):
            raise ValueError("leitner_days phải gồm đúng 6 số tăng dần")
        return days


class AgendaItem(BaseModel):
    id: CoercedStr
    kind: Literal["quiz", "step", "writing", "chat", "task"]
    title: str
    minutes: Optional[int] = None
    when: Optional[str] = None      # "HH:MM" giờ địa phương hoặc null
    topic: Optional[str] = None
    prompt: Optional[str] = None    # đề writing / câu mở đầu chat

    @field_validator("when")
    @classmethod
    def _valid_clock_or_none(cls, value: Optional[str]) -> Optional[str]:
        return value if value and CLOCK_RE.match(value) else None

    @property
    def effective_prompt(self) -> str:
        return self.prompt or self.title   # skill: thiếu prompt thì dùng title làm đề


class Milestone(BaseModel):
    id: CoercedStr
    title: str
    due_date: date
    remind_before_days: list[int] = [30, 7, 1]


class ChecklistEntry(BaseModel):
    id: CoercedStr
    title: str
    status: Literal["todo", "doing", "done"] = "todo"
    due_date: Optional[date] = None


class Display(BaseModel):
    title: str = ""
    phase: str = ""
    countdown: Optional[dict] = None   # {label, date}


class SrsOverride(BaseModel):
    item_id: CoercedStr
    action: Literal["retire", "reset"]


def _policy_or_none(value: Any) -> Any:
    """Policy sai cấu trúc → None (giữ policy cũ) nhưng phần còn lại của bản sync vẫn được dùng."""
    if value is None or isinstance(value, Policy):
        return value
    try:
        return Policy.model_validate(value)
    except ValidationError as exc:
        logger.warning("Policy không hợp lệ, giữ policy cũ: %s", str(exc)[:200])
        return None


def _display_or_default(value: Any) -> Any:
    try:
        return Display.model_validate(value)
    except ValidationError:
        return Display()


PAYLOAD_KEYS = ("display", "policy", "agenda", "milestones", "checklist", "srs_overrides")


class SyncPlanPayload(BaseModel):
    display: Annotated[Display, BeforeValidator(_display_or_default)] = Field(default_factory=Display)
    policy: Annotated[Optional[Policy], BeforeValidator(_policy_or_none)] = None
    agenda: Annotated[list[AgendaItem], lenient_list_of(AgendaItem)] = []
    milestones: Annotated[list[Milestone], lenient_list_of(Milestone)] = []
    checklist: Annotated[list[ChecklistEntry], lenient_list_of(ChecklistEntry)] = []
    srs_overrides: Annotated[list[SrsOverride], lenient_list_of(SrsOverride)] = []


class SyncPlanResponse(BaseModel):
    """Hoặc {"needs_onboarding": true} hoặc nguyên payload."""

    needs_onboarding: bool = False
    payload: Optional[SyncPlanPayload] = None

    @model_validator(mode="before")
    @classmethod
    def _split(cls, data: Any) -> Any:
        if not isinstance(data, dict) or "needs_onboarding" in data and "payload" in data:
            return data
        if data.get("needs_onboarding") is True:
            return {"needs_onboarding": True, "payload": None}
        if not any(key in data for key in PAYLOAD_KEYS):
            # {} hay JSON lạ sẽ "hợp lệ" với toàn mặc định và xoá agenda → từ chối để request_json retry
            raise ValueError("Phản hồi sync không chứa trường kế hoạch nào")
        return {"needs_onboarding": False, "payload": data}
