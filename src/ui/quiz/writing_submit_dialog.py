"""Soạn bài viết: đề, đếm từ trực tiếp, đồng hồ; nộp → lưu trước rồi chấm (90s). Lỗi → giữ bài, nút "Chấm lại"."""

import logging
from html import escape
import time
from typing import Callable, Optional

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QDialog, QLabel, QPlainTextEdit, QPushButton, QHBoxLayout, QVBoxLayout, QWidget
from shiboken6 import isValid

from src.core.background_task_spawner import spawn_background_task
from src.engines.coach.writing_submission_service import WritingOutcome, WritingSubmissionService
from src.ui.quiz.writing_result_dialog import WritingResultDialog

logger = logging.getLogger("ted")


def count_words(text: str) -> int:
    return len(text.split())


class WritingSubmitDialog(QDialog):
    def __init__(
        self, service: WritingSubmissionService, prompt: str, agenda_id: str = "", topic: str = "",
        on_graded: Callable[[], None] = lambda: None,
        show_dialog: Callable[[QDialog], None] = lambda dlg: dlg.show(), parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._service, self._prompt, self._agenda_id, self._topic = service, prompt, agenda_id, topic
        self._on_graded, self._show_dialog = on_graded, show_dialog
        self._submission_id: Optional[str] = None
        self._started = time.monotonic()
        self.setWindowTitle("✍️ Bài viết")
        self.resize(560, 460)
        layout = QVBoxLayout(self)
        prompt_label = QLabel(f"<b>Đề:</b> {escape(prompt)}")
        prompt_label.setObjectName("SectionLabel")
        prompt_label.setWordWrap(True)
        layout.addWidget(prompt_label)
        self.editor = QPlainTextEdit()
        self.editor.textChanged.connect(self._update_counter)
        layout.addWidget(self.editor, stretch=1)
        self.status_label = QLabel()
        self.status_label.setObjectName("HintLabel")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        footer = QHBoxLayout()
        self.counter_label = QLabel()
        self.counter_label.setObjectName("MutedLabel")
        footer.addWidget(self.counter_label)
        footer.addStretch(1)
        self.btn_submit = QPushButton("Nộp bài")
        self.btn_submit.setObjectName("PrimaryBtn")
        self.btn_submit.clicked.connect(self._submit)
        footer.addWidget(self.btn_submit)
        layout.addLayout(footer)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_counter)
        self._timer.start(1000)
        self._update_counter()

    def minutes_spent(self) -> int:
        return max(0, round((time.monotonic() - self._started) / 60))

    def _update_counter(self) -> None:
        secs = int(time.monotonic() - self._started)
        self.counter_label.setText(f"{count_words(self.editor.toPlainText())} từ · ⏱ {secs // 60:02d}:{secs % 60:02d}")

    def _submit(self) -> None:
        text = self.editor.toPlainText().strip()
        if not text and self._submission_id is None:
            return
        self.btn_submit.setEnabled(False)
        self.editor.setReadOnly(True)
        self.status_label.setText("Ted đang chấm bài…")
        try:
            spawn_background_task(self._run(text), "coach-writing-submit")
        except RuntimeError:   # chưa có event loop (hiếm): bài đã/sẽ được lưu ở lần gọi sau
            self._fail_ui()

    async def _run(self, text: str) -> None:
        try:
            if self._submission_id is None:
                outcome = await self._service.submit(
                    self._prompt, text, self.minutes_spent(), self._agenda_id, self._topic)
            else:
                outcome = await self._service.regrade(self._submission_id, self.minutes_spent())
        except Exception:
            logger.exception("Nộp bài viết lỗi")
            outcome = None
        if outcome is not None:
            self._submission_id = outcome.submission_id
            if outcome.result is not None:
                self._on_graded()   # không đụng widget → an toàn dù dialog đã bị huỷ (Red Team #3)
        if isValid(self):
            self._show_outcome(outcome)

    def _show_outcome(self, outcome: Optional[WritingOutcome]) -> None:
        if outcome is not None and outcome.result is not None:
            self._timer.stop()
            self._show_dialog(WritingResultDialog(outcome.result))
            self.accept()
        else:
            self._fail_ui()

    def _fail_ui(self) -> None:
        self.status_label.setObjectName("ErrorLabel")   # báo lỗi bằng màu error của design system
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
        self.status_label.setText("Chưa chấm được (mất kết nối?). Bài của bạn đã được lưu — thử lại nhé.")
        self.btn_submit.setText("Chấm lại")
        self.btn_submit.setEnabled(True)
