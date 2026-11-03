"""Popup nhỏ "Họp/học gì?" khi bắt đầu chế độ Họp: ô chủ đề + 4 chip loại. Enter hoặc "Bỏ qua" đều BẮT ĐẦU ngay.

Chủ đề tuỳ chọn (bỏ trống được). Đóng bằng Esc/✕ = huỷ (không bắt đầu). Phát `chosen(topic, kind)` khi bắt đầu.
Kiểu chip dùng QPushButton:checked có sẵn trong 00-base.qss (không setStyleSheet inline).
"""

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QButtonGroup, QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from src.core.i18n import tr
from src.core.meeting_mode.meeting_session_table_model_and_repository import (
    MEETING_KINDS, TOPIC_MAX_CHARS, normalize_kind)
from src.ui.button_text_escape import btn_text


class MeetingTopicDialog(QDialog):
    chosen = Signal(str, str)   # (topic, kind)

    def __init__(self, topic: str = "", kind: str = "team_meeting", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle(tr("meeting_dialog_title"))
        self.setMinimumWidth(460)
        self.setWindowFlags((self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
                            & ~Qt.WindowType.WindowContextHelpButtonHint)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        root = QVBoxLayout(self)
        root.setSpacing(10)

        self.lbl_prompt = QLabel(tr("meeting_dialog_prompt"))
        self.lbl_prompt.setObjectName("FieldLabel")
        root.addWidget(self.lbl_prompt)

        self.txt_topic = QLineEdit(topic)
        self.txt_topic.setMaxLength(TOPIC_MAX_CHARS)
        self.txt_topic.setPlaceholderText(tr("meeting_dialog_placeholder"))
        self.txt_topic.returnPressed.connect(self._start)
        root.addWidget(self.txt_topic)

        chips = QHBoxLayout()
        chips.setSpacing(6)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self.chips: dict = {}
        for k in MEETING_KINDS:
            btn = QPushButton(btn_text(tr(f"meeting_kind_{k}")))
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setChecked(k == normalize_kind(kind))
            self._group.addButton(btn)
            self.chips[k] = btn
            chips.addWidget(btn)
        root.addLayout(chips)

        buttons = QHBoxLayout()
        buttons.addStretch()
        self.btn_skip = QPushButton(btn_text(tr("meeting_btn_skip")))
        self.btn_skip.clicked.connect(self._skip)
        buttons.addWidget(self.btn_skip)
        self.btn_start = QPushButton(btn_text(tr("meeting_btn_start")))
        self.btn_start.setObjectName("PrimaryBtn")
        self.btn_start.clicked.connect(self._start)
        buttons.addWidget(self.btn_start)
        root.addLayout(buttons)
        self.txt_topic.selectAll()

    def selected_kind(self) -> str:
        return next((k for k, b in self.chips.items() if b.isChecked()), "other")

    def _finish(self, topic: str) -> None:
        self.chosen.emit(topic, self.selected_kind())
        self.accept()

    def _start(self) -> None:
        self._finish(self.txt_topic.text().strip())

    def _skip(self) -> None:
        self._finish("")   # bỏ qua = không chủ đề, nhưng vẫn giữ loại đang chọn

    def focus_input(self) -> None:
        self.activateWindow()
        self.txt_topic.setFocus()
