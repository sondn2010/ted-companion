"""Rock = vướng mắc tồn đọng của công việc. Lưu UTC; mọi phép tính "tuổi" dùng ngày local."""

from __future__ import annotations

import builtins
from datetime import datetime, timezone
from typing import List, Optional
from uuid import uuid4

from sqlalchemy.engine import Engine
from sqlmodel import Field, Session, SQLModel, select

ROCK_STATUSES = ("open", "resolved", "dropped")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Rock(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    title: str
    detail: str = ""
    status: str = Field(default="open", index=True)  # open|resolved|dropped
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    resolved_note: str = ""


def rock_age_days(rock: Rock, now: Optional[datetime] = None) -> int:
    """Số ngày lịch (theo giờ local) từ lúc tạo đến `now`."""
    now = now or _utcnow()
    created = rock.created_at
    if created.tzinfo is None:  # SQLite trả datetime naive (đã là UTC)
        created = created.replace(tzinfo=timezone.utc)
    return max(0, (now.astimezone().date() - created.astimezone().date()).days)  # naive `now` = giờ local


class RockRepository:
    def __init__(self, engine: Engine):
        self._engine = engine
        Rock.__table__.create(engine, checkfirst=True)

    def add(self, title: str, detail: str = "") -> Rock:
        title = title.strip()
        if not title:
            raise ValueError("Tiêu đề Rock không được để trống")
        with Session(self._engine) as session:
            rock = Rock(title=title, detail=detail.strip())
            session.add(rock)
            session.commit()
            session.refresh(rock)
            return rock

    def set_status(self, rock_id: str, status: str, note: str = "") -> Optional[Rock]:
        if status not in ROCK_STATUSES:
            raise ValueError(f"Trạng thái Rock không hợp lệ: {status}")
        with Session(self._engine) as session:
            rock = session.get(Rock, rock_id)
            if rock is None:
                return None
            rock.status = status
            if status == "resolved":
                rock.resolved_note = note.strip()
            rock.updated_at = _utcnow()
            session.add(rock)
            session.commit()
            session.refresh(rock)
            return rock

    def list(self, include_closed: bool = False) -> List[Rock]:
        with Session(self._engine) as session:
            stmt = select(Rock).order_by(Rock.created_at)  # cũ nhất trước
            if not include_closed:
                stmt = stmt.where(Rock.status == "open")
            return builtins.list(session.exec(stmt).all())

    def get(self, rock_id: str) -> Optional[Rock]:
        with Session(self._engine) as session:
            return session.get(Rock, rock_id)

    def delete(self, rock_id: str) -> bool:
        with Session(self._engine) as session:
            rock = session.get(Rock, rock_id)
            if rock is None:
                return False
            session.delete(rock)
            session.commit()
            return True

    def stale(self, now: datetime, min_days: int) -> List[Rock]:
        """Rock open có tuổi > min_days, cũ nhất trước."""
        return [r for r in self.list() if rock_age_days(r, now) > min_days]
