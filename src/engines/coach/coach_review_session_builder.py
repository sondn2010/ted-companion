"""Chọn câu cho 1 phiên ôn: ưu tiên topic yêu cầu, thiếu thì bù câu đến hạn của topic khác."""

from typing import Optional

from src.engines.coach.coach_data_models import QuizItem
from src.engines.coach.coach_module_services import CoachModuleServices

REVIEW_SCHEDULER_LIMIT = 3
REVIEW_NOW_LIMIT = 20


def quiz_limit_for_agenda(minutes: Optional[int]) -> int:
    return max(REVIEW_SCHEDULER_LIMIT, (minutes or 0) // 2)


def build_session_items(
    services: CoachModuleServices, limit: int, topic: Optional[str] = None, respect_new_cap: bool = False,
) -> list[QuizItem]:
    """respect_new_cap=True (scheduler tự nhắc) giữ hạn mức câu mới/ngày; người dùng chủ động thì bỏ qua."""
    now = services.now()
    new_cap = services.policy().new_per_day if respect_new_cap else limit
    picked = services.items.select_for_review(services.module_id, now, limit, new_cap, services.day_start(), topic)
    if topic and len(picked) < limit:
        seen = {item.id for item in picked}
        others = services.items.select_for_review(
            services.module_id, now, limit - len(picked), 0, services.day_start(), None)
        picked.extend(item for item in others if item.id not in seen and item.topic != topic)
    return picked[:limit]
