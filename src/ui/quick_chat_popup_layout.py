"""Dựng giao diện của QuickChatPopup (tách khỏi logic để file popup gọn). Gắn widget vào thuộc tính của popup."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTextEdit, QVBoxLayout

from src.config import settings
from src.core.i18n import tr
from src.ui.quick_chat_mindful_ping_banner import MindfulPingBanner
from src.ui.quick_chat_transcript_store import ChatTranscriptStore
from src.ui.button_text_escape import btn_text


def get_welcome_html() -> str:
    return tr("welcome_html")


WELCOME_HTML = get_welcome_html()


def _build_header(popup, root_layout) -> None:
    """Hàng đầu: tên nhân vật (TitleLabel) · chấm cyan + Chip chế độ · nút làm mới phiên (IconBtn)."""
    header = QHBoxLayout()
    header.setSpacing(6)
    popup.lbl_title = QLabel(settings.character_display_name)
    popup.lbl_title.setObjectName("TitleLabel")
    badge_dot = QLabel()
    badge_dot.setObjectName("ChipDot")
    badge_dot.setFixedSize(8, 8)
    popup.lbl_mode_badge = QLabel(popup._mode_badge_text())
    popup.lbl_mode_badge.setObjectName("Chip")
    popup.lbl_mode_badge.setFont(_uppercase_font(popup.lbl_mode_badge))   # IN HOA bằng font, không đổi nội dung text
    popup.btn_reset = QPushButton("🔄")
    popup.btn_reset.setObjectName("IconBtn")
    popup.btn_reset.setFixedSize(28, 28)
    popup.btn_reset.setToolTip(tr("chat_btn_reset_tooltip"))
    popup.btn_reset.clicked.connect(popup._on_reset_session)
    header.addWidget(popup.lbl_title)
    header.addStretch()
    header.addWidget(badge_dot, alignment=Qt.AlignmentFlag.AlignVCenter)
    header.addWidget(popup.lbl_mode_badge, alignment=Qt.AlignmentFlag.AlignVCenter)
    header.addWidget(popup.btn_reset)
    root_layout.addLayout(header)


def _uppercase_font(widget) -> QFont:
    font = QFont(widget.font())
    font.setCapitalization(QFont.Capitalization.AllUppercase)
    return font


def _build_parking_row(popup, root_layout) -> None:
    """Ô phụ cất ý tưởng gây xao nhãng: input chuẩn + nút 🅿️ Secondary (cùng kiểu Bãi đỗ ở mọi nơi)."""
    park_row = QHBoxLayout()
    popup.input_parking = QLineEdit(popup)
    popup.input_parking.setPlaceholderText(tr("quick_chat_parking_placeholder"))
    popup.input_parking.returnPressed.connect(popup._on_park_idea)
    popup.btn_park = QPushButton(btn_text(tr("quick_chat_btn_park")))
    popup.btn_park.clicked.connect(popup._on_park_idea)
    park_row.addWidget(popup.input_parking, stretch=1)
    park_row.addWidget(popup.btn_park)
    root_layout.addLayout(park_row)


def _build_composer(popup, root_layout) -> None:
    """Composer dock đáy: khung L2 có viền mảnh, chứa ô chat + nút Gửi (PrimaryBtn)."""
    composer = QFrame(popup)
    composer.setObjectName("ChatComposer")
    chat_row = QHBoxLayout(composer)
    chat_row.setContentsMargins(8, 6, 6, 6)
    chat_row.setSpacing(8)
    popup.input_chat = QLineEdit(composer)
    popup.input_chat.setObjectName("ComposerInput")
    popup.input_chat.setPlaceholderText(tr("quick_chat_input_placeholder"))
    popup.input_chat.returnPressed.connect(popup._on_send_chat)
    popup.btn_send = QPushButton(btn_text(tr("quick_chat_btn_send")))
    popup.btn_send.setObjectName("PrimaryBtn")
    popup.btn_send.clicked.connect(popup._on_send_btn_clicked)
    from src.ui.voice_input_mic_button import VoiceInputMicButton
    popup.btn_mic = VoiceInputMicButton(popup.input_chat, composer)   # 🎤 nói thay vì gõ (ẩn khi chưa bật STT)
    chat_row.addWidget(popup.input_chat, stretch=1)
    chat_row.addWidget(popup.btn_mic)
    chat_row.addWidget(popup.btn_send)
    root_layout.addWidget(composer)


def build_quick_chat_ui(popup) -> None:
    """Tạo lbl_title, lbl_mode_badge, ping_banner, chat_view, input_parking, input_chat, btn_send trên `popup`."""
    root_layout = QVBoxLayout(popup)
    root_layout.setContentsMargins(14, 14, 14, 14)
    root_layout.setSpacing(10)
    _build_header(popup, root_layout)

    popup.ping_banner = MindfulPingBanner(popup)
    popup.ping_banner.focused.connect(popup._on_confirm_focused)
    popup.ping_banner.distracted.connect(popup._on_report_distracted)
    root_layout.addWidget(popup.ping_banner)

    popup.chat_view = QTextEdit(popup)
    popup.chat_view.setObjectName("ChatView")
    popup.chat_view.setReadOnly(True)
    welcome_text = get_welcome_html()
    popup.chat_view.setHtml(welcome_text)
    popup.transcripts = ChatTranscriptStore(popup.chat_view, welcome_text)
    root_layout.addWidget(popup.chat_view, stretch=1)

    _build_parking_row(popup, root_layout)
    _build_composer(popup, root_layout)
