"""Quét bảng coach (Attempt / AgendaDone / WritingSubmission) → sự kiện XP. Idempotent nhờ dedupe_key."""

from datetime import datetime
from typing import Callable

from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from src.engines.coach.coach_data_models import AgendaDone, Attempt, WritingSubmission
from src.core.gamification.xp_ledger_repository import XpLedgerRepository


def scan_attempts(engine: Engine, ledger: XpLedgerRepository, since: datetime, module_engine_of: Callable[[str], str]) -> int:
    """quiz_answered (key attempt:<id>) + quiz_correct (key attempt_ok:<id>). `since` nên lùi 7 ngày để bắt
    trường hợp chấm lại "Mình đúng mà" làm correct đổi sang True sau khi đã quét."""
    with Session(engine) as s:
        rows = s.exec(select(Attempt).where(Attempt.answered_at >= since)).all()
    created = 0
    for a in rows:
        if module_engine_of(a.module_id) != "coach":
            continue
        meta = {"module": a.module_id}
        created += ledger.add(f"attempt:{a.id}", a.answered_at, a.module_id, "coach", "quiz_answered", meta) is not None
        if a.correct:
            created += ledger.add(f"attempt_ok:{a.id}", a.answered_at, a.module_id, "coach", "quiz_correct", meta) is not None
    return created


def scan_agenda(engine: Engine, ledger: XpLedgerRepository, since: datetime, module_engine_of: Callable[[str], str]) -> int:
    with Session(engine) as s:
        rows = s.exec(select(AgendaDone).where(AgendaDone.done_at >= since)).all()
    return sum(
        ledger.add(f"agenda:{r.module_id}:{r.agenda_id}", r.done_at, r.module_id, "coach", "agenda_done") is not None
        for r in rows if module_engine_of(r.module_id) == "coach")


def scan_writing(engine: Engine, ledger: XpLedgerRepository, since: datetime, module_engine_of: Callable[[str], str]) -> int:
    """Bài viết chấm xong (result_json != ""). `since` lùi 7 ngày vì bài có thể chấm muộn sau lúc nộp."""
    with Session(engine) as s:
        rows = s.exec(select(WritingSubmission).where(
            WritingSubmission.created_at >= since, WritingSubmission.result_json != "")).all()
    return sum(
        ledger.add(f"writing:{r.id}", r.created_at, r.module_id, "coach", "writing_graded") is not None
        for r in rows if module_engine_of(r.module_id) == "coach")
