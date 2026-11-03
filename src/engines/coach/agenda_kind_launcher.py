"""Mở trình hiển thị theo `kind` của agenda. Kind mới = thêm 1 hàm vào KIND_RENDERERS, không đụng module cụ thể."""

import logging
from typing import Callable, Optional, Sequence

from PySide6.QtWidgets import QDialog

from src.core.background_task_spawner import spawn_background_task
from src.engines.coach.coach_data_models import QuizItem
from src.engines.coach.coach_module_services import CoachModuleServices
from src.engines.coach.coach_quiz_session_service import CoachQuizSessionService
from src.engines.coach.coach_review_session_builder import build_session_items, quiz_limit_for_agenda
from src.engines.coach.coach_sync_plan_schemas import AgendaItem
from src.engines.coach.quiz_batch_refill_service import refill_if_needed
from src.engines.coach.writing_submission_service import WritingSubmissionService
from src.ui.quiz.quiz_popup_dialog import QuizPopupDialog
from src.ui.quiz.step_problem_dialog import StepProblemDialog
from src.ui.quiz.writing_result_dialog import WritingResultDialog
from src.ui.quiz.writing_submit_dialog import WritingSubmitDialog

logger = logging.getLogger("ted")
PREPARING_TEXT = "Ted đang soạn câu hỏi…"
NO_ITEMS_TEXT = "Chưa soạn được câu hỏi nào, thử lại sau nhé."

_open_dialogs: set = set()   # giữ tham chiếu mạnh tới dialog không có parent cho đến khi đóng


def show_dialog(dialog: QDialog) -> None:
    _open_dialogs.add(dialog)
    dialog.finished.connect(lambda _=0, d=dialog: _open_dialogs.discard(d))
    dialog.show()
    dialog.raise_()


