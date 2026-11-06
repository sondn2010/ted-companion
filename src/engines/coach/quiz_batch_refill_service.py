"""Bổ sung câu hỏi từ Hermes khi kho câu chưa hỏi sắp hết; mỗi (module, topic, types) tối đa 1 yêu cầu đang bay."""

import logging
from datetime import datetime
from typing import Optional, Protocol, Sequence

from src.bridge.openai_client import OpenAIBrainClient as HermesBrainClient
from src.bridge.openai_json_contract_request import request_openai_json_contract as request_json
from src.engines.coach.coach_item_repository import CoachItemRepository
from src.engines.coach.coach_quiz_writing_report_schemas import QuizBatchResponse
from src.engines.coach.coach_request_envelope import envelope

logger = logging.getLogger("ted")

RECENT_QUESTIONS_SENT = 20
THRESHOLD_ANY_TOPIC = 5
THRESHOLD_SINGLE_TOPIC = 3
THRESHOLD_TYPED = 1          # việc `step` trong agenda: cần ít nhất 1 câu dạng đó

_in_flight: set[tuple] = set()


class CoachModuleLike(Protocol):
    id: str
    learner_id: Optional[str]


async def refill_if_needed(
    module: CoachModuleLike, repo: CoachItemRepository, client: HermesBrainClient, now: datetime,
    topic: Optional[str] = None, types: Optional[Sequence[str]] = None, count: int = 10,
) -> int:
    """Trả về số câu mới đã chèn (0 nếu đủ câu, đang có yêu cầu bay, offline hoặc Hermes trả rác)."""
    key = (module.id, topic, tuple(types) if types else None)
    threshold = THRESHOLD_TYPED if types else THRESHOLD_SINGLE_TOPIC if topic else THRESHOLD_ANY_TOPIC
    if key in _in_flight or repo.unseen_count(module.id, topic, types) >= threshold:
        return 0
    _in_flight.add(key)   # đồng bộ với bước kiểm tra phía trên (không có await ở giữa) → không đua
    try:
        request = {
            "learner": module.learner_id, "count": count, "topic": topic,
            "types": list(types) if types else None,
            "recent_questions": repo.recent_questions(module.id, RECENT_QUESTIONS_SENT),
        }
        batch = await request_json(client, envelope("TED_QUIZ_BATCH_REQUEST", request), QuizBatchResponse)
        if batch is None:
            return 0
        return repo.insert_items_dedup(module.id, batch.items, now)
    except Exception:
        logger.exception("Refill câu hỏi lỗi (module=%s, topic=%s)", module.id, topic)
        return 0
    finally:
        _in_flight.discard(key)
