"""Gom dữ liệu từ repo rồi gọi hàm thuần của coach_stats_builder (Phase 07/08 chỉ cần gọi 2 hàm này)."""

from datetime import date, datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from src.engines.coach.coach_attempt_repository import CoachAttemptRepository
from src.engines.coach.coach_item_repository import CoachItemRepository
from src.engines.coach.coach_local_day import day_bounds_utc, local_date
from src.engines.coach.coach_stats_builder import build_progress_payload, build_sync_stats, streak_days
from src.engines.coach.utc_aware_datetime_type import require_aware


def _streak(attempts: CoachAttemptRepository, module_id: str, today: date, tz: ZoneInfo) -> int:
    return streak_days({local_date(t, tz) for t in attempts.attempt_times(module_id)}, today)


def collect_sync_stats(
    items: CoachItemRepository, attempts: CoachAttemptRepository, module_id: str, now: datetime, tz: ZoneInfo,
) -> dict:
    """`stats` của [TED_SYNC_PLAN]: 7 ngày địa phương gần nhất (gồm hôm nay)."""
    today = local_date(require_aware(now), tz)
    start, _ = day_bounds_utc(today - timedelta(days=6), tz)
    _, end = day_bounds_utc(today, tz)
    last7 = attempts.attempts_between(module_id, start, end)
    items_by_id = attempts.load_items({a.item_id for a in last7})
    return build_sync_stats(
        last7, items_by_id, items.due_count(module_id, now), items.unseen_count(module_id),
        _streak(attempts, module_id, today, tz),
    )


def collect_progress_payload(
    attempts: CoachAttemptRepository, module_id: str, learner: str, report_day: date, now: datetime, tz: ZoneInfo,
) -> Optional[dict]:
    """Payload [TED_PROGRESS_REPORT] cho 1 ngày địa phương; ngày không có lượt trả lời → None."""
    start, end = day_bounds_utc(report_day, tz)
    day_attempts = attempts.attempts_between(module_id, start, end)
    if not day_attempts:
        return None
    item_ids = {a.item_id for a in day_attempts}
    return build_progress_payload(
        report_day, learner, module_id, day_attempts, attempts.load_items(item_ids), attempts.load_states(item_ids),
        attempts.first_seen_item_ids(module_id, start, end), _streak(attempts, module_id, report_day, tz), start, end,
    )
