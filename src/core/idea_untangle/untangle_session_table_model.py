"""Bảng UntangleSession (Gỡ Rối Ý Tưởng): bảng mới hoàn toàn → create_all tự tạo, không cần migration.

Không có FK tới task (xoá task không bao giờ được lỗi). Thời gian lưu UTC.
"""

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlmodel import Field, SQLModel

TRIGGERS = ("hotkey", "nudge", "menu")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UntangleSession(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    module_id: str = Field(default="")                  # module đang active lúc mở
    engine: str = Field(default="work")                 # work/coach (quyết định bộ problem_kind + audience)
    task_id: Optional[str] = Field(default=None, index=True)
    task_title: str = Field(default="")
    problem_kind: str = Field(default="other")
    trigger: str = Field(default="menu")                # hotkey | nudge | menu
    transcript_json: str = Field(default="[]")          # list[{"role","text"}] đã cắt giới hạn
    critique_json: Optional[str] = Field(default=None)
    started_at: datetime = Field(default_factory=_utcnow)
    completed_at: Optional[datetime] = Field(default=None)
