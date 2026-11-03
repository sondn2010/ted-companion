"""Kho PlanSnapshot (bản sync gần nhất), AgendaDone, WritingSubmission."""

import logging
from datetime import datetime
from typing import Iterable, Optional

from pydantic import ValidationError
from sqlmodel import col, select

from src.engines.coach.coach_data_models import AgendaDone, PlanSnapshot, WritingSubmission, open_session
from src.engines.coach.coach_policy_clamp import DEFAULT_POLICY, apply_policy
from src.engines.coach.coach_quiz_writing_report_schemas import WritingGradeResult
from src.engines.coach.coach_sync_plan_schemas import Policy, SyncPlanPayload
from src.engines.coach.utc_aware_datetime_type import require_aware

logger = logging.getLogger("ted")


class CoachPlanRepository:
    def __init__(self, engine):
        self.engine = engine

    # ---- snapshot ----
    def get_snapshot(self, module_id: str) -> Optional[SyncPlanPayload]:
        """Bản sync gần nhất; chưa có hoặc hỏng → None (bên gọi dùng mặc định / offline)."""
        with open_session(self.engine) as session:
            row = session.get(PlanSnapshot, module_id)
        if row is None:
            return None
        try:
            return SyncPlanPayload.model_validate_json(row.payload_json)
        except ValidationError:
            logger.warning("PlanSnapshot của %s hỏng, bỏ qua", module_id)
            return None

    def get_synced_at(self, module_id: str) -> Optional[datetime]:
        with open_session(self.engine) as session:
            row = session.get(PlanSnapshot, module_id)
            return row.synced_at if row else None

    def current_policy(self, module_id: str) -> Policy:
        snapshot = self.get_snapshot(module_id)
        return snapshot.policy if snapshot and snapshot.policy else DEFAULT_POLICY

    def save_sync(
        self, module_id: str, payload: SyncPlanPayload, now: datetime, reported_ids: Iterable[str] = (),
    ) -> SyncPlanPayload:
        """Thay snapshot bằng bản sync mới và đánh dấu `reported_ids` đã báo — trong 1 giao dịch.
        Policy được kẹp/giữ cũ qua apply_policy. Chỉ các id THỰC SỰ đã gửi trong request mới được đánh dấu,
        nên việc tick hoàn thành trong lúc sync đang bay không bị mất (Red Team #8)."""
        require_aware(now)
        effective = payload.model_copy(update={"policy": apply_policy(self.current_policy(module_id), payload.policy)})
        body = effective.model_dump_json()
        with open_session(self.engine) as session:
            row = session.get(PlanSnapshot, module_id)
            if row is None:
                row = PlanSnapshot(module_id=module_id, synced_at=now, payload_json=body)
            else:
                row.synced_at, row.payload_json = now, body
            session.add(row)
            for agenda_id in set(reported_ids):
                done = session.get(AgendaDone, (module_id, agenda_id))
                if done is not None:
                    done.reported_in_sync = True
                    session.add(done)
            session.commit()
        return effective

    # ---- agenda done ----
    def mark_done(self, module_id: str, agenda_id: str, now: datetime) -> bool:
        """Lần đầu → True. Đã có và CHƯA báo → giữ nguyên, False. Đã có và đã báo Hermes (id dùng lại ở kế hoạch
        mới) → làm lại: done_at = now, chờ báo lần nữa, True."""
        require_aware(now)
        with open_session(self.engine) as session:
            row = session.get(AgendaDone, (module_id, agenda_id))
            if row is None:
                session.add(AgendaDone(module_id=module_id, agenda_id=agenda_id, done_at=now))
            elif row.reported_in_sync:
                row.done_at, row.reported_in_sync = now, False
                session.add(row)
            else:
                return False
            session.commit()
            return True

    def unmark_done(self, module_id: str, agenda_id: str) -> bool:
        """Bỏ tick — chỉ khi chưa báo Hermes (đã báo thì Hermes là nguồn đúng). True nếu đã xoá."""
        with open_session(self.engine) as session:
            row = session.get(AgendaDone, (module_id, agenda_id))
            if row is None or row.reported_in_sync:
                return False
            session.delete(row)
            session.commit()
            return True

    def done_ids(self, module_id: str) -> set[str]:
        """Việc xong THUỘC kế hoạch hiện tại: chưa báo Hermes, hoặc xong sau lần sync gần nhất. Dòng đã báo từ
        kế hoạch cũ bị bỏ qua → id dùng lại ("a1") không hiện ✓ vĩnh viễn, và trạng thái Hermes thắng sau khi báo."""
        with open_session(self.engine) as session:
            snapshot = session.get(PlanSnapshot, module_id)
            rows = session.exec(select(AgendaDone).where(AgendaDone.module_id == module_id)).all()
        return {r.agenda_id for r in rows
                if not r.reported_in_sync or snapshot is None or r.done_at >= snapshot.synced_at}

    def unreported_done_ids(self, module_id: str) -> list[str]:
        """Việc xong kể từ lần sync thành công gần nhất (→ `done_today` của [TED_SYNC_PLAN])."""
        with open_session(self.engine) as session:
            stmt = select(AgendaDone.agenda_id).where(
                AgendaDone.module_id == module_id, AgendaDone.reported_in_sync == False,  # noqa: E712
            ).order_by(AgendaDone.done_at)
            return list(session.exec(stmt).all())

    # ---- bài viết ----
    def add_writing_submission(
        self, module_id: str, prompt: str, text: str, now: datetime, agenda_id: str = "", topic: str = "",
    ) -> WritingSubmission:
        with open_session(self.engine) as session:
            row = WritingSubmission(module_id=module_id, agenda_id=agenda_id, topic=topic, prompt=prompt,
                                    text=text, created_at=require_aware(now))
            session.add(row)
            session.commit()
            return row

    def save_writing_result(self, submission_id: str, result: WritingGradeResult) -> bool:
        with open_session(self.engine) as session:
            row = session.get(WritingSubmission, submission_id)
            if row is None:
                return False
            row.result_json = result.model_dump_json()
            session.add(row)
            session.commit()
            return True

    def get_writing_submission(self, submission_id: str) -> Optional[WritingSubmission]:
        with open_session(self.engine) as session:
            return session.get(WritingSubmission, submission_id)

    def ungraded_submissions(self, module_id: str) -> list[WritingSubmission]:
        with open_session(self.engine) as session:
            stmt = select(WritingSubmission).where(WritingSubmission.module_id == module_id,
                                                   WritingSubmission.result_json == "").order_by(WritingSubmission.created_at)
            return list(session.exec(stmt).all())

    def recent_submissions(self, module_id: str, limit: int = 20) -> list[WritingSubmission]:
        """Lịch sử bài viết, mới nhất trước."""
        with open_session(self.engine) as session:
            stmt = select(WritingSubmission).where(WritingSubmission.module_id == module_id)                 .order_by(col(WritingSubmission.created_at).desc()).limit(limit)
            return list(session.exec(stmt).all())
