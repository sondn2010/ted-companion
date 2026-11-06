"""Nộp bài viết: LƯU TRƯỚC khi gọi mạng (không mất bài khi offline), chấm qua [TED_WRITING_SUBMISSION], chấm lại được."""

import logging
from dataclasses import dataclass
from typing import Optional

from src.bridge.openai_json_contract_request import request_openai_json_contract as request_json
from src.engines.coach.coach_module_services import CoachModuleServices
from src.engines.coach.coach_quiz_writing_report_schemas import WritingGradeResult
from src.engines.coach.coach_request_envelope import envelope

logger = logging.getLogger("ted")

WRITING_TIMEOUT_SECS = 90.0


@dataclass(frozen=True)
class WritingOutcome:
    submission_id: str
    result: Optional[WritingGradeResult]   # None = chưa chấm được (đã lưu, bấm "Chấm lại")


class WritingSubmissionService:
    def __init__(self, services: CoachModuleServices):
        self._s = services

    async def submit(
        self, prompt: str, text: str, minutes_spent: int, agenda_id: str = "", topic: str = "",
    ) -> WritingOutcome:
        row = self._s.plans.add_writing_submission(
            self._s.module_id, prompt, text, self._s.now(), agenda_id=agenda_id, topic=topic)
        return await self._grade(row.id, minutes_spent)

    async def regrade(self, submission_id: str, minutes_spent: int = 0) -> WritingOutcome:
        return await self._grade(submission_id, minutes_spent)

    async def _grade(self, submission_id: str, minutes_spent: int) -> WritingOutcome:
        row = self._s.plans.get_writing_submission(submission_id)
        if row is None:
            raise LookupError(f"Không có bài viết {submission_id}")
        client = self._s.client()
        if client is None:
            return WritingOutcome(submission_id, None)
        payload = {
            "learner": self._s.learner_id, "agenda_id": row.agenda_id, "topic": row.topic,
            "prompt": row.prompt, "text": row.text, "minutes_spent": max(0, minutes_spent),
        }
        try:
            result = await request_json(
                client, envelope("TED_WRITING_SUBMISSION", payload), WritingGradeResult, timeout=WRITING_TIMEOUT_SECS)
        except Exception:
            logger.exception("Chấm bài viết lỗi (module=%s)", self._s.module_id)
            result = None
        if result is not None:
            self._s.plans.save_writing_result(submission_id, result)
        return WritingOutcome(submission_id, result)
