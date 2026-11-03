"""Hợp đồng JSON: lô câu hỏi, chấm bài viết, phản hồi lưu báo cáo, khối onboarding done."""

import json
import re
from typing import Annotated, Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from src.engines.coach.coach_sync_plan_schemas import lenient_list_of

ONBOARDING_DONE_RE = re.compile(r"<json>\s*(\{.*?\"onboarding\"\s*:\s*\"done\".*?\})\s*</json>", re.S)


def extract_choice_letter(text: str) -> Optional[str]:
    """'B', 'b', 'B. has lived', 'B) x' → 'B'; 'a lot' → None (không phải chữ cái lựa chọn)."""
    stripped = text.strip()
    if len(stripped) == 1 and stripped.isalpha():
        return stripped.upper()
    match = re.match(r"^([A-Za-z])[\.\):]", stripped)
    return match.group(1).upper() if match else None


class GeneratedQuizItem(BaseModel):
    topic: str = ""
    type: Literal["mcq", "short", "step"]
    question: str = Field(min_length=1)
    choices: list[str] = []
    hints: list[str] = []
    answer: str = ""
    explanation: str = ""
    difficulty: int = 2

    @field_validator("difficulty", mode="before")
    @classmethod
    def _clamp_difficulty(cls, value: Any) -> Any:
        return max(1, min(5, value)) if isinstance(value, int) and not isinstance(value, bool) else value

    @model_validator(mode="after")
    def _check_by_type(self):
        if not self.answer.strip():
            raise ValueError("Câu hỏi thiếu đáp án")
        if self.type == "mcq":
            letter = extract_choice_letter(self.answer)
            if len(self.choices) < 2 or letter is None or ord(letter) - ord("A") >= len(self.choices):
                raise ValueError("mcq cần ≥2 choices và answer là chữ cái nằm trong choices")
            self.answer = letter   # chuẩn hoá về chữ cái duy nhất
        return self

    def choices_json(self) -> str:
        return json.dumps(self.choices, ensure_ascii=False)

    def hints_json(self) -> str:
        return json.dumps(self.hints, ensure_ascii=False)


class QuizBatchResponse(BaseModel):
    # Câu lỗi bị bỏ riêng; rỗng hoàn toàn → lỗi validate để request_json retry
    items: Annotated[list[GeneratedQuizItem], lenient_list_of(GeneratedQuizItem)] = Field(min_length=1)


class WritingError(BaseModel):
    original: str = ""
    fixed: str = ""
    why: str = ""


class WritingGradeResult(BaseModel):
    topic: str = ""
    word_count: Optional[int] = None
    scores: dict[str, float] = {}
    overall: float = Field(ge=0, le=10)
    estimated_level: Optional[str] = None
    strengths: list[str] = []
    errors: Annotated[list[WritingError], lenient_list_of(WritingError)] = []
    rewrite_paragraph: Optional[dict[str, str]] = None
    next_focus: list[str] = []


class ProgressReportSavedReply(BaseModel):
    saved: bool
    path: str = ""
    error: str = ""
