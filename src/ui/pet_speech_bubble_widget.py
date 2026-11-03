import asyncio
from html import escape
import logging
from typing import Callable, Optional, Sequence

from PySide6.QtCore import QPoint, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QFont, QPainter, QPainterPath, QPen, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from shiboken6 import isValid

from src.bridge.chat_json_tail_detector import ChatJsonTailDetector
from src.config import settings
from src.core.background_task_spawner import spawn_background_task
from src.core.chat_session_manager import chat_session_manager
from src.core.i18n import i18n, tr
from src.core.tts_service import tts_service
from src.ui.bubble_task_link_html import linkify_task_titles, task_id_from_href
from src.ui.button_text_escape import btn_text
from src.ui.pet_theme_color_helpers import qcolor
from src.ui.quick_chat_message_html import assistant_open_html, notice_html, user_message_html
from src.ui.rich_content.rich_reply_html_renderer import reply_body_html
from src.ui.rich_content.rich_text_view_helpers import replace_trailing_plain_text_with_html
from src.ui.theme import design_tokens as tk

logger = logging.getLogger("ted")

TAIL_HEIGHT = 10
TAIL_OFFSET_X = 46  # trùng vị trí nhân vật (x=54) bên trái cửa sổ companion (300px)
CORNER_RADIUS = 16.0
MIN_BUBBLE_WIDTH = 250
MAX_BUBBLE_WIDTH = 300  # khớp bề rộng của companion widget (300px) khi ở chế độ cheer/nhắc việc
CHAT_BUBBLE_WIDTH = 380  # Khung chat rộng rãi hơn
CHAT_BUBBLE_HEIGHT = 420  # Khung chat cao hơn kèm scroll
SHADOW_SPREAD = 5  # lề trong suốt quanh thân bubble (flat: không vẽ bóng, giữ lề cho viền mood khỏi bị cắt)
# Viền theo mood: accent token; mặc định (không mood) là viền secondary mờ
MOOD_BORDER = {"CHEER": tk.TERTIARY, "GENTLE_NUDGE": tk.WARNING, "FOCUS": tk.TERTIARY, "REST": tk.PRIMARY_SOFT}

BubbleAction = tuple[str, Callable[[], None]]