class AgendaKindLauncher:
    def __init__(self, services: CoachModuleServices):
        self.s = services
        self.quiz_service = CoachQuizSessionService(services)
        self.writing_service = WritingSubmissionService(services)
        self._regrading: set[str] = set()   # bài đang chấm lại: bấm "Chấm lại" lần nữa bị bỏ qua

    # ---- tiện ích ----
    def say(self, text: str, mood: str = "CHEER", timeout_ms: int = 8000) -> None:
        if self.s.ctx.bubble is not None:
            self.s.ctx.bubble.show_message(text, mood=mood, timeout_ms=timeout_ms)

    def _set_mood(self, mood: str) -> None:
        self.s.ctx.focus_engine.set_mood(mood)

    def _spawn(self, coro, name: str) -> bool:
        try:
            spawn_background_task(coro, name)
            return True
        except RuntimeError:   # chưa có event loop (vd. test thuần Qt)
            coro.close()
            return False

    async def _refill(self, topic: Optional[str], types: Optional[Sequence[str]] = None, count: int = 10) -> None:
        client = self.s.client()
        if client is not None:
            await refill_if_needed(self.s.manifest, self.s.items, client, self.s.now(), topic, types, count)

    def refill_in_background(self) -> None:
        """Mỗi tick của scheduler: bổ sung kho câu hỏi (không chặn UI)."""
        self._spawn(self._refill(None), "coach-refill-tick")

    # ---- phiên quiz (agenda quiz, scheduler, "Ôn ngay") ----
    def start_quiz_session(
        self, limit: int, topic: Optional[str] = None, agenda_id: Optional[str] = None, respect_new_cap: bool = False,
    ) -> None:
        items = build_session_items(self.s, limit, topic, respect_new_cap)
        if items:
            self.open_quiz_dialog(items, agenda_id)
            self._spawn(self._refill(topic), "coach-refill-bg")   # bổ sung kho cho lần sau
            return
        self.say(PREPARING_TEXT, "GENTLE_NUDGE")
        self._spawn(self._prepare_then_open(limit, topic, agenda_id, respect_new_cap), "coach-quiz-prepare")

    async def _prepare_then_open(self, limit, topic, agenda_id, respect_new_cap) -> None:
        await self._refill(topic)
        items = build_session_items(self.s, limit, topic, respect_new_cap)
        if items:
            self.open_quiz_dialog(items, agenda_id)
        else:
            self.say(NO_ITEMS_TEXT, "GENTLE_NUDGE")

    def open_quiz_dialog(self, items: Sequence[QuizItem], agenda_id: Optional[str] = None) -> QuizPopupDialog:
        on_completed = (lambda _answered, _correct: self.s.mark_done(agenda_id)) if agenda_id else (lambda *_: None)
        dialog = QuizPopupDialog(items, self.quiz_service, self._set_mood, on_completed)
        dialog.finished.connect(lambda _=0: self.s.on_changed())
        show_dialog(dialog)
        return dialog

    # ---- step ----
    def open_step(self, agenda: AgendaItem) -> None:
        item = self.s.items.first_unseen(self.s.module_id, agenda.topic, ["step"])
        if item is not None:
            self._open_step_dialog(item, agenda.id)
            return
        self.say(PREPARING_TEXT, "GENTLE_NUDGE")
        self._spawn(self._prepare_step(agenda), "coach-step-prepare")

    async def _prepare_step(self, agenda: AgendaItem) -> None:
        await self._refill(agenda.topic, ["step"], 1)
        item = self.s.items.first_unseen(self.s.module_id, agenda.topic, ["step"])
        if item is None:
            self.say(NO_ITEMS_TEXT, "GENTLE_NUDGE")
        else:
            self._open_step_dialog(item, agenda.id)

    def _open_step_dialog(self, item: QuizItem, agenda_id: str) -> None:
        dialog = StepProblemDialog(
            item, self.quiz_service, on_assessed=lambda _passed: self.s.mark_done(agenda_id), set_mood=self._set_mood)
        show_dialog(dialog)

    # ---- writing / chat / task ----
    def open_writing(self, agenda: AgendaItem) -> None:
        dialog = WritingSubmitDialog(
            self.writing_service, agenda.effective_prompt, agenda.id, agenda.topic or "",
            on_graded=lambda: self.s.mark_done(agenda.id), show_dialog=show_dialog)
        show_dialog(dialog)

    def regrade_writing(self, submission_id: str) -> None:
        """Nút Chấm lại cho bài đã lưu nhưng chưa chấm (lịch sử bài viết)."""
        if submission_id in self._regrading:
            self.say("Ted đang chấm bài này rồi, đợi chút nhé.", "GENTLE_NUDGE", 4000)
            return
        self._regrading.add(submission_id)
        self.say("Ted đang chấm lại bài…", "GENTLE_NUDGE", 4000)
        if not self._spawn(self._regrade_writing(submission_id), "coach-writing-regrade"):
            self._regrading.discard(submission_id)

    async def _regrade_writing(self, submission_id: str) -> None:
        try:
            await self._regrade_writing_inner(submission_id)
        finally:
            self._regrading.discard(submission_id)

    async def _regrade_writing_inner(self, submission_id: str) -> None:
        outcome = await self.writing_service.regrade(submission_id)
        if outcome.result is None:
            self.say("Chưa chấm được, thử lại sau nhé.", "GENTLE_NUDGE")
            return
        row = self.s.plans.get_writing_submission(submission_id)
        if row is not None and row.agenda_id:
            self.s.mark_done(row.agenda_id)
        self.s.on_changed()
        show_dialog(WritingResultDialog(outcome.result))

    def open_chat(self, agenda: AgendaItem) -> None:
        opened = self.s.ctx.quick_chat.open_for(
            self.s.module_id, prefill=agenda.prompt or f"Mình bắt đầu: {agenda.title}", auto_send=True)
        if opened:   # False = bị từ chối (đang có luồng trả lời) → chưa gửi gì thì chưa tính là xong
            self.s.mark_done(agenda.id)
        else:
            self.say("Ted đang bận trả lời, bấm lại sau nhé.", "GENTLE_NUDGE", 4000)

    def complete_task(self, agenda: AgendaItem) -> None:
        self.s.mark_done(agenda.id)

    def launch(self, agenda: AgendaItem) -> None:
        renderer = KIND_RENDERERS.get(agenda.kind)
        if renderer is None:
            logger.warning("Chưa có renderer cho kind '%s'", agenda.kind)
            return
        try:
            renderer(self, agenda)
        except Exception:
            logger.exception("Mở agenda %s (%s) lỗi", agenda.id, agenda.kind)


KIND_RENDERERS: dict[str, Callable[[AgendaKindLauncher, AgendaItem], None]] = {
    "quiz": lambda l, a: l.start_quiz_session(quiz_limit_for_agenda(a.minutes), a.topic, a.id),
    "step": AgendaKindLauncher.open_step,
    "writing": AgendaKindLauncher.open_writing,
    "chat": AgendaKindLauncher.open_chat,
    "task": AgendaKindLauncher.complete_task,
}
