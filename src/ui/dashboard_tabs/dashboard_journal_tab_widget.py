from PySide6.QtWidgets import QHBoxLayout, QLabel, QMessageBox, QPushButton, QTextEdit, QVBoxLayout, QWidget
from shiboken6 import isValid
from src.bridge.hermes_client_pool import hermes_client_pool
from src.core.background_task_spawner import spawn_background_task
from src.core.i18n import i18n, tr
from src.core.models import db
from src.ui.button_text_escape import btn_text


class DashboardJournalTabWidget(QWidget):
    """Tab 2: Daily Journal (cam kết buổi sáng, phản tư buổi tối, tổng kết AI từ Hermes của module work)."""

    def __init__(self, focus_engine, parent=None):
        super().__init__(parent)
        self.focus_engine = focus_engine
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.lbl_title = QLabel(tr("journal_title"))
        self.lbl_title.setObjectName("TitleLabel")
        layout.addWidget(self.lbl_title)
        layout.addSpacing(8)

        self.lbl_morning = QLabel(tr("journal_morning_label"))
        self.lbl_morning.setObjectName("SectionLabel")
        layout.addWidget(self.lbl_morning)
        self.txt_morning = QTextEdit()
        self.txt_morning.setPlaceholderText(tr("journal_morning_placeholder"))
        layout.addWidget(self.txt_morning)

        self.lbl_evening = QLabel(tr("journal_evening_label"))
        self.lbl_evening.setObjectName("SectionLabel")
        layout.addWidget(self.lbl_evening)
        self.txt_evening = QTextEdit()
        self.txt_evening.setPlaceholderText(tr("journal_evening_placeholder"))
        layout.addWidget(self.txt_evening)

        self.lbl_ai = QLabel(tr("journal_ai_label"))
        self.lbl_ai.setObjectName("SectionLabel")
        layout.addWidget(self.lbl_ai)
        self.txt_ai_summary = QTextEdit()
        self.txt_ai_summary.setPlaceholderText(tr("journal_ai_placeholder"))
        layout.addWidget(self.txt_ai_summary)

        btn_row = QHBoxLayout()
        self.btn_save_journal = QPushButton(btn_text(tr("journal_btn_save")))
        self.btn_save_journal.clicked.connect(self._on_save_journal)
        self.btn_ai_summarize = QPushButton(btn_text(tr("journal_btn_ai")))
        self.btn_ai_summarize.setObjectName("PrimaryBtn")
        self.btn_ai_summarize.clicked.connect(self._on_generate_ai_journal)
        btn_row.addWidget(self.btn_ai_summarize)
        btn_row.addWidget(self.btn_save_journal)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        i18n.language_changed.connect(lambda _: self.retranslate_ui())

    def retranslate_ui(self):
        self.lbl_title.setText(tr("journal_title"))
        self.lbl_morning.setText(tr("journal_morning_label"))
        self.txt_morning.setPlaceholderText(tr("journal_morning_placeholder"))
        self.lbl_evening.setText(tr("journal_evening_label"))
        self.txt_evening.setPlaceholderText(tr("journal_evening_placeholder"))
        self.lbl_ai.setText(tr("journal_ai_label"))
        self.txt_ai_summary.setPlaceholderText(tr("journal_ai_placeholder"))
        self.btn_save_journal.setText(btn_text(tr("journal_btn_save")))
        self.btn_ai_summarize.setText(btn_text(tr("journal_btn_ai")))

    def refresh(self):
        journal = db.get_or_create_journal()
        self.txt_morning.setPlainText(journal.morning_intention or "")
        self.txt_evening.setPlainText(journal.evening_reflection or "")
        self.txt_ai_summary.setPlainText(journal.ai_summary or "")

    def _on_save_journal(self):
        db.update_journal(
            morning_intention=self.txt_morning.toPlainText().strip(),
            evening_reflection=self.txt_evening.toPlainText().strip(),
            ai_summary=self.txt_ai_summary.toPlainText().strip(),
        )
        QMessageBox.information(self, tr("journal_saved_title"), tr("journal_saved_msg"))

    def _on_generate_ai_journal(self):
        self.btn_ai_summarize.setEnabled(False)
        self.txt_ai_summary.clear()
        stats = db.get_today_analytics()
        morning, evening = self.txt_morning.toPlainText(), self.txt_evening.toPlainText()
        prompt = (
            f"Hãy viết bản tổng kết Daily Journal ngắn gọn, ấm áp cho ngày {stats['date']}. "
            f"Số phiên Pomodoro hoàn thành: {stats['completed_sessions']} ({stats['total_focus_minutes']} phút). "
            f"Task đã xong: {stats['completed_tasks']}. Task còn chờ: {stats['pending_tasks']}. "
            f"Cam kết sáng của người dùng: '{morning}'. Phản tư tối: '{evening}'."
        )
        spawn_background_task(self._run_ai_journal_summary(prompt, morning, evening), "journal-ai-summary")

    async def _run_ai_journal_summary(self, prompt: str, morning: str, evening: str):
        # Tab core không bị huỷ khi rebuild module tabs, nhưng vẫn kiểm tra isValid khi cửa sổ đóng lúc app thoát
        def on_token(tok: str):
            if isValid(self):
                self.txt_ai_summary.insertPlainText(tok)

        try:
            summary = await hermes_client_pool.for_module("work").stream_chat(
                user_message=prompt,
                current_context=self.focus_engine.get_context_snapshot(),
                on_mood_change=lambda m: self.focus_engine.set_mood(m),
                on_token=on_token,
                resume_mood=self.focus_engine.current_mood,
            )
            db.update_journal(morning_intention=morning.strip(), evening_reflection=evening.strip(), ai_summary=summary.strip())
        finally:
            if isValid(self):
                self.btn_ai_summarize.setEnabled(True)
