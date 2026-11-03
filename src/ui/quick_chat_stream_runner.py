"""Stream 1 câu trả lời Hermes vào khung chat của QuickChatPopup (tách khỏi popup, hành vi không đổi)."""

import asyncio
import logging
import re

from shiboken6 import isValid

from src.bridge.chat_json_tail_detector import ChatJsonTailDetector
from src.core.i18n import i18n, tr
from src.core.offline_guide_engine import get_offline_starter_menu, match_offline_guide
from src.ui.quick_chat_message_html import notice_html

logger = logging.getLogger("ted")

NO_CONNECTION_HTML = notice_html(
    "<b>Ted:</b> Chưa cấu hình kết nối Não AI cho module này — vào Cài đặt → Module để chọn kết nối nhé."
)


async def stream_reply_into_popup(popup, user_text: str, client, module_id: str) -> None:
    """Luôn nhả khoá `_in_flight` + trả nút ⏹ Dừng về Gửi khi kết thúc (kể cả lỗi/bị dừng)."""
    detector = ChatJsonTailDetector()   # ẩn khối <json> cuối câu trả lời khỏi khung chat
    full_reply = ""
    from src.core.tts_service import tts_service
    tts_service.stop()   # câu hỏi mới: im ngay câu trả lời cũ, chỉ đọc câu trả lời mới

    def show(text: str):
        nonlocal full_reply
        if not text or not isValid(popup):   # popup có thể đã bị huỷ khi app thoát (Red Team #3)
            return
        full_reply += text
        popup.transcripts.insert_text(module_id, text)   # ghi vào đúng hội thoại của module, kể cả khi đang ẩn

    try:
        if client is None:   # module chưa có kết nối: trả lời bằng tri thức ngoại tuyến
            if isValid(popup):
                lang = getattr(i18n, "current_language", "vi")
                matched = match_offline_guide(user_text, lang=lang)
                if matched:
                    _, answer = matched
                    if module_id != "work":
                        popup.transcripts.append_html(module_id, NO_CONNECTION_HTML)
                    popup.transcripts.append_html(module_id, notice_html(answer, "info"))
                    full_reply = re.sub(r"<[^>]+>", "", answer)
                else:
                    menu = get_offline_starter_menu(lang)
                    if module_id != "work":
                        popup.transcripts.append_html(module_id, NO_CONNECTION_HTML + notice_html(menu, "info"))
                    else:
                        popup.transcripts.append_html(module_id, notice_html(menu, "info"))
                    full_reply = re.sub(r"<[^>]+>", "", menu)

                from src.config import settings
                if getattr(settings, "tts_enabled", False) and full_reply:
                    try:
                        from src.core.background_task_spawner import spawn_background_task
                        spawn_background_task(tts_service.speak(full_reply), "quick-chat-tts-reply")
                    except Exception:
                        pass
            return

        await client.stream_chat(
            user_message=user_text,
            current_context=popup.focus_engine.get_context_snapshot(),
            on_mood_change=popup.focus_engine.set_mood,
            on_token=lambda token: show(detector.feed(token)),
            persona=popup._persona_for(module_id),
            resume_mood=popup.focus_engine.current_mood,
        )
        leftover, data = detector.finish()
        if leftover:
            show(leftover)
        if isValid(popup):   # công thức / bảng / hình vẽ: dựng lại sau khi stream xong
            try:
                popup.transcripts.render_streamed_reply(module_id, full_reply)
            except Exception:
                logger.exception("Không dựng được nội dung giàu định dạng cho câu trả lời")

        try:
            from src.core.chat_session_manager import chat_session_manager
            chat_session_manager.record_turn(module_id, user_text, full_reply)
        except Exception:
            pass

        from src.config import settings
        if getattr(settings, "tts_enabled", False) and full_reply:
            try:
                from src.core.background_task_spawner import spawn_background_task
                spawn_background_task(tts_service.speak(full_reply), "quick-chat-tts-reply")
            except Exception:
                pass

        handler = popup._reply_json_handlers.get(module_id)
        if data is not None and handler is not None:
            try:
                handler(data)
            except Exception:
                logger.exception("Callback khối JSON của module %s lỗi", module_id)
    except asyncio.CancelledError:   # người dùng bấm ⏹ Dừng: giữ phần đã nhận, không ghi lượt hội thoại
        if isValid(popup):
            popup.transcripts.append_html(module_id, notice_html(f"<b>Ted:</b> {tr('bubble_reply_stopped')}", "info"))
        raise
    finally:
        popup._in_flight = False
        popup._stream_task = None
        if isValid(popup):
            popup.set_streaming_ui(False)
