"""Bảng SQLite của engine coach (mọi bảng khoá theo module_id; Hermes là nguồn nội dung, Ted chỉ lưu)."""

import hashlib
import re
import unicodedata
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, Session, SQLModel

from src.engines.coach.utc_aware_datetime_type import UtcDateTime

DATE_PATTERN = r"^\d{4}-\d{2}-\d{2}$"


def _uuid() -> str:
    return str(uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def content_hash(topic: str, question: str) -> str:
    """Hash chống trùng câu hỏi: topic + câu hỏi đã chuẩn hoá (NFC, casefold, gộp khoảng trắng)."""
    norm = re.sub(r"\s+", " ", unicodedata.normalize("NFC", question)).strip().casefold()
    return hashlib.sha256(f"{topic.strip().casefold()}\n{norm}".encode("utf-8")).hexdigest()


def open_session(engine) -> Session:
    # expire_on_commit=False: entity trả ra cho UI/engine vẫn đọc được sau khi session đóng
    return Session(engine, expire_on_commit=False)


class QuizItem(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("module_id", "content_hash"),)

    id: str = Field(default_factory=_uuid, primary_key=True)
    module_id: str = Field(index=True)
    topic: str = Field(default="", index=True)
    type: str                                   # mcq | short | step
    question: str
    choices_json: str = "[]"
    hints_json: str = "[]"
    answer: str = ""
    explanation: str = ""
    difficulty: int = 2
    content_hash: str = Field(index=True)
    created_at: datetime = Field(default_factory=_now, sa_type=UtcDateTime)
    flagged: bool = False
    flag_reason: str = ""
    retired: bool = False


class ReviewState(SQLModel, table=True):
    item_id: str = Field(primary_key=True, foreign_key="quizitem.id")
    box: int = 0
    prev_box: Optional[int] = None              # hộp trước lần trả lời gần nhất, để hoàn tác "Mình đúng mà"
    due_at: datetime = Field(index=True, sa_type=UtcDateTime)
    lapses: int = 0
    last_reviewed_at: Optional[datetime] = Field(default=None, sa_type=UtcDateTime)


class Attempt(SQLModel, table=True):
    id: str = Field(default_factory=_uuid, primary_key=True)
    item_id: str = Field(index=True)
    module_id: str = Field(index=True)
    answered_at: datetime = Field(index=True, sa_type=UtcDateTime)
    user_answer: str = ""
    correct: bool
    response_secs: int = 0


class PlanSnapshot(SQLModel, table=True):
    module_id: str = Field(primary_key=True)
    synced_at: datetime = Field(sa_type=UtcDateTime)
    payload_json: str                           # SyncPlanPayload đã validate


class AgendaDone(SQLModel, table=True):
    module_id: str = Field(primary_key=True)
    agenda_id: str = Field(primary_key=True)    # agenda id hoặc checklist id
    done_at: datetime = Field(sa_type=UtcDateTime)
    reported_in_sync: bool = False


class WritingSubmission(SQLModel, table=True):
    id: str = Field(default_factory=_uuid, primary_key=True)
    module_id: str = Field(index=True)
    agenda_id: str = ""
    topic: str = ""
    prompt: str
    text: str
    result_json: str = ""                       # "" = chưa chấm
    created_at: datetime = Field(default_factory=_now, sa_type=UtcDateTime)


class ProgressReportOutbox(SQLModel, table=True):
    module_id: str = Field(primary_key=True)
    # YYYY-MM-DD chặt chẽ: Hermes ghép ngày vào đường dẫn file (Red Team #4); repo validate lại khi ghi
    date: str = Field(primary_key=True, regex=DATE_PATTERN)
    payload_json: str
    status: str = Field(default="pending", index=True)   # pending | sent | failed_permanently
    sent: bool = False
    attempts: int = 0
    max_attempts: int = 5
    last_error: str = ""
    updated_at: datetime = Field(default_factory=_now, sa_type=UtcDateTime)
