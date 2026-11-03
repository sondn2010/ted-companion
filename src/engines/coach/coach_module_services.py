"""Gói dependency dùng chung của 1 module coach (repo, tz, đồng hồ, client) để scheduler/launcher/tab không phải
nhận từng tham số rời. Không chứa logic nghiệp vụ nặng — chỉ truy cập tiện lợi + hook "dữ liệu đã đổi"."""

import logging
from datetime import date, datetime, timedelta, tzinfo
from typing import Any, Callable, Optional

from src.engines.coach.coach_attempt_repository import CoachAttemptRepository
from src.engines.coach.coach_item_repository import CoachItemRepository
from src.engines.coach.coach_local_day import day_bounds_utc, local_date
from src.engines.coach.coach_plan_snapshot_repository import CoachPlanRepository
from src.engines.coach.coach_progress_report_outbox import ProgressReportOutboxRepository
from src.engines.coach.coach_sync_plan_schemas import Policy

logger = logging.getLogger("ted")


def local_tz() -> tzinfo:
    """Múi giờ của máy (aware). Hàm coach_local_day chỉ cần tzinfo, không bắt buộc ZoneInfo."""
    return datetime.now().astimezone().tzinfo


class CoachModuleServices:
    def __init__(
        self, manifest, ctx, db_engine, tz: Optional[tzinfo] = None,
        clock: Optional[Callable[[], datetime]] = None,
    ):
        self.manifest = manifest
        self.ctx = ctx
        self.tz = tz or local_tz()
        self._clock = clock
        self.items = CoachItemRepository(db_engine)
        self.attempts = CoachAttemptRepository(db_engine)
        self.plans = CoachPlanRepository(db_engine)
        self.outbox = ProgressReportOutboxRepository(db_engine)
        self.db_engine = db_engine
        self.on_changed: Callable[[], None] = lambda: None   # engine gắn: làm tươi tab khi dữ liệu đổi
        self.request_sync: Callable[[], None] = lambda: None  # engine gắn: kích hoạt [TED_SYNC_PLAN] (có phản hồi bong bóng)
        self.start_onboarding: Callable[[], None] = lambda: None  # engine gắn: mở chat [TED_ONBOARDING]

    @property
    def module_id(self) -> str:
        return self.manifest.id

    @property
    def learner_id(self) -> Optional[str]:
        return self.manifest.learner_id

    def now(self) -> datetime:
        """Giờ địa phương (aware)."""
        return self._clock() if self._clock else datetime.now(self.tz)

    def today(self) -> date:
        return self.now().date()

    def day_start(self) -> datetime:
        return day_bounds_utc(self.today(), self.tz)[0]

    def policy(self) -> Policy:
        return self.plans.current_policy(self.module_id)

    def client(self) -> Any:
        pool = self.ctx.client_pool
        return pool.for_module(self.module_id) if pool is not None else None

    def focus_state(self) -> str:
        return self.ctx.focus_engine.state

    def mark_done(self, agenda_id: str) -> None:
        """Idempotent; luôn báo "đã đổi" để tab vẽ lại."""
        self.plans.mark_done(self.module_id, agenda_id, self.now())
        self.on_changed()

    def unmark_done(self, agenda_id: str) -> None:
        """Bỏ tick checklist (chỉ khi chưa báo Hermes); luôn báo "đã đổi" để tab vẽ lại."""
        self.plans.unmark_done(self.module_id, agenda_id)
        self.on_changed()

    def plan_is_today(self) -> bool:
        """Snapshot được sync trong ngày địa phương hiện tại (kế hoạch hôm qua → False)."""
        synced = self.plans.get_synced_at(self.module_id)
        return synced is not None and local_date(synced, self.tz) == self.today()

    def attempts_today(self) -> int:
        start, end = day_bounds_utc(self.today(), self.tz)
        return len(self.attempts.attempts_between(self.module_id, start, end))

    def new_available(self, policy: Policy) -> int:
        """Số câu mới còn được đẩy hôm nay = min(chưa hỏi, new_per_day còn lại)."""
        room = max(0, policy.new_per_day - self.items.new_seen_count(self.module_id, self.day_start()))
        return min(room, self.items.unseen_count(self.module_id))

    # ---- cờ "cần onboarding" (Hermes báo needs_onboarding; xoá khi sync có kế hoạch) ----
    def needs_onboarding(self) -> bool:
        return self.ctx.kv.get(f"coach.{self.module_id}.needs_onboarding") == "1"

    def set_needs_onboarding(self, on: bool) -> None:
        self.ctx.kv.set(f"coach.{self.module_id}.needs_onboarding", "1" if on else "0")

    # ---- snooze / bỏ qua hôm nay (KV, dùng chung cho scheduler và nhắc agenda) ----
    def snooze_until(self) -> Optional[datetime]:
        raw = self.ctx.kv.get(f"coach.{self.module_id}.snooze_until")
        try:
            return datetime.fromisoformat(raw) if raw else None
        except ValueError:
            return None   # giá trị hỏng → coi như không snooze

    def skip_date(self) -> Optional[date]:
        raw = self.ctx.kv.get(f"coach.{self.module_id}.skip_date")
        try:
            return date.fromisoformat(raw) if raw else None
        except ValueError:
            return None

    def snooze(self, minutes: int) -> None:
        self.ctx.kv.set(f"coach.{self.module_id}.snooze_until", (self.now() + timedelta(minutes=minutes)).isoformat())

    def skip_today(self) -> None:
        self.ctx.kv.set(f"coach.{self.module_id}.skip_date", self.today().isoformat())
