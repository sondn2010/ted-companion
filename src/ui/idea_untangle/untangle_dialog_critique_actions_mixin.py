"""Mixin phản biện + hành động sau phản biện (lưu ghi chú, tạo task bước tiếp) của UntangleDialog."""

import logging
from html import escape

from src.core.i18n import tr
from src.core.idea_untangle.untangle_critique_request import request_untangle_critique
from src.ui.idea_untangle.untangle_critique_result_html import critique_html, notes_text
from src.ui.quick_chat_message_html import notice_html
from src.ui.quick_chat_stream_runner import NO_CONNECTION_HTML

logger = logging.getLogger("ted")


class UntangleCritiqueActionsMixin:
    # ---- phản biện ----
    def _on_critique(self) -> None:
        if self._in_flight or not self._has_user_turn():
            return
        self._in_flight = True
        self.set_streaming_ui(True)
        self.transcripts.append_html(self._key, notice_html(escape(tr("untangle_critique_pending")), "info"))
        client = self._pool.for_module(self._module_id)
        self._spawn(self._run_critique(client, self._key), "untangle-critique")

    async def _run_critique(self, client, key: str) -> None:
        try:
            if client is None:
                self.transcripts.append_html(key, NO_CONNECTION_HTML)
                return
            critique = await request_untangle_critique(client, self._engine, self._kind, self._turns)
            if critique is None:
                self.transcripts.append_html(key, notice_html(f"<b>Ted:</b> {escape(tr('untangle_critique_failed'))}"))
                return
            self._critique = critique
            self.transcripts.append_html(key, critique_html(critique))
            self._complete_session(critique)
        finally:
            self._in_flight = False
            self._stream_task = None
            self.set_streaming_ui(False)

    def _complete_session(self, critique) -> None:
        if not self._session_id:
            return
        try:
            self._service.complete(self._session_id, critique.model_dump_json())
        except Exception:
            logger.exception("Gỡ Rối: không đánh dấu hoàn tất phiên")

    # ---- hành động sau phản biện ----
    def _on_save_notes(self) -> None:
        if self._critique is None or not self._task_id:
            return
        try:
            saved = self._db.append_task_notes(self._task_id, notes_text(self._critique))
        except Exception:
            logger.exception("Gỡ Rối: không lưu được ghi chú task")
            saved = None
        if saved is not None:
            self.transcripts.append_html(self._key, notice_html(f"<b>Ted:</b> {escape(tr('untangle_notes_saved'))}", "success"))

    def _on_create_next_task(self) -> None:
        if self._critique is None or not self._critique.next_step:
            return
        title = self._critique.next_step.splitlines()[0].strip()
        try:
            self.focus_engine.add_task(title)
        except Exception:
            logger.exception("Gỡ Rối: không tạo được task bước tiếp")
            return
        self.transcripts.append_html(self._key, notice_html(
            f"<b>Ted:</b> {escape(tr('untangle_next_task_created', title=title))}", "success"))

