"""Nối tín hiệu FocusEngine → engine work: task_added (phân loại Eisenhower), session_started (nhắc việc quan trọng kế tiếp)."""

import logging

from src.core.models import DatabaseManager
from src.engines.work.deep_work_next_task_announcer import announce, compose_next_task_message, next_task_links
from src.engines.work.meeting_overlap_gate import is_in_meeting
from src.engines.work.parked_idea_eisenhower_classifier import ParkedIdeaClassifier

logger = logging.getLogger("ted")
NEXT_TASKS_LIMIT = 3


class WorkFocusEngineSignalWiring:
    def __init__(self, manifest, ctx, db_engine, calendar_repo):
        self._ctx = ctx
        self._calendar_repo = calendar_repo
        self._tasks = DatabaseManager.for_engine(db_engine)
        self.classifier = ParkedIdeaClassifier(manifest, ctx, db_engine)
        self._connected = False

    def connect(self) -> None:
        focus = self._ctx.focus_engine
        if focus is None or self._connected:  # chống connect 2 lần (start gọi lặp)
            return
        focus.task_added.connect(self.classifier.on_task_added)
        focus.session_started.connect(self.on_session_started)
        self._connected = True

    def disconnect(self) -> None:
        focus = self._ctx.focus_engine
        if focus is None or not self._connected:
            return
        pairs = ((focus.task_added, self.classifier.on_task_added), (focus.session_started, self.on_session_started))
        for signal, slot in pairs:
            try:
                signal.disconnect(slot)
            except (RuntimeError, TypeError):  # đã ngắt / object Qt đã huỷ
                pass
        self._connected = False

    def on_session_started(self, task_id: str, title: str) -> None:
        """Đang họp hoặc không còn việc Q1/Q2 → chỉ bubble (không đọc to). Lỗi DB không được làm hỏng phiên focus."""
        try:
            ranked = self._tasks.next_important_tasks(NEXT_TASKS_LIMIT)
            message = compose_next_task_message(task_id or None, title, ranked)
            announce(
                self._ctx, message, speak=bool(ranked) and not is_in_meeting(self._calendar_repo),
                task_links=next_task_links(task_id or None, title, ranked),
            )
        except Exception:
            logger.exception("Không nhắc được việc quan trọng kế tiếp")
