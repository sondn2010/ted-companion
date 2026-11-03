"""Hộp thoại Gỡ Rối Ý Tưởng: chat kể-cho-Ted-nghe gắn với module đang active (work/coach) + Tóm tắt & Phản biện.

Dùng lại hạ tầng Quick Chat: `stream_reply_into_popup` (duck-typed host: transcripts, focus_engine, _persona_for,
_reply_json_handlers, _in_flight, _stream_task, set_streaming_ui). Một khoá `_in_flight` chung cho stream lẫn phản biện.
"""

import logging
from html import escape
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog

from src.core.background_task_spawner import spawn_background_task
from src.core.chat_session_manager import chat_session_manager
from src.core.i18n import i18n, tr
from src.core.idea_untangle.idea_untangle_service_and_completion_signal import idea_untangle_service
from src.core.idea_untangle.untangle_critique_request import build_chat_message
from src.core.idea_untangle.untangle_problem_kinds_by_engine import DEFAULT_KIND, audience_for
from src.ui.button_text_escape import btn_text
from src.ui.idea_untangle.untangle_dialog_critique_actions_mixin import UntangleCritiqueActionsMixin
from src.ui.idea_untangle.untangle_dialog_kind_chips_mixin import UntangleKindChipsMixin
from src.ui.idea_untangle.untangle_dialog_layout import build_untangle_ui
from src.ui.idea_untangle.untangle_last_session_hint import last_session_hint
from src.ui.quick_chat_message_html import assistant_open_html, notice_html, user_message_html
from src.ui.quick_chat_stream_runner import stream_reply_into_popup

logger = logging.getLogger("ted")


