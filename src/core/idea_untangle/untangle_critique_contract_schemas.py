"""Hợp đồng JSON `ted-idea-untangle` (phản biện): validator khoan dung — cắt chuỗi/danh sách thay vì từ chối."""

from typing import Any, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

MAX_FLOW_STEPS = 12


def _text(value: Any, limit: int) -> str:
    return "" if value is None else str(value).strip()[:limit]


def _text_list(value: Any, max_items: int, limit: int) -> List[str]:
    if not isinstance(value, list):
        return []
    return [t for t in (_text(v, limit) for v in value) if t][:max_items]


class LogicGap(BaseModel):
    step: Optional[int] = None  # 1-based, trỏ vào flow_steps; ngoài khoảng → None
    issue: str = ""
    question: str = ""

    @field_validator("issue", "question", mode="before")
    @classmethod
    def _cut(cls, value: Any) -> str:
        return _text(value, 300)

    @field_validator("step", mode="before")
    @classmethod
    def _step_int(cls, value: Any) -> Optional[int]:
        if isinstance(value, bool) or value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None


class UntangleCritique(BaseModel):
    summary: str = ""
    flow_steps: List[str] = Field(default_factory=list)
    logic_gaps: List[LogicGap] = Field(default_factory=list)
    assumptions: List[str] = Field(default_factory=list)
    new_angles: List[str] = Field(default_factory=list)
    next_step: str = ""

    @field_validator("summary", mode="before")
    @classmethod
    def _summary(cls, value: Any) -> str:
        return _text(value, 600)

    @field_validator("next_step", mode="before")
    @classmethod
    def _next(cls, value: Any) -> str:
        return _text(value, 160)

    @field_validator("flow_steps", mode="before")
    @classmethod
    def _steps(cls, value: Any) -> List[str]:
        return _text_list(value, MAX_FLOW_STEPS, 90)

    @field_validator("assumptions", mode="before")
    @classmethod
    def _assumptions(cls, value: Any) -> List[str]:
        return _text_list(value, 6, 200)

    @field_validator("new_angles", mode="before")
    @classmethod
    def _angles(cls, value: Any) -> List[str]:
        return _text_list(value, 5, 200)

    @field_validator("logic_gaps", mode="before")
    @classmethod
    def _gaps(cls, value: Any) -> Any:
        return value[:6] if isinstance(value, list) else []

    @model_validator(mode="after")
    def _need_content_and_fix_steps(self) -> "UntangleCritique":
        if not self.flow_steps:
            raise ValueError("flow_steps phải có ít nhất 1 bước")
        for gap in self.logic_gaps:
            if gap.step is not None and not 1 <= gap.step <= len(self.flow_steps):
                gap.step = None
        return self
