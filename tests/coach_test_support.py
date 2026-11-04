"""Tiện ích dùng chung cho test coach: mốc thời gian aware, tạo câu hỏi, repo trên SQLite in-memory."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from src.engines.coach.coach_attempt_repository import CoachAttemptRepository
from src.engines.coach.coach_item_repository import CoachItemRepository
from src.engines.coach.coach_quiz_writing_report_schemas import GeneratedQuizItem

TZ = ZoneInfo("Asia/Ho_Chi_Minh")
NOW = datetime(2026, 10, 19, 5, 0, tzinfo=timezone.utc)   # 12:00 giờ VN
DAYS = [0.007, 1, 3, 7, 14, 30]
MODULE = "thcs"


def quiz(question: str, topic: str = "english.conditionals", type_: str = "short", answer: str = "x", **extra):
    fields = dict(topic=topic, type=type_, question=question, answer=answer)
    if type_ == "mcq":
        fields.update(choices=["A. one", "B. two", "C. three", "D. four"], answer="B")
    fields.update(extra)
    return GeneratedQuizItem(**fields)


def seed(engine, questions, module_id: str = MODULE, topic: str = "english.conditionals", now=NOW):
    """Chèn danh sách câu; trả về list QuizItem theo thứ tự đã chèn."""
    repo = CoachItemRepository(engine)
    repo.insert_items_dedup(module_id, [quiz(q, topic=topic) for q in questions], now)
    by_question = {i.question: i for i in repo.select_for_review(module_id, now, 500, 500, now)}
    return [by_question[q] for q in questions]


def repos(engine):
    return CoachItemRepository(engine), CoachAttemptRepository(engine)
