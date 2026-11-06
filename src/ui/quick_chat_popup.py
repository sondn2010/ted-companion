import logging
from html import escape
from typing import Callable, Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget
from src.config import settings
from src.core.chat_session_manager import chat_session_manager
from src.core.i18n import i18n, tr
from src.core.background_task_spawner import spawn_background_task
from src.ui.quick_chat_message_html import assistant_open_html, notice_html, user_message_html
from src.ui.quick_chat_popup_layout import build_quick_chat_ui
from src.ui.quick_chat_stream_runner import stream_reply_into_popup
from src.ui.button_text_escape import btn_text

logger = logging.getLogger("ted")
WORK_MODULE_ID = "work"
BUSY_HINT = "Ted đang trả lời, thử lại sau nhé"


class QuickChatPopup(QWidget):
    """
    Trang "💬 Chat" nằm trong Dashboard (không còn là popup nổi cạnh Ted; double-click avatar mở trang này):
    - Trò chuyện trực tiếp với não bộ Hermes Agent (Streaming).
    - Cất nhanh ý tưởng gây xao nhãng vào Parking Lot chỉ với 1 phím Enter.
    - Trả lời Mindful Ping 1 chạm.
    Cần hiện ra → phát `reveal_requested`; Dashboard mở trang Chat (DashboardWindow.bind_chat).
    """

    reveal_requested = Signal()

    def __init__(self, focus_engine, client_pool, registry, parent=None):
        super().__init__(parent)
        self.focus_engine = focus_engine
        self._pool = client_pool
        self._registry = registry
        self._module_id: Optional[str] = None  # module đang gắn với popup; None = module chính
        self._in_flight = False  # đang stream 1 câu trả lời → chặn gửi chồng; nút Gửi thành ⏹ Dừng
        self._stream_task = None  # task stream đang chạy, để nút ⏹ Dừng huỷ
        self._display_override: Optional[str] = None  # nhãn hiển thị thay cho prefill giao thức, dùng 1 lần
        # module_id -> callback nhận khối <json> cuối câu trả lời (vd. {"onboarding":"done"}); là hàm của engine, không phải widget
        self._reply_json_handlers: dict[str, Callable[[dict], None]] = {}
        self._build_ui()
        self.focus_engine.character_changed.connect(lambda _: self.refresh_mode_badge())
        i18n.language_changed.connect(lambda _: self.retranslate_ui())

    def _build_ui(self):
        build_quick_chat_ui(self)

    def _current_module_id(self) -> str:
        if self._module_id:
            return self._module_id
        active = self._registry.active()
        return active.id if active else "work"

    def _mode_badge_text(self) -> str:
        client = self._pool.for_module(self._current_module_id())
        return client.connection.name if client else tr("quick_chat_no_conn")

    def retranslate_ui(self):
        self.refresh_mode_badge()
        if hasattr(self, "btn_reset"):
            self.btn_reset.setToolTip(tr("chat_btn_reset_tooltip"))
        self.input_parking.setPlaceholderText(tr("quick_chat_parking_placeholder"))
        self.btn_park.setText(btn_text(tr("quick_chat_btn_park")))
        self.input_chat.setPlaceholderText(tr("quick_chat_input_placeholder"))
        self.set_streaming_ui(self._in_flight)

    def _on_reset_session(self):
        mid = self._current_module_id()
        chat_session_manager.reset_session(mid)
        self.transcripts.clear_for(mid)
        self._log_html(notice_html(f"🌱 <b>{tr('chat_session_reset_notice')}</b>", "success"))

    def refresh_mode_badge(self):
        self.lbl_title.setText(settings.character_display_name)
        self.lbl_mode_badge.setText(self._mode_badge_text())

    def _log_html(self, html: str) -> None:
        """Ghi 1 đoạn HTML vào hội thoại của module đang gắn với popup."""
        self.transcripts.append_html(self._current_module_id(), html)

    def _bind_module(self, module_id: str) -> None:
        """Gắn popup với `module_id`: đổi kết nối, nhãn và hội thoại hiển thị theo module đó."""
        self._module_id = module_id
        self.transcripts.switch_to(module_id)
        self.refresh_mode_badge()
        if hasattr(self, "btn_reset"):
            self.btn_reset.setToolTip(tr("chat_btn_reset_tooltip"))

    def open_for(
        self, module_id: str, prefill: Optional[str] = None, auto_send: bool = False,
        display_text: Optional[str] = None,
    ) -> bool:
        """Mở chat gắn với kết nối của `module_id`; có thể điền sẵn (và tự gửi) 1 câu.
        `display_text`: nhãn ngắn hiện trong khung chat khi `prefill` là gói giao thức [TED_*] thô.
        Trả True khi câu đã được gửi (auto_send) hoặc trang Chat hiện để nhập tay; False khi từ chối vì đang stream dở."""
        self._bind_module(module_id)
        self.btn_mic.refresh_visibility()   # STT có thể vừa bật/tắt trong Dashboard
        refused = bool(prefill and auto_send and self._in_flight)
        if refused:
            # Không để gói [TED_*] thô nằm lại ô nhập và không để nhãn cũ gắn nhầm vào tin nhắn tay kế tiếp
            self._display_override = None
            self._log_html(notice_html(f"<b>Ted:</b> {escape(BUSY_HINT)}"))
        elif prefill:
            self.input_chat.setText(prefill)
            self._display_override = display_text if auto_send else None
        self.reveal_requested.emit()
        self.input_chat.setFocus()
        if refused:
            return False
        if prefill and auto_send:
            return self._on_send_chat()
        return True

    def focus_parking_input(self) -> None:
        """Đưa con trỏ vào ô nhập nhanh Bãi đỗ (phím tắt "cất nhanh ý tưởng")."""
        self.input_parking.setFocus()

    def set_reply_json_handler(self, module_id: str, handler: Optional[Callable[[dict], None]]) -> None:
        if handler is None:
            self._reply_json_handlers.pop(module_id, None)
        else:
            self._reply_json_handlers[module_id] = handler

    def _persona_for(self, module_id: str) -> str:
        """Engine của module quyết định system prompt/header của chat (work giữ nguyên, coach theo SOUL của profile)."""
        manifest = self._registry.get(module_id) if hasattr(self._registry, "get") else None
        return manifest.engine if manifest else "work"

    def show_mindful_ping(self, task_title: str):
        self._bind_module(WORK_MODULE_ID)   # Mindful Ping thuộc phiên Deep Work: không dùng nhầm profile gia sư đang gắn
        self.ping_banner.ask(task_title)
        self.reveal_requested.emit()

    def show_ai_nudge(self, mood: str, message: str):
        """Chỉ lưu lời nhắc vào hội thoại work (lời nhắc hiện ở bubble, không bật cả app lên)."""
        self.transcripts.append_html(WORK_MODULE_ID, notice_html(f"<b>Ted [{escape(mood)}]:</b> {escape(message)}"))

    show_hermes_nudge = show_ai_nudge

    def _on_confirm_focused(self):
        self.ping_banner.hide()
        self.focus_engine.set_mood("FOCUS")
        self._log_html(
            notice_html("<b>Ted:</b> Tuyệt vời! Giữ vững nhịp độ nhé, mình vẫn đang canh giờ cho bạn.", "success")
        )

    def _on_report_distracted(self):
        self.ping_banner.hide()
        self.focus_engine.record_distraction()
        self.focus_engine.set_mood("GENTLE_NUDGE")
        self._log_html(
            notice_html(
                "<b>Ted:</b> Không sao cả, nhận ra mình đang xao nhãng đã là thành công rồi! "
                "Hít sâu một nhịp rồi mình quay lại làm tiếp 5 phút nhẹ nhàng nhé."
            )
        )

    def _on_park_idea(self):
        text = self.input_parking.text().strip()
        if not text:
            return
        self.input_parking.clear()
        self.focus_engine.record_distraction(parked_idea_text=text)
        self._log_html(
            notice_html(
                f"<b>🅿️ Đã cất vào Bãi đỗ:</b> <i>{escape(text)}</i> "
                f"— Yên tâm quay lại phiên Deep Work nhé, hết giờ mình sẽ nhắc bạn!",
                "info",
            )
        )

    def _on_send_chat(self) -> bool:
        """True khi đã khởi chạy stream; False khi bị bỏ qua (rỗng/đang stream) hoặc chưa có event loop."""
        user_text = self.input_chat.text().strip()
        if not user_text or self._in_flight:
            return False
        self._in_flight = True
        self.input_chat.clear()
        shown, self._display_override = self._display_override or user_text, None
        module_id = self._current_module_id()   # chốt lúc gửi: đổi module giữa chừng không làm lệch callback
        self.transcripts.append_html(module_id, user_message_html(shown))
        self.transcripts.append_html(module_id, assistant_open_html())
        self.set_streaming_ui(True)
        client = self._pool.for_module(module_id)
        coro = self._stream_from_ai(user_text, client, module_id)
        try:
            self._stream_task = spawn_background_task(coro, "quick-chat-stream")
        except RuntimeError:   # chưa có event loop: nhả khoá để người dùng gửi lại được
            coro.close()
            self._in_flight = False
            self.set_streaming_ui(False)
            return False
        return True

    def _on_send_btn_clicked(self) -> None:
        """Nút Gửi đổi thành ⏹ Dừng khi Ted đang trả lời."""
        if self._in_flight:
            self._stop_reply()
        else:
            self._on_send_chat()

    def _stop_reply(self) -> None:
        """Huỷ câu trả lời đang stream (vd. gửi nhầm); phần đã nhận giữ lại trong khung chat."""
        from src.core.tts_service import tts_service
        tts_service.stop()
        task = self._stream_task
        if task is not None and not task.done():
            task.cancel()

    def set_streaming_ui(self, streaming: bool) -> None:
        self.btn_send.setText(btn_text(tr("bubble_btn_stop" if streaming else "quick_chat_btn_send")))
        self.btn_send.setToolTip(tr("bubble_btn_stop_tooltip") if streaming else "")

    async def _stream_from_ai(self, user_text: str, client, module_id: str):
        await stream_reply_into_popup(self, user_text, client, module_id)

    _stream_from_hermes = _stream_from_ai
