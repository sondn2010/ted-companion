"""Singleton dịch vụ Gỡ Rối: giữ repo trên DB chính + phát tín hiệu hoàn tất (chỉ lần đầu) cho Hub XP.

Hub contract: source `untangle`, dedupe_key = f"untangle:{session_id}", thời gian = completed_at.
"""

import logging
from typing import Optional

from PySide6.QtCore import QObject, Signal

from src.core.idea_untangle.untangle_session_repository import UntangleSessionRepository

logger = logging.getLogger("ted")


class IdeaUntangleService(QObject):
    session_completed = Signal(str, str, str)  # (session_id, task_id hoặc "", problem_kind) — chỉ lần hoàn tất đầu

    def __init__(self, repository: Optional[UntangleSessionRepository] = None, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._repo = repository

    @property
    def repo(self) -> UntangleSessionRepository:
        if self._repo is None:  # lazy: tránh mở DB chính lúc import
            from src.core.models import db
            self._repo = UntangleSessionRepository(db.engine)
        return self._repo

    def complete(self, session_id: str, critique_json: Optional[str] = None) -> bool:
        """Đánh dấu hoàn tất; phát tín hiệu 1 lần. Trả True nếu là lần đầu."""
        first = self.repo.complete_session(session_id, critique_json)
        if not first:
            return False
        row = self.repo.get(session_id)
        self.session_completed.emit(session_id, (row.task_id or "") if row else "", row.problem_kind if row else "other")
        return True


idea_untangle_service = IdeaUntangleService()
