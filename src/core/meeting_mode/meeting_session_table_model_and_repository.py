"""Phiên Họp / Học nhóm / Học với thầy cô (thay thế một phiên Deep Work).

Bảng RIÊNG (không thêm cột vào FocusSession) → mọi quét Deep Work (XP focus, chuỗi tập trung, baseline Gỡ Rối)
tự động KHÔNG đếm họp. Bảng mới hoàn toàn nên create_all tự tạo, DB cũ không cần migration.
`topic` chỉ nằm trên máy (không bao giờ gửi Hermes — báo cáo tăng trưởng chỉ có số đếm).
"""

from datetime import datetime, timezone
from typing import Optional, Tuple
from uuid import uuid4

from sqlalchemy.engine import Engine
from sqlmodel import Field, Session, SQLModel, col, select

KIND_TEAM_MEETING = "team_meeting"   # Họp team
KIND_TEAM_STUDY = "team_study"       # Học nhóm
KIND_TEACHER = "teacher"             # Học với thầy cô
KIND_OTHER = "other"                 # Khác
MEETING_KINDS = (KIND_TEAM_MEETING, KIND_TEAM_STUDY, KIND_TEACHER, KIND_OTHER)
STUDY_MEETING_KINDS = (KIND_TEAM_STUDY, KIND_TEACHER)   # tính vào báo cáo "học tập" của profile coach
TOPIC_MAX_CHARS = 120
MIN_SECONDS_TO_COUNT = 30   # ngắn hơn → coi như bấm nhầm, không lưu (khớp stop_session của Deep Work)


def normalize_kind(kind: Optional[str]) -> str:
    return kind if kind in MEETING_KINDS else KIND_OTHER


def normalize_topic(topic: Optional[str]) -> str:
    return " ".join((topic or "").split())[:TOPIC_MAX_CHARS]


class MeetingSession(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    kind: str = KIND_OTHER
    topic: str = ""
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)
    ended_at: Optional[datetime] = Field(default=None, index=True)
    actual_minutes: int = 0


class MeetingSessionRepository:
    def __init__(self, engine: Engine):
        self._engine = engine
        MeetingSession.__table__.create(engine, checkfirst=True)

    def start(self, kind: str, topic: str) -> str:
        row = MeetingSession(kind=normalize_kind(kind), topic=normalize_topic(topic))
        with Session(self._engine) as s:
            s.add(row)
            s.commit()
            return row.id

    def finish(self, session_id: str, actual_minutes: int) -> None:
        with Session(self._engine) as s:
            row = s.get(MeetingSession, session_id)
            if row is None:
                return
            row.actual_minutes, row.ended_at = max(0, int(actual_minutes)), datetime.now(timezone.utc)
            s.add(row)
            s.commit()

    def discard(self, session_id: str) -> None:
        """Xoá phiên quá ngắn (bấm nhầm)."""
        with Session(self._engine) as s:
            row = s.get(MeetingSession, session_id)
            if row is not None:
                s.delete(row)
                s.commit()

    def last_used(self) -> Tuple[str, str]:
        """(kind, topic) của phiên gần nhất để gợi ý lần sau; chưa có → (team_meeting, "")."""
        with Session(self._engine) as s:
            row = s.exec(select(MeetingSession).order_by(col(MeetingSession.started_at).desc()).limit(1)).first()
        return (row.kind, row.topic) if row else (KIND_TEAM_MEETING, "")
