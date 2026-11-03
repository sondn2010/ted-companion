"""Hợp đồng JSON `ted-eisenhower-classify`: 1 Làm ngay · 2 Lên lịch · 3 Giao việc · 4 Loại bỏ."""

from typing import Any

from pydantic import BaseModel, Field, field_validator


class EisenhowerClassification(BaseModel):
    quadrant: int = Field(ge=1, le=4)
    reason: str = Field(default="", max_length=200)

    @field_validator("reason", mode="before")
    @classmethod
    def _null_to_empty(cls, value: Any) -> Any:
        return "" if value is None else value
