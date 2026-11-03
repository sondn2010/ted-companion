"""CRUD phiên Gỡ Rối: tạo, lưu transcript (có trần), hoàn tất (completed_at chỉ ghi lần đầu), tra phiên gần đây."""

import json
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from src.core.idea_untangle.untangle_session_table_model import TRIGGERS, UntangleSession

MAX_TRANSCRIPT_TURNS = 40
MAX_TRANSCRIPT_CHARS = 20000


def cap_transcript(turns: list) -> list:
    """Giữ ≤40 lượt mới nhất và ≤20k ký tự tổng (bỏ lượt cũ nhất trước)."""
    kept = list(turns)[-MAX_TRANSCRIPT_TURNS:]
    while len(kept) > 1 and sum(len(str(t.get("text", ""))) for t in kept) > MAX_TRANSCRIPT_CHARS:
        kept.pop(0)
    return kept


class UntangleSessionRepository:
    def __init__(self, engine: Engine):
        self._engine = engine
        UntangleSession.__table__.create(engine, checkfirst=True)

    def create_session(self, module_id: str, engine: str, task_id: Optional[str], task_title: str,
                       problem_kind: str, trigger: str) -> UntangleSession:
        row = UntangleSession(module_id=module_id, engine=engine, task_id=task_id or None, task_title=task_title,
                              problem_kind=problem_kind, trigger=trigger if trigger in TRIGGERS else "menu")
        with Session(self._engine) as s:
            s.add(row)
            s.commit()
            s.refresh(row)
            return row

    def get(self, session_id: str) -> Optional[UntangleSession]:
        with Session(self._engine) as s:
            return s.get(UntangleSession, session_id)

    def save_transcript(self, session_id: str, turns: list) -> bool:
        with Session(self._engine) as s:
            row = s.get(UntangleSession, session_id)
            if row is None:
                return False
            row.transcript_json = json.dumps(cap_transcript(turns), ensure_ascii=False)
            s.add(row)
            s.commit()
            return True

    def complete_session(self, session_id: str, critique_json: Optional[str] = None) -> Optional[bool]:
        """Trả None nếu không có phiên, True nếu đây là lần hoàn tất ĐẦU (completed_at giữ nguyên các lần sau)."""
        with Session(self._engine) as s:
            row = s.get(UntangleSession, session_id)
            if row is None:
                return None
            first = row.completed_at is None
            if first:
                row.completed_at = datetime.now(timezone.utc)
            if critique_json is not None:
                row.critique_json = critique_json
            s.add(row)
            s.commit()
            return first

    def recent_for_task(self, task_id: str, limit: int = 3) -> List[UntangleSession]:
        with Session(self._engine) as s:
            stmt = (select(UntangleSession).where(UntangleSession.task_id == task_id)
                    .order_by(UntangleSession.started_at.desc()).limit(limit))
            return list(s.exec(stmt).all())
