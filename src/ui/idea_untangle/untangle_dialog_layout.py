"""Dựng widget của UntangleDialog (tách khỏi logic, giống quick_chat_popup_layout). Gắn widget vào thuộc tính của dialog."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTextEdit, QVBoxLayout

from src.core.i18n import tr
from src.ui.button_text_escape import btn_text
from src.ui.quick_chat_transcript_store import ChatTranscriptStore


def _icon_button(text: str, slot) -> QPushButton:
    btn = QPushButton(text)
    btn.setObjectName("IconBtn")
    btn.setFixedSize(28, 28)
    btn.clicked.connect(slot)
    return btn


def _build_header(dlg, root) -> None:
    """Hàng đầu: tiêu đề · chip module · 🔄 phiên mới · ✕."""
    row = QHBoxLayout()
    dlg.lbl_title = QLabel(tr("untangle_dialog_title"))
    dlg.lbl_title.setObjectName("TitleLabel")
    dlg.lbl_module = QLabel("")
    dlg.lbl_module.setObjectName("Chip")
    dlg.btn_new_session = _icon_button("🔄", dlg._on_new_session)
    dlg.btn_new_session.setToolTip(tr("untangle_btn_new_session"))
    row.addWidget(dlg.lbl_title)
    row.addStretch()
    row.addWidget(dlg.lbl_module, alignment=Qt.AlignmentFlag.AlignVCenter)
    row.addWidget(dlg.btn_new_session)
    row.addWidget(_icon_button("✕", dlg.hide))
    root.addLayout(row)
    dlg.lbl_task = QLabel("")
    dlg.lbl_task.setObjectName("MutedLabel")
    root.addWidget(dlg.lbl_task)


def _build_kind_row(dlg, root) -> None:
    """Chip loại vấn đề: nút đổi nhãn/số lượng theo engine ở `dlg._refresh_kinds()`."""
    dlg.kind_row = QHBoxLayout()
    dlg.kind_row.setSpacing(6)
    root.addLayout(dlg.kind_row)
    dlg.kind_buttons = {}


def _build_actions(dlg, root) -> None:
    row = QHBoxLayout()
    dlg.btn_critique = QPushButton(btn_text(tr("untangle_btn_critique")))
    dlg.btn_critique.clicked.connect(dlg._on_critique)
    dlg.btn_save_notes = QPushButton(btn_text(tr("untangle_btn_save_notes")))
    dlg.btn_save_notes.clicked.connect(dlg._on_save_notes)
    dlg.btn_next_task = QPushButton(btn_text(tr("untangle_btn_next_task")))
    dlg.btn_next_task.clicked.connect(dlg._on_create_next_task)
    for btn in (dlg.btn_critique, dlg.btn_save_notes, dlg.btn_next_task):
        row.addWidget(btn)
    row.addStretch()
    root.addLayout(row)


def _build_composer(dlg, root) -> None:
    composer = QFrame(dlg)
    composer.setObjectName("ChatComposer")
    row = QHBoxLayout(composer)
    row.setContentsMargins(8, 6, 6, 6)
    row.setSpacing(8)
    dlg.input_chat = QLineEdit(composer)
    dlg.input_chat.setObjectName("ComposerInput")
    dlg.input_chat.setPlaceholderText(tr("untangle_input_placeholder"))
    dlg.input_chat.returnPressed.connect(dlg._on_send_chat)
    dlg.btn_send = QPushButton(btn_text(tr("quick_chat_btn_send")))
    dlg.btn_send.setObjectName("PrimaryBtn")
    dlg.btn_send.clicked.connect(dlg._on_send_btn_clicked)
    from src.ui.voice_input_mic_button import VoiceInputMicButton
    dlg.btn_mic = VoiceInputMicButton(dlg.input_chat, composer)
    row.addWidget(dlg.input_chat, stretch=1)
    row.addWidget(dlg.btn_mic)
    row.addWidget(dlg.btn_send)
    root.addWidget(composer)


def build_untangle_ui(dlg) -> None:
    """Tạo lbl_title/lbl_module/lbl_task/kind_row/chat_view/transcripts/btn_*/input_chat trên `dlg`."""
    root = QVBoxLayout(dlg)
    root.setContentsMargins(14, 14, 14, 14)
    root.setSpacing(10)
    _build_header(dlg, root)
    _build_kind_row(dlg, root)
    dlg.chat_view = QTextEdit(dlg)
    dlg.chat_view.setObjectName("ChatView")
    dlg.chat_view.setReadOnly(True)
    dlg.transcripts = ChatTranscriptStore(dlg.chat_view, "")
    root.addWidget(dlg.chat_view, stretch=1)
    _build_actions(dlg, root)
    _build_composer(dlg, root)
