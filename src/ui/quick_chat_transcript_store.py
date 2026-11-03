"""Lịch sử khung chat TÁCH THEO MODULE: đổi module thì đổi nội dung hiển thị, hội thoại của module này không bao giờ
hiện dưới module khác. Ghi vào module đang ẩn (stream còn chạy dở) được xếp hàng rồi phát lại khi quay lại.
Tự động khôi phục từ ChatSessionManager để giữ vững luồng chat khi tắt đi bật lại app."""

import logging
from typing import Optional

from PySide6.QtGui import QTextCursor

logger = logging.getLogger("ted")


class ChatTranscriptStore:
    def __init__(self, view, welcome_html: str):
        self._view = view
        self._welcome = welcome_html
        self.current: Optional[str] = None            # module đang hiển thị trong `view` (None = chưa gắn)
        self._saved: dict[str, str] = {}              # module_id -> HTML đã lưu khi rời đi
        self._pending: dict[str, list[tuple[str, str]]] = {}   # ghi dở vào module đang ẩn: ("html"|"text", nội dung)

    def _html_for_module(self, module_id: str) -> str:
        if module_id in self._saved:
            return self._saved[module_id]
        # Khôi phục từ ChatSessionManager nếu app vừa khởi động lại
        try:
            from src.core.chat_session_manager import chat_session_manager
            from src.ui.quick_chat_message_html import assistant_open_html, user_message_html
            from src.ui.rich_content.rich_reply_html_renderer import reply_body_html

            session = chat_session_manager.get_session(module_id)
            messages = session.get("messages", [])
            if messages:
                html = self._welcome
                for m in messages:
                    txt = m.get("text", "")
                    if m.get("role") == "user":
                        html += user_message_html(txt)
                    else:
                        html += assistant_open_html() + reply_body_html(txt) + "</p>"
                self._saved[module_id] = html
                return html
        except Exception as exc:
            logger.debug("Không thể khôi phục phiên chat cho module %s: %s", module_id, exc)

        return self._welcome

    def switch_to(self, module_id: str) -> None:
        if module_id == self.current:
            return
        if self.current is None:
            self.current = module_id
            self._view.setHtml(self._html_for_module(module_id))
            self._replay(module_id)
            return
        self._saved[self.current] = self._view.toHtml()
        self.current = module_id
        self._view.setHtml(self._html_for_module(module_id))
        self._replay(module_id)

    def clear_for(self, module_id: str) -> None:
        """Xoá sạch lịch sử hiển thị của module khi reset session."""
        self._saved[module_id] = self._welcome
        if self.current == module_id:
            self._view.setHtml(self._welcome)

    def append_html(self, module_id: str, html: str) -> None:
        if self.current is None:
            self.current = module_id
        if module_id == self.current:
            self._view.append(html)
        else:
            self._pending.setdefault(module_id, []).append(("html", html))

    def insert_text(self, module_id: str, text: str) -> None:
        if self.current is None:
            self.current = module_id
        if module_id != self.current:
            self._pending.setdefault(module_id, []).append(("text", text))
            return
        self._insert_visible(text)

    def render_streamed_reply(self, module_id: str, raw_text: str) -> None:
        """Stream xong: thay chữ thuần vừa stream bằng công thức / bảng / hình vẽ (module đang ẩn thì xếp hàng)."""
        from src.ui.rich_content.rich_reply_segment_patterns import has_rich_markup
        if not has_rich_markup(raw_text):
            return
        if module_id == self.current:
            from src.ui.rich_content.rich_text_view_helpers import replace_trailing_plain_text_with_html
            replace_trailing_plain_text_with_html(self._view, raw_text)
            self._view.ensureCursorVisible()
        else:
            self._pending.setdefault(module_id, []).append(("rich", raw_text))

    def _insert_visible(self, text: str) -> None:
        cursor = self._view.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(text)
        self._view.setTextCursor(cursor)
        self._view.ensureCursorVisible()

    def _replay(self, module_id: str) -> None:
        for kind, content in self._pending.pop(module_id, []):
            if kind == "html":
                self._view.append(content)
            elif kind == "rich":
                self.render_streamed_reply(module_id, content)
            else:
                self._insert_visible(content)
