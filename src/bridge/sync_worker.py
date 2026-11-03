import asyncio
import logging

from src.bridge.hermes_client import HermesRequestRejectedError, HermesUnavailableError
from src.bridge.hermes_client_pool import hermes_client_pool
from src.core.models import db

logger = logging.getLogger("ted")


class HermesSyncWorker:
    """
    Đồng bộ các phiên tập trung (Focus Sessions) hoàn thành lúc Offline lên bộ nhớ dài hạn
    của Hermes Agent (kết nối của module work) khi mạng hoặc VPS khả dụng trở lại.
    """

    async def sync_completed_sessions(self) -> int:
        unsynced = db.get_unsynced_sessions()
        if not unsynced:
            return 0

        client = hermes_client_pool.for_module("work")
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
            except (HermesUnavailableError, HermesRequestRejectedError) as exc:
                logger.info("Dừng đồng bộ phiên tập trung: %s", exc)
                break
            db.mark_session_synced(session.id)
            synced_count += 1
            await asyncio.sleep(0.2)
        return synced_count


sync_worker = HermesSyncWorker()
