"""Hợp đồng JSON của gợi ý sức khỏe nhỏ sau Deep Work: Hermes skill `ted-health-break` → Ted (tag [TED_HEALTH_BREAK])."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

HealthBreakKind = Literal["move", "water", "eyes", "breath", "posture"]
ACTION_ID_RE = r"^[a-z0-9_-]{1,40}$"   # id đi vào KV/log → slug chặt


class HealthBreakSuggestion(BaseModel):
    """extra=forbid: khoá lạ trong SKILL.md mẫu hoặc phản hồi Hermes → test đỏ / retry 1 lần."""

    model_config = ConfigDict(extra="forbid")

    action_id: str = Field(pattern=ACTION_ID_RE)
    text_vi: str = Field(min_length=1, max_length=240)
    text_en: str = Field(min_length=1, max_length=240)
    duration_sec: int = Field(ge=5, le=300)
    kind: HealthBreakKind

    def text_for(self, language: str) -> str:
        return self.text_en if language == "en" else self.text_vi
