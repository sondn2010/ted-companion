"""Lưu/đọc BadgeUnlock (PK badge_id + week_start): day/week mở 1 lần mỗi tuần, lifetime 1 lần mãi mãi."""

from typing import List, Set

from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from src.core.gamification.gamification_table_models import BadgeUnlock


class BadgeUnlockRepository:
    def __init__(self, engine: Engine):
        self._engine = engine
        BadgeUnlock.__table__.create(engine, checkfirst=True)

    def add(self, badge_id: str, week_start: str) -> bool:
        """Idempotent: False nếu (badge, tuần) đã có."""
        with Session(self._engine) as s:
            if s.get(BadgeUnlock, (badge_id, week_start)) is not None:
                return False
            s.add(BadgeUnlock(badge_id=badge_id, week_start=week_start))
            try:
                s.commit()
            except IntegrityError:
                s.rollback()
                return False
            return True

    def ids_for_week(self, week_start: str) -> Set[str]:
        with Session(self._engine) as s:
            return set(s.exec(select(BadgeUnlock.badge_id).where(BadgeUnlock.week_start == week_start)).all())

    def ever_unlocked_ids(self) -> Set[str]:
        with Session(self._engine) as s:
            return set(s.exec(select(BadgeUnlock.badge_id)).all())

    def distinct_unlocked_count(self) -> int:
        """Số badge id khác nhau đã mở (cổng mở skin, phase 06)."""
        return len(self.ever_unlocked_ids())

    def list_all(self) -> List[BadgeUnlock]:
        with Session(self._engine) as s:
            return list(s.exec(select(BadgeUnlock).order_by(BadgeUnlock.week_start, BadgeUnlock.badge_id)).all())