class UntangleDialog(UntangleKindChipsMixin, UntangleCritiqueActionsMixin, QDialog):
    def __init__(self, focus_engine, client_pool, registry, kv=None, service=idea_untangle_service, db_=None, parent=None):
        super().__init__(parent)
        self.focus_engine, self._pool, self._registry, self._kv, self._service = focus_engine, client_pool, registry, kv, service
        if db_ is None:
            from src.core.models import db as db_
        self._db = db_
        self._module_id, self._engine, self._kind, self._trigger = "work", "work", DEFAULT_KIND, "menu"
        self._task_id: Optional[str] = None
        self._task_title, self._session_id = "", None
        self._turns: list = []            # [{"role": "user"|"assistant", "text": ...}] — gốc, không kèm thẻ giao thức
        self._critique, self._in_flight, self._stream_task = None, False, None
        self._reply_json_handlers: dict = {}   # runner yêu cầu thuộc tính này; Gỡ Rối không dùng
        self._fresh_keys: set = set()          # khoá hội thoại đã dọn lần đầu của lượt chạy app này
        self.setObjectName("PopupRoot")
        self.setWindowTitle(tr("untangle_dialog_title"))
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint)
        self.resize(520, 660)
        build_untangle_ui(self)
        i18n.language_changed.connect(lambda _: self.retranslate_ui())
        self._refresh_actions()

    # ---- host duck-typing cho stream runner ----
    @property
    def _key(self) -> str:
        return f"untangle:{self._module_id}"   # hội thoại Gỡ Rối tách khỏi chat thường, kid/work không lẫn

    def _persona_for(self, _module_id: str) -> str:
        return self._engine

    def set_streaming_ui(self, streaming: bool) -> None:
        self.btn_send.setText(btn_text(tr("bubble_btn_stop" if streaming else "quick_chat_btn_send")))
        self.btn_send.setToolTip(tr("bubble_btn_stop_tooltip") if streaming else "")
        self._refresh_actions()

    # ---- mở / gắn ngữ cảnh ----
    def open_from(self, trigger: str = "menu", module_id: Optional[str] = None, task_id: Optional[str] = None,
                  kind: Optional[str] = None) -> None:
        if self._in_flight:   # đang stream/phản biện: giữ ngữ cảnh phiên đang chạy (không gắn kết quả sang task khác)
            active = self._registry.get(self._module_id)
            new_module, new_engine, task_id = self._module_id, self._engine, self._task_id
        else:
            active = self._registry.get(module_id) if module_id else self._registry.active()
            new_module = active.id if active else "work"
            new_engine = active.engine if active else "work"
            task_id = task_id or getattr(self.focus_engine, "active_task_id", None) or None
        changed = (new_module, task_id) != (self._module_id, self._task_id) or f"untangle:{new_module}" not in self._fresh_keys
        self._module_id, self._engine, self._task_id, self._trigger = new_module, new_engine, task_id, trigger
        self._task_title = self._resolve_task_title(task_id)
        if changed and not self._in_flight:
            self._session_id, self._turns, self._critique = None, [], None
            self._begin_view()
        self.transcripts.switch_to(self._key)
        self._refresh_kinds(kind)
        self.lbl_module.setText(f"{active.icon} {active.name}".strip() if active else "Ted")
        self.lbl_task.setText(tr("untangle_task_chip", task=self._task_title) if self._task_id else tr("untangle_no_task"))
        self.btn_mic.refresh_visibility()   # STT có thể vừa bật/tắt trong Dashboard
        self._refresh_actions()
        self.show()
        self.raise_()
        self.activateWindow()   # hotkey/bubble có quyền foreground → lên trước app đang dùng
        self.input_chat.setFocus()

    def _resolve_task_title(self, task_id: Optional[str]) -> str:
        if not task_id:
            return ""
        try:
            task = self._db.get_task(task_id)
            return task.title if task else ""
        except Exception:
            logger.exception("Gỡ Rối: không đọc được task %s", task_id)
            return ""

    def _begin_view(self) -> None:
        """Hội thoại mới: dọn khung, chào theo audience, nhắc phiên gần nhất của task (nếu có)."""
        self._fresh_keys.add(self._key)
        self.transcripts.clear_for(self._key)
        self.transcripts.switch_to(self._key)
        intro = tr("untangle_intro_learner" if audience_for(self._engine) == "learner" else "untangle_intro_work")
        self.transcripts.append_html(self._key, notice_html(f"<b>Ted:</b> {escape(intro)}", "info"))
        try:
            hint = last_session_hint(self._service.repo, self._task_id)
        except Exception:
            logger.exception("Gỡ Rối: không đọc được phiên gần nhất")
            return
        if hint:
            self.transcripts.append_html(self._key, notice_html(escape(hint), "info"))

    # ---- gửi chat ----
    def _has_user_turn(self) -> bool:
        return any(t["role"] == "user" for t in self._turns)

    def _refresh_actions(self) -> None:
        idle = not self._in_flight
        self.btn_critique.setEnabled(idle and self._has_user_turn())
        self.btn_save_notes.setVisible(self._critique is not None and bool(self._task_id))
        self.btn_next_task.setVisible(self._critique is not None and bool(self._critique.next_step))
        self.btn_new_session.setEnabled(idle)

    def _ensure_session(self) -> None:
        if self._session_id is None:
            row = self._service.repo.create_session(self._module_id, self._engine, self._task_id, self._task_title,
                                                    self._kind, self._trigger)
            self._session_id = row.id

    def _on_send_chat(self) -> bool:
        text = self.input_chat.text().strip()
        if not text:
            return False
        if self._in_flight:
            self.transcripts.append_html(self._key, notice_html(f"<b>Ted:</b> {escape(tr('untangle_busy'))}"))
            return False
        try:
            self._ensure_session()
        except Exception:
            logger.exception("Gỡ Rối: không tạo được phiên")   # vẫn chat được, chỉ không lưu lịch sử
        self._in_flight = True
        self.input_chat.clear()
        key = self._key
        self.transcripts.append_html(key, user_message_html(text))
        self.transcripts.append_html(key, assistant_open_html())
        self.set_streaming_ui(True)
        sent = build_chat_message(self._engine, self._kind, self._task_title, text)
        coro = self._stream(sent, text, self._pool.for_module(self._module_id), key)
        return self._spawn(coro, "untangle-chat-stream")

    def _spawn(self, coro, name: str) -> bool:
        try:
            self._stream_task = spawn_background_task(coro, name)
            return True
        except RuntimeError:   # chưa có event loop: nhả khoá
            coro.close()
            self._in_flight = False
            self.set_streaming_ui(False)
            return False

    async def _stream(self, sent: str, raw: str, client, key: str) -> None:
        before = len(chat_session_manager.get_session(key).get("messages", []))
        await stream_reply_into_popup(self, sent, client, key)   # bị huỷ → ném CancelledError, không ghi lượt
        messages = chat_session_manager.get_session(key).get("messages", [])
        if len(messages) >= before + 2:   # runner đã record_turn → lấy câu trả lời thật
            self._turns += [{"role": "user", "text": raw}, {"role": "assistant", "text": messages[-1].get("text", "")}]
            self._save_transcript()
            self._refresh_actions()

    def _save_transcript(self) -> None:
        if self._session_id:
            try:
                self._service.repo.save_transcript(self._session_id, self._turns)
            except Exception:
                logger.exception("Gỡ Rối: không lưu được transcript")

    def _on_send_btn_clicked(self) -> None:
        if self._in_flight:
            from src.core.tts_service import tts_service
            tts_service.stop()
            task = self._stream_task
            if task is not None and not task.done():
                task.cancel()
        else:
            self._on_send_chat()

    def _on_new_session(self) -> None:
        if self._in_flight:
            return
        # Chỉ mở bản ghi/khung hội thoại mới cho khoá "untangle:<module>". KHÔNG đụng client.history:
        # lịch sử Hermes được mọi khung chat của cùng kết nối dùng chung (Quick Chat, bong bóng).
        chat_session_manager.reset_session(self._key)
        self._session_id, self._turns, self._critique = None, [], None
        self._begin_view()
        self._refresh_actions()

    def retranslate_ui(self) -> None:
        self.setWindowTitle(tr("untangle_dialog_title"))
        self.lbl_title.setText(tr("untangle_dialog_title"))
        self.btn_critique.setText(btn_text(tr("untangle_btn_critique")))
        self.btn_save_notes.setText(btn_text(tr("untangle_btn_save_notes")))
        self.btn_next_task.setText(btn_text(tr("untangle_btn_next_task")))
        self.btn_new_session.setToolTip(tr("untangle_btn_new_session"))
        self.input_chat.setPlaceholderText(tr("untangle_input_placeholder"))
        self._refresh_kinds()
        self.set_streaming_ui(self._in_flight)