class PetSpeechBubble(QWidget):
    """
    Bong bóng thoại tương tác nổi phía trên pet:
    - Hiển thị thông điệp, động viên, nhắc việc từ Ted.
    - Chat trực tiếp với Ted ngay trong bong bóng: Khung chat to hơn, có scroll lịch sử dài.
    - Lưu giữ session bền vững qua mỗi lần tắt/bật.
    - Có nút nhỏ Reset Session để tạo luồng trò chuyện mới bất kỳ lúc nào.
    - 2 nút hành động tối ưu UX:
        1. 💬 Chat (Enter): Trò chuyện hỏi đáp nhanh với Não AI.
        2. 🅿️ Bãi đỗ (Ctrl+Enter): Cất nhanh ý tưởng xao nhãng vào Parking Lot.
    - Tự động bo tròn mềm mại, không cướp focus nhưng gõ trực tiếp khi click/mở.
    """

    def __init__(
        self,
        focus_engine=None,
        client_pool=None,
        registry=None,
        quick_chat=None,
        dashboard=None,
    ):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        self._border = qcolor(tk.OUTLINE_SECONDARY)
        self._pet: Optional[QWidget] = None
        self._timeout_ms = 0
        self._margin_h = 14 + SHADOW_SPREAD
        self._margin_v = 10 + SHADOW_SPREAD
        self._tail_offset_x = float(TAIL_OFFSET_X)
        self._in_flight = False
        self._stream_task: Optional[asyncio.Future] = None  # task stream đang chạy → nút ⏹ Dừng huỷ được
        self._module_id: Optional[str] = None
        self._chat_mode = False

        self._focus_engine = focus_engine
        self._client_pool = client_pool
        self._registry = registry
        self._quick_chat = quick_chat
        self._dashboard = dashboard  # nút "🅿️ Xem Bãi đỗ" mở tab Công việc

        self._outer_layout = QVBoxLayout(self)
        self._outer_layout.setContentsMargins(
            self._margin_h, self._margin_v, self._margin_h, self._margin_v + TAIL_HEIGHT
        )
        self._outer_layout.setSpacing(6)

        # 0. Header cho chế độ Chat (Title + Reset Session + Close)
        self._chat_header = QWidget(self)
        self._chat_header.setObjectName("BubbleChatHeader")
        header_layout = QHBoxLayout(self._chat_header)
        header_layout.setContentsMargins(2, 0, 2, 0)
        header_layout.setSpacing(6)

        self._lbl_header_title = QLabel(settings.character_display_name, self._chat_header)
        self._lbl_header_title.setObjectName("BubbleHeaderTitle")
        self._lbl_header_title.setFont(QFont(tk.FONT_FAMILY, 10, QFont.Weight.Bold))
        header_layout.addWidget(self._lbl_header_title)
        header_layout.addStretch()

        self.btn_reset_session = QPushButton(btn_text(tr("chat_btn_reset_session")), self._chat_header)
        self.btn_reset_session.setProperty("compact", True)
        self.btn_reset_session.setToolTip(tr("chat_btn_reset_tooltip"))
        self.btn_reset_session.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_reset_session.clicked.connect(self._on_reset_session_clicked)
        header_layout.addWidget(self.btn_reset_session)

        # Bật/tắt Ted đọc câu trả lời (TTS) — chỉ hiện khi giọng nói đã được cấu hình
        self.btn_toggle_voice = QPushButton(self._chat_header)
        self.btn_toggle_voice.setProperty("compact", True)
        self.btn_toggle_voice.setCheckable(True)
        self.btn_toggle_voice.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_voice.toggled.connect(self._on_toggle_voice)
        header_layout.addWidget(self.btn_toggle_voice)
        self.refresh_voice_toggle()

        self.btn_close = QPushButton("✕", self._chat_header)
        self.btn_close.setObjectName("IconBtn")
        self.btn_close.setFixedSize(22, 22)
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.clicked.connect(self.hide)
        header_layout.addWidget(self.btn_close)

        self._chat_header.hide()
        self._outer_layout.addWidget(self._chat_header)

        # 1. Khung cuộn tin nhắn chat dài (QTextEdit)
        self._chat_view = QTextEdit(self)
        self._chat_view.setObjectName("BubbleChatView")
        self._chat_view.setReadOnly(True)
        self._chat_view.setFont(QFont(tk.FONT_FAMILY, 9))
        self._chat_view.hide()
        self._outer_layout.addWidget(self._chat_view, stretch=1)

        # 2. Label câu thoại đơn của Ted / thông điệp ngắn (dùng cho cheer / alerts)
        self._label = QLabel()
        self._label.setWordWrap(True)
        self._label.setTextFormat(Qt.TextFormat.PlainText)  # giữ tương thích kiểm thử
        self._label.setObjectName("BubbleLabel")
        self._label.setFont(QFont(tk.FONT_FAMILY, 10))
        self._label.setOpenExternalLinks(False)
        self._label.linkActivated.connect(self._on_label_link)  # link "task:<id>" → popup chi tiết task
        self._plain_text = ""
        self._task_dialog = None
        self._label.setMinimumWidth(MIN_BUBBLE_WIDTH - (self._margin_h * 2))
        self._label.setMaximumWidth(MAX_BUBBLE_WIDTH - (self._margin_h * 2))
        self._outer_layout.addWidget(self._label)

        # 3. Action buttons tuỳ chọn (onboarding, nhắc lịch...)
        self._buttons = QHBoxLayout()
        self._buttons.setSpacing(6)
        self._outer_layout.addLayout(self._buttons)

        # 4. Khung nhập liệu chat & bãi đỗ
        self._input_container = QWidget(self)
        self._input_container.setObjectName("BubbleInputContainer")
        input_layout = QVBoxLayout(self._input_container)
        input_layout.setContentsMargins(0, 2, 0, 0)
        input_layout.setSpacing(6)

        self._input_field = QLineEdit(self._input_container)
        self._input_field.setPlaceholderText(tr("bubble_input_placeholder"))
        self._input_field.setObjectName("BubbleInput")
        self._input_field.keyPressEvent = self._input_key_press_event
        self._input_field.textChanged.connect(self._on_input_text_changed)
        # Ô nhập + nút 🎤 nói thay vì gõ (chỉ hiện khi đã bật Nhận giọng nói)
        from src.ui.voice_input_mic_button import VoiceInputMicButton
        field_row = QHBoxLayout()
        field_row.setSpacing(6)
        field_row.addWidget(self._input_field, stretch=1)
        self.btn_mic = VoiceInputMicButton(self._input_field, self._input_container)
        field_row.addWidget(self.btn_mic)
        input_layout.addLayout(field_row)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        self.btn_chat = QPushButton(btn_text(tr("bubble_btn_chat")), self._input_container)
        self.btn_chat.setObjectName("PrimaryBtn")
        self.btn_chat.setProperty("compact", True)
        self.btn_chat.setToolTip(tr("bubble_btn_chat_tooltip"))
        self.btn_chat.clicked.connect(self._on_chat_btn_clicked)
        btn_row.addWidget(self.btn_chat, 1)

        self.btn_park = QPushButton(btn_text(tr("bubble_btn_park")), self._input_container)
        self.btn_park.setProperty("compact", True)  # Bãi đỗ = Secondary ở mọi nơi
        self.btn_park.setToolTip(tr("bubble_btn_park_tooltip"))
        self.btn_park.clicked.connect(self._on_park_submit)
        btn_row.addWidget(self.btn_park, 1)

        input_layout.addLayout(btn_row)
        self._outer_layout.addWidget(self._input_container)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)

        i18n.language_changed.connect(lambda _: self.retranslate_ui())
        if hasattr(chat_session_manager, "session_reset"):
            chat_session_manager.session_reset.connect(self._on_external_session_reset)

    def retranslate_ui(self):
        self._lbl_header_title.setText(settings.character_display_name)
        self.btn_reset_session.setText(btn_text(tr("chat_btn_reset_session")))
        self.btn_reset_session.setToolTip(tr("chat_btn_reset_tooltip"))
        self._update_voice_toggle_text()
        self._input_field.setPlaceholderText(tr("bubble_input_placeholder"))
        self._set_streaming_ui(self._in_flight)
        self.btn_park.setText(btn_text(tr("bubble_btn_park")))
        self.btn_park.setToolTip(tr("bubble_btn_park_tooltip"))

    def setup_services(self, focus_engine=None, client_pool=None, registry=None, quick_chat=None) -> None:
        """Liên kết dịch vụ hệ thống với bong bóng chat."""
        if focus_engine is not None:
            self._focus_engine = focus_engine
        if client_pool is not None:
            self._client_pool = client_pool
        if registry is not None:
            self._registry = registry
        if quick_chat is not None:
            self._quick_chat = quick_chat

    def follow(self, pet_widget: QWidget) -> None:
        """Gắn với cửa sổ pet; gọi reposition() khi pet di chuyển."""
        self._pet = pet_widget

    def is_busy(self) -> bool:
        return self.isVisible()

    def has_pending_actions(self) -> bool:
        """Bubble đang hiện kèm nút hành động (briefing/nudge) → không được ghi đè bằng câu cheer."""
        return self.isVisible() and self._buttons.count() > 0

    def _current_module_id(self) -> str:
        if self._module_id:
            return self._module_id
        if self._registry and hasattr(self._registry, "active"):
            active = self._registry.active()
            if active:
                return active.id
        return "work"

    def _persona_for(self, module_id: str) -> str:
        if self._registry and hasattr(self._registry, "get"):
            manifest = self._registry.get(module_id)
            if manifest:
                return manifest.engine
        return "work"

    def _calc_optimal_width(self, text: str, actions_count: int = 0) -> int:
        padding_h = self._margin_h * 2
        min_w = MIN_BUBBLE_WIDTH
        max_w = MAX_BUBBLE_WIDTH
        if actions_count > 0:
            min_w = max(min_w, min(max_w, actions_count * 85 + padding_h))

        clean_text = text.strip()
        if not clean_text:
            return min_w

        fm = self._label.fontMetrics()
        lines = clean_text.splitlines() or [""]
        longest_line = max(fm.horizontalAdvance(line) for line in lines)

        if longest_line + padding_h <= max_w:
            return max(min_w, longest_line + padding_h)

        usable_max = max_w - padding_h
        r_max = fm.boundingRect(QRect(0, 0, usable_max, 2000), Qt.TextFlag.TextWordWrap, clean_text)
        line_spacing = max(1, fm.lineSpacing())
        min_lines = max(1, round(r_max.height() / line_spacing))

        for candidate_w in range(min_w, max_w, 10):
            usable_w = candidate_w - padding_h
            r = fm.boundingRect(QRect(0, 0, usable_w, 2000), Qt.TextFlag.TextWordWrap, clean_text)
            candidate_lines = max(1, round(r.height() / line_spacing))
            if candidate_lines <= min_lines:
                return candidate_w
        return max_w

    def _apply_layout_for_text(self, text: str, actions_count: int = 0) -> None:
        target_w = self._calc_optimal_width(text, actions_count)
        label_w = target_w - (self._margin_h * 2)
        self._label.setFixedWidth(label_w)
        self.adjustSize()

    def _set_chat_mode(self, enabled: bool) -> None:
        """Chuyển đổi giữa chế độ bong bóng chat mở rộng (có scroll) và chế độ tin nhắn ngắn."""
        self._chat_mode = enabled
        if enabled:
            self._label.hide()
            self._chat_header.show()
            self._chat_view.show()
            self.setFixedSize(CHAT_BUBBLE_WIDTH, CHAT_BUBBLE_HEIGHT)
        else:
            self._chat_header.hide()
            self._chat_view.hide()
            self._label.show()
            self.setMinimumSize(0, 0)
            self.setMaximumSize(16777215, 16777215)

    def _render_session_history(self) -> None:
        """Tải và hiển thị toàn bộ lịch sử tin nhắn của phiên làm việc từ SQLite."""
        module_id = self._current_module_id()
        session = chat_session_manager.get_session(module_id)
        messages = session.get("messages", [])

        # Cùng bộ HTML với Quick Chat: QTextEdit không hỗ trợ inline-block/border-radius trên <span>
        html_parts = []
        if not messages:
            html_parts.append(notice_html(
                "🐾 <b>Ted:</b> Chào bạn! Mình đã sẵn sàng đồng hành cùng bạn. "
                "Cần nhắn gì hoặc cất ý tưởng cứ gửi cho mình nhé!", "info"
            ))
        else:
            for msg in messages:
                raw = msg.get("text", "")
                if msg.get("role", "assistant") == "user":
                    html_parts.append(user_message_html(raw))
                else:
                    html_parts.append(assistant_open_html() + reply_body_html(raw, max_width=320) + "</p>")

        self._chat_view.setHtml("".join(html_parts))
        self._scroll_chat_to_bottom()

    def _scroll_chat_to_bottom(self) -> None:
        cursor = self._chat_view.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self._chat_view.setTextCursor(cursor)
        self._chat_view.ensureCursorVisible()

    def _on_reset_session_clicked(self) -> None:
        """Xoá ngữ cảnh phiên hiện tại, bắt đầu phiên mới."""
        module_id = self._current_module_id()
        chat_session_manager.reset_session(module_id)
        notice = tr("chat_session_reset_notice")
        self._set_label_text(f"🌱 {notice}")
        self._chat_view.setHtml(notice_html(f"<b>🌱 {escape(notice)}</b>", "success"))
        self._scroll_chat_to_bottom()

    def _on_external_session_reset(self, module_id: str) -> None:
        if module_id == self._current_module_id() and self.isVisible() and self._chat_mode:
            self._render_session_history()

    def show_message(
        self,
        text: str,
        mood: Optional[str] = None,
        actions: Sequence[BubbleAction] = (),
        timeout_ms: int = 6000,
        task_links: Sequence[tuple[str, str]] = (),
    ) -> None:
        """task_links: (tên task đúng như trong text, task_id) → tên đó thành link mở popup chi tiết task."""
        self._hide_timer.stop()
        self._set_chat_mode(False)
        self._clear_buttons()
        self._border = qcolor(MOOD_BORDER.get(mood or "", tk.OUTLINE_SECONDARY))
        self._set_label_text(text, task_links)
        self._timeout_ms = timeout_ms
        for caption, callback in actions:
            btn = QPushButton(btn_text(caption))
            btn.setProperty("compact", True)
            btn.clicked.connect(lambda _=False, cb=callback: self._run_action(cb))
            self._buttons.addWidget(btn)
        self._apply_layout_for_text(text, len(actions))
        self.reposition()
        self.show()
        self.raise_()
        if timeout_ms > 0:
            self._hide_timer.start(timeout_ms)

    def current_text(self) -> str:
        return self._plain_text

    def _set_label_text(self, text: str, task_links: Sequence[tuple[str, str]] = ()) -> None:
        """Có link task → RichText (tên task bấm được); còn lại PlainText như cũ (giữ xuống dòng, không hiểu nhầm HTML)."""
        self._plain_text = text
        html = linkify_task_titles(text, task_links) if task_links else ""
        if "<a " in html:
            self._label.setTextFormat(Qt.TextFormat.RichText)
            self._label.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse)
            self._label.setText(html)
        else:
            self._label.setTextFormat(Qt.TextFormat.PlainText)
            self._label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
            self._label.setText(text)

    def _on_label_link(self, href: str) -> None:
        task_id = task_id_from_href(href)
        if task_id:
            self.open_task_detail(task_id)

    def open_task_detail(self, task_id: str):
        """Popup xem/sửa task (giữ tham chiếu để không bị GC); lưu xong refresh Dashboard."""
        from src.ui.task_detail_edit_dialog import TaskDetailEditDialog
        self._hide_timer.stop()  # người dùng đang xem → bubble không tự ẩn giữa chừng
        dialog = TaskDetailEditDialog(task_id, dashboard=self._dashboard, focus_engine=self._focus_engine)
        dashboard = self._dashboard
        if dashboard is not None:
            dialog.task_saved.connect(lambda _id: dashboard.refresh_all())
        self._task_dialog = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        return dialog

    def update_text(self, text: str, mood: Optional[str] = None) -> None:
        """Thay chữ của bong bóng đang hiện, giữ nút; chạy lại bộ đếm ẩn."""
        self._set_label_text(text)
        if mood:
            self._border = qcolor(MOOD_BORDER.get(mood, tk.OUTLINE_SECONDARY))
        self._apply_layout_for_text(text, self._buttons.count())
        self.reposition()
        self.update()
        if self._timeout_ms > 0:
            self._hide_timer.start(self._timeout_ms)

    def refresh_voice_toggle(self) -> None:
        """Đồng bộ nút 🔊 với cấu hình: ẩn nếu TTS chưa cấu hình, trạng thái nhấn = đang bật đọc."""
        from src.core.tts_service import is_tts_configured
        self.btn_toggle_voice.setVisible(is_tts_configured())
        self.btn_toggle_voice.blockSignals(True)
        self.btn_toggle_voice.setChecked(bool(settings.tts_enabled))
        self.btn_toggle_voice.blockSignals(False)
        self._update_voice_toggle_text()

    def _update_voice_toggle_text(self) -> None:
        on = self.btn_toggle_voice.isChecked()
        self.btn_toggle_voice.setText(btn_text(tr("chat_btn_voice_on" if on else "chat_btn_voice_off")))
        self.btn_toggle_voice.setToolTip(tr("chat_btn_voice_tooltip"))

    def _on_toggle_voice(self, checked: bool) -> None:
        settings.tts_enabled = checked
        settings.tts_configured = True
        settings.save()
        if not checked:
            tts_service.stop()   # tắt là im ngay, không đọc nốt câu đang phát
        self._update_voice_toggle_text()

    def open_chat(self, module_id: Optional[str] = None, initial_text: str = "") -> None:
        """Mở bong bóng chat với ô nhập sẵn sàng, hiển thị toàn bộ lịch sử trò chuyện đã lưu."""
        self._hide_timer.stop()
        self.refresh_voice_toggle()   # cấu hình TTS có thể vừa đổi trong Dashboard
        self.btn_mic.refresh_visibility()   # STT có thể vừa bật trong Dashboard
        self._timeout_ms = 0
        if module_id:
            self._module_id = module_id

        self._set_chat_mode(True)
        self._render_session_history()
        self.reposition()
        self.show()
        self.raise_()
        self.activateWindow()

        if initial_text:
            self._input_field.setText(initial_text)
        self._input_field.setFocus()

    def append_ted_line(self, text: str) -> None:
        """Thêm 1 dòng của Ted (không lưu vào phiên) vào khung chat đang mở; bubble đã đóng/không ở chế độ chat → bỏ qua."""
        if not (self.isVisible() and self._chat_mode):
            return
        self._chat_view.append(assistant_open_html() + escape(text).replace("\n", "<br>") + "</p>")
        self._scroll_chat_to_bottom()

    def _input_key_press_event(self, event) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier):
                self._on_park_submit()
                return
            else:
                self._on_chat_submit()
                return
        elif event.key() == Qt.Key.Key_Escape:
            self.hide()
            return
        QLineEdit.keyPressEvent(self._input_field, event)

    def _on_input_text_changed(self, text: str) -> None:
        if text.strip():
            self._hide_timer.stop()

    def _on_chat_submit(self) -> None:
        user_text = self._input_field.text().strip()
        if not user_text or self._in_flight:
            return
        self._in_flight = True
        self._input_field.clear()
        self._hide_timer.stop()
        self._clear_buttons()  # nút "Xem Bãi đỗ" của lần đỗ trước không còn liên quan
        self._set_streaming_ui(True)

        module_id = self._current_module_id()
        client = self._client_pool.for_module(module_id) if self._client_pool else None

        # Cập nhật _label cho tương thích test
        self._set_label_text(f"💬 Bạn: {user_text}\n\n🐾 Ted: đang trả lời...")

        # Thêm tin nhắn của user vào khung chat cuộn
        self._chat_view.append(user_message_html(user_text))
        self._scroll_chat_to_bottom()

        if not self._chat_mode:
            self._apply_layout_for_text(self.current_text())
            self.reposition()

        if client is None:
            err_msg = (
                f"Chưa có kết nối Não AI cho module '{module_id}' — "
                "bạn vào Cài đặt → Module để chọn kết nối nhé!"
            )
            self._set_label_text(f"💬 Bạn: {user_text}\n\n🐾 Ted: {err_msg}")
            self._chat_view.append(notice_html(f"<b>🐾 Ted:</b> {escape(err_msg)}"))
            self._scroll_chat_to_bottom()
            self._in_flight = False
            self._set_streaming_ui(False)
            if not self._chat_mode:
                self._apply_layout_for_text(self.current_text())
                self.reposition()
            return

        try:
            self._stream_task = spawn_background_task(
                self._stream_reply(user_text, client, module_id),
                "bubble-chat-stream",
            )
        except RuntimeError:
            self._in_flight = False
            self._set_streaming_ui(False)

    def _on_chat_btn_clicked(self) -> None:
        """Nút 💬 Chat đổi thành ⏹ Dừng khi Ted đang trả lời."""
        if self._in_flight:
            self._stop_reply()
        else:
            self._on_chat_submit()

    def _stop_reply(self) -> None:
        """Huỷ câu trả lời đang stream (vd. gửi nhầm); phần đã nhận giữ lại trong khung chat."""
        tts_service.stop()
        task = self._stream_task
        if task is not None and not task.done():
            task.cancel()

    def _set_streaming_ui(self, streaming: bool) -> None:
        """Đang stream: nút Chat thành ⏹ Dừng; ô nhập và 🅿️ Bãi đỗ vẫn dùng được."""
        key = "bubble_btn_stop" if streaming else "bubble_btn_chat"
        self.btn_chat.setText(btn_text(tr(key)))
        self.btn_chat.setToolTip(tr(key + "_tooltip"))

    async def _stream_reply(self, user_text: str, client, module_id: str) -> None:
        detector = ChatJsonTailDetector()
        full_reply = ""
        tts_service.stop()  # câu hỏi mới: im ngay câu trả lời cũ, chỉ đọc câu trả lời mới

        # Mở đoạn trả lời mới — append() tạo block riêng, không dính vào tin trước hay kế thừa căn lề của nó
        if isValid(self):
            self._chat_view.append(assistant_open_html())
            self._scroll_chat_to_bottom()

        def on_token(token: str) -> None:
            nonlocal full_reply
            if not token or not isValid(self):
                return
            filtered = detector.feed(token)
            if filtered:
                full_reply += filtered
                self._set_label_text(f"💬 Bạn: {user_text}\n\n🐾 Ted: {full_reply}")
                cursor = self._chat_view.textCursor()
                cursor.movePosition(QTextCursor.MoveOperation.End)
                cursor.insertText(filtered)
                self._scroll_chat_to_bottom()
                if not self._chat_mode:
                    self._apply_layout_for_text(self.current_text())
                    self.reposition()

        try:
            context_snapshot = (
                self._focus_engine.get_context_snapshot()
                if self._focus_engine and hasattr(self._focus_engine, "get_context_snapshot")
                else {}
            )
            on_mood = (
                self._focus_engine.set_mood
                if self._focus_engine and hasattr(self._focus_engine, "set_mood")
                else (lambda m: None)
            )
            persona = self._persona_for(module_id)

            await client.stream_chat(
                user_message=user_text,
                current_context=context_snapshot,
                on_mood_change=on_mood,
                on_token=on_token,
                persona=persona,
                resume_mood=getattr(self._focus_engine, "current_mood", None),
            )
            leftover, _data = detector.finish()
            if leftover:
                full_reply += leftover
                if isValid(self):
                    self._set_label_text(f"💬 Bạn: {user_text}\n\n🐾 Ted: {full_reply}")
                    cursor = self._chat_view.textCursor()
                    cursor.movePosition(QTextCursor.MoveOperation.End)
                    cursor.insertText(leftover)
                    self._scroll_chat_to_bottom()
                    if not self._chat_mode:
                        self._apply_layout_for_text(self.current_text())
                        self.reposition()

            if isValid(self):
                replace_trailing_plain_text_with_html(self._chat_view, full_reply, max_width=320)   # công thức/bảng/hình
                self._scroll_chat_to_bottom()

            # Lưu vào session bền vững để lần tắt/bật sau tiếp tục theo dõi
            chat_session_manager.record_turn(module_id, user_text, full_reply)

            # Phát giọng nói TTS nếu đang bật
            if settings.tts_enabled:
                spawn_background_task(tts_service.speak(full_reply), "bubble-tts-reply")

        except asyncio.CancelledError:
            if isValid(self):
                self._chat_view.append(notice_html(f"<b>🐾 Ted:</b> {escape(tr('bubble_reply_stopped'))}", "info"))
                self._scroll_chat_to_bottom()
            raise
        except Exception as exc:
            logger.exception("Bubble stream_chat lỗi")
            if isValid(self) and not full_reply:
                err_text = f"Lỗi kết nối ({type(exc).__name__})."
                self._set_label_text(f"💬 Bạn: {user_text}\n\n🐾 Ted: {err_text}")
                self._chat_view.append(notice_html(f"<b>🐾 Ted:</b> {escape(err_text)}"))
                self._scroll_chat_to_bottom()
                if not self._chat_mode:
                    self._apply_layout_for_text(self.current_text())
                    self.reposition()
        finally:
            self._in_flight = False
            self._stream_task = None
            if isValid(self):
                self._set_streaming_ui(False)
                self._input_field.setFocus()
                if self._quick_chat and hasattr(self._quick_chat, "transcripts"):
                    try:
                        self._quick_chat.transcripts.append_html(
                            module_id,
                            user_message_html(user_text) + assistant_open_html() + reply_body_html(full_reply) + "</p>",
                        )
                    except Exception:
                        pass

    def _on_park_submit(self) -> None:
        idea = self._input_field.text().strip()
        if not idea:
            return
        self._input_field.clear()
        task = None
        if self._focus_engine and hasattr(self._focus_engine, "record_distraction"):
            task = self._focus_engine.record_distraction(parked_idea_text=idea)

        self._border = qcolor(MOOD_BORDER["GENTLE_NUDGE"])
        park_msg = f"🅿️ Đã cất vào Bãi đỗ: \"{idea}\"\n\nYên tâm tập trung nhé, hết phiên Ted sẽ nhắc bạn!"
        self._set_label_text(park_msg)
        self._show_view_parking_button(getattr(task, "id", None))

        if self._chat_mode:
            self._chat_view.append(
                notice_html(f"<b>🅿️ Đã cất vào Bãi đỗ:</b> <i>{escape(idea)}</i> — Yên tâm làm tiếp nhé!", "info")
            )
            self._scroll_chat_to_bottom()
        else:
            self._apply_layout_for_text(self.current_text(), self._buttons.count())
            self.reposition()
            self.update()
            self._hide_timer.start(7000)

        if self._quick_chat and hasattr(self._quick_chat, "_log_html"):
            try:
                self._quick_chat._log_html(
                    f"<p style='color:{tk.PRIMARY_SOFT};'><b>🅿️ Đã cất vào Bãi đỗ:</b> <i>{escape(idea)}</i></p>"
                )
            except Exception:
                pass

    def _show_view_parking_button(self, task_id: Optional[str]) -> None:
        """Nút ngay dưới câu trả lời: mở tab Công việc (Danh sách), chọn sẵn ý tưởng vừa đỗ."""
        self._clear_buttons()
        dashboard = self._dashboard
        if dashboard is None:
            return
        btn = QPushButton(btn_text(tr("bubble_btn_view_parking")))
        btn.setProperty("compact", True)
        btn.clicked.connect(lambda _=False: self._run_action(lambda: dashboard.open_tasks_list(task_id)))
        self._buttons.addWidget(btn)
        btn.show()  # bubble đang hiện: Qt chỉ hiện nút ở vòng lặp sau → adjustSize sẽ bỏ sót chiều cao nút

    def _run_action(self, callback: Callable[[], None]) -> None:
        self.hide()
        callback()

    def _clear_buttons(self) -> None:
        while self._buttons.count():
            item = self._buttons.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def reposition(self) -> None:
        pet = self._pet
        if pet is None or not isValid(pet):
            return
        pos = pet.pos()
        x, y = pos.x(), pos.y() - self.height() + 6 + SHADOW_SPREAD
        # Kẹp theo màn hình Ted đang đứng (nhiều màn hình) — dùng primaryScreen sẽ ghim bubble ở mép màn chính
        screen = QApplication.screenAt(pet.geometry().center()) or pet.screen()
        if screen:
            geo = screen.availableGeometry()
            x = min(max(geo.left() + 4, x), geo.right() - self.width() - 4)
            y = max(geo.top() + 4, y)

        avatar_center_x = pos.x() + 54
        ideal_tail_x = float(avatar_center_x - x - 8)
        min_tail_x = CORNER_RADIUS + 2.0
        max_tail_x = max(min_tail_x, float(self.width()) - CORNER_RADIUS - 18.0)
        self._tail_offset_x = min(max(min_tail_x, ideal_tail_x), max_tail_x)

        self.move(QPoint(x, y))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        inset = float(SHADOW_SPREAD)
        body = QRectF(
            inset,
            inset,
            float(self.width()) - 2 * inset,
            float(self.height()) - TAIL_HEIGHT - 2 * inset,
        )
        base = body.bottom()
        tail_left = float(self._tail_offset_x)
        tail_left = max(CORNER_RADIUS + 2.0, min(float(self.width()) - CORNER_RADIUS - 18.0, tail_left))

        def bubble_path(grow: float, dy: float) -> QPainterPath:
            """Thân bo góc + đuôi nhọn; `grow`/`dy` nở/lệch đường viền (0 = đúng thân)."""
            rect = QPainterPath()
            r = CORNER_RADIUS + grow
            rect.addRoundedRect(body.adjusted(-grow, -grow + dy, grow, grow + dy), r, r)
            tail = QPainterPath()
            tail.moveTo(tail_left - grow, base - 1.0 + dy)
            tail.lineTo(tail_left + 8.0, base + TAIL_HEIGHT + grow + dy)
            tail.lineTo(tail_left + 16.0 + grow, base - 1.0 + dy)
            tail.closeSubpath()
            return rect.united(tail).simplified()

        # Flat (docs/UI/style-guideline.md): nền đặc L3 + viền mood 1.2px, không bóng đổ
        full_path = bubble_path(0.0, 0.0)
        painter.fillPath(full_path, qcolor(tk.SURFACE_OVERLAY, 0.97))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(self._border, 1.2))
        painter.drawPath(full_path)
