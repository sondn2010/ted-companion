"""Hợp đồng JSON `ted-email-digest`: email do Hermes đọc từ Gmail, Ted chỉ nhận bản tóm tắt (không token, không thân thư)."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

MAX_EMAILS = 50
_MAX_CHARS = {"sender": 200, "subject": 300, "summary": 500, "reason": 120}


class EmailItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    sender: str = Field(default="", alias="from", max_length=200)   # "from" là từ khoá Python → alias
    subject: str = Field(default="", max_length=300)
    summary: str = Field(default="", max_length=500)
    priority: Literal["important", "low"]
    reason: str = Field(default="", max_length=120)

    @field_validator("sender", "subject", "summary", "reason", mode="before")
    @classmethod
    def _null_to_empty_and_truncate(cls, value: Any, info: ValidationInfo) -> Any:
        if value is None:
            return ""  # skill trả null cho trường không có
        # Chuỗi quá dài thì cắt chứ không loại cả digest
        return value[: _MAX_CHARS[info.field_name]] if isinstance(value, str) else value


class EmailDigestResponse(BaseModel):
    emails: list[EmailItem] = Field(default_factory=list, max_length=MAX_EMAILS)
    total_unread: int = Field(default=0, ge=0)

    @field_validator("emails", mode="before")
    @classmethod
    def _slice_to_max(cls, value: Any) -> Any:
        return value[:MAX_EMAILS] if isinstance(value, list) else value  # quá nhiều thì lấy MAX đầu, không loại cả digest
