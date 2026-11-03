"""Thống kê thuần hàm: stats cho [TED_SYNC_PLAN] và payload [TED_PROGRESS_REPORT] (khớp skill mẫu)."""

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Iterable, Optional

from src.engines.coach.coach_data_models import Attempt, QuizItem, ReviewState

WEAK_MIN_ATTEMPTS = 2
WEAK_ACCURACY_BELOW = 0.6
WEAK_TOP = 5
MASTERED_BOX = 4


def subject_of(topic: str) -> str:
    """'hsk.hsk3-vocab' → 'hsk'; topic rỗng → 'general'."""
    return topic.split(".", 1)[0] or "general" if topic else "general"


def weak_topics(attempts: Iterable[Attempt], items_by_id: dict[str, QuizItem]) -> list[dict]:
    """Chủ đề ≥2 lượt và đúng <60%, tệ nhất trước, tối đa 5."""
    totals: dict[str, list[int]] = defaultdict(lambda: [0, 0])   # topic → [correct, total]
    for attempt in attempts:
        item = items_by_id.get(attempt.item_id)
        if item is None or not item.topic:
            continue
        totals[item.topic][1] += 1
        totals[item.topic][0] += int(attempt.correct)
    weak = [(t, c, n) for t, (c, n) in totals.items() if n >= WEAK_MIN_ATTEMPTS and c / n < WEAK_ACCURACY_BELOW]
    weak.sort(key=lambda row: (row[1] / row[2], -row[2], row[0]))
    return [{"topic": t, "correct": c, "total": n} for t, c, n in weak[:WEAK_TOP]]


def streak_days(active_days: set[date], today: date) -> int:
    """Số ngày liên tiếp có trả lời, tính lùi từ hôm nay (hôm nay chưa học thì tính từ hôm qua)."""
    cursor = today if today in active_days else today - timedelta(days=1)
    count = 0
    while cursor in active_days:
        count += 1
        cursor -= timedelta(days=1)
    return count


def build_sync_stats(
    last7_attempts: list[Attempt], items_by_id: dict[str, QuizItem], due_reviews: int, unseen_items: int, streak: int,
) -> dict:
    return {
        "last7_answered": len(last7_attempts),
        "last7_correct": sum(1 for a in last7_attempts if a.correct),
        "weak_topics": weak_topics(last7_attempts, items_by_id),
        "due_reviews": due_reviews,
        "unseen_items": unseen_items,
        "streak_days": streak,
    }


def _reached_mastery_in(state: Optional[ReviewState], start: datetime, end: datetime) -> bool:
    """Chạm hộp ≥4 trong khoảng: lần trả lời cuối nằm trong khoảng và trước đó chưa ở hộp ≥4."""
    if state is None or state.last_reviewed_at is None or state.box < MASTERED_BOX:
        return False
    return start <= state.last_reviewed_at < end and (state.prev_box is None or state.prev_box < MASTERED_BOX)


def build_progress_payload(
    report_date: date, learner: str, module_id: str, day_attempts: list[Attempt],
    items_by_id: dict[str, QuizItem], states_by_id: dict[str, ReviewState], first_seen_ids: set[str],
    streak: int, day_start: datetime, day_end: datetime,
) -> Optional[dict]:
    """Payload báo cáo của 1 ngày; không có lượt trả lời nào → None (không gửi báo cáo rỗng)."""
    known = [a for a in day_attempts if a.item_id in items_by_id]
    if not known:
        return None
    by_subject: dict[str, list[Attempt]] = defaultdict(list)
    for attempt in known:
        by_subject[subject_of(items_by_id[attempt.item_id].topic)].append(attempt)

    subjects = []
    for subject, attempts in sorted(by_subject.items()):
        item_ids = {a.item_id for a in attempts}
        subjects.append({
            "subject": subject,
            "answered": len(attempts),
            "correct": sum(1 for a in attempts if a.correct),
            "weak_topics": weak_topics(attempts, items_by_id),
            "new_items": len(item_ids & first_seen_ids),
            "mastered_items": sum(1 for i in item_ids if _reached_mastery_in(states_by_id.get(i), day_start, day_end)),
        })
    flagged_ids = dict.fromkeys(a.item_id for a in known if items_by_id[a.item_id].flagged)
    return {
        "date": report_date.isoformat(),
        "learner": learner,
        "module": module_id,
        "subjects": subjects,
        "flagged": [{"item_id": i, "question": items_by_id[i].question, "reason": items_by_id[i].flag_reason}
                    for i in flagged_ids],
        "study_minutes": round(sum(a.response_secs for a in known) / 60),
        "streak_days": streak,
    }
