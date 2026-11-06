import asyncio
import logging

from src.bridge.openai_client import OpenAIRequestRejectedError, OpenAIUnavailableError
from src.bridge.openai_client_pool import openai_client_pool
from src.core.models import db

logger = logging.getLogger("ted")

# Backward compatibility alias
hermes_client_pool = openai_client_pool


class OpenAISyncWorker:
    """
    Đồng bộ các phiên tập trung (Focus Sessions) hoàn thành lúc Offline lên bộ nhớ dài hạn
    của Não AI (kết nối của module work) khi mạng hoặc máy chủ khả dụng trở lại.
    """

    async def sync_completed_sessions(self) -> int:
        unsynced = db.get_unsynced_sessions()
        if not unsynced:
            return 0

        pool = hermes_client_pool if hermes_client_pool is not openai_client_pool else openai_client_pool
        client = pool.for_module("work")
        if client is None:
            return 0

        synced_count = 0
        for session in unsynced:
            summary_msg = (
                f"[SYNC_EVENT] Người dùng vừa hoàn thành phiên tập trung '{session.intent_statement}' "
                f"trong {session.actual_minutes}/{session.planned_minutes} phút "
                f"(số lần xao nhãng: {session.distraction_count}, đánh giá: {session.focus_rating}/5). "
                f"Hãy ghi nhận ngắn gọn vào ngữ cảnh làm việc hôm nay."
            )
            try:
                await client.complete_text([{"role": "user", "content": summary_msg}], timeout=25.0)
            except (OpenAIUnavailableError, OpenAIRequestRejectedError) as exc:
                logger.info("Dừng đồng bộ phiên tập trung: %s", exc)
                break
            db.mark_session_synced(session.id)
            synced_count += 1
            await asyncio.sleep(0.2)
        return synced_count


sync_worker = OpenAISyncWorker()

# Backward compatibility alias
HermesSyncWorker = OpenAISyncWorker
