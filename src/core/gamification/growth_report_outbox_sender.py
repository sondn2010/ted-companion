"""Outbox báo cáo tăng trưởng gửi Hermes: đóng băng ngày/tuần đã qua, gửi cũ → mới, offline lùi lịch không tốn lượt.

Dùng lại bảng ProgressReportOutbox của coach với khóa module_id = "growth.daily@<conn>" / "growth.weekly@<conn>"
(truy vấn của coach lọc theo module_id riêng nên không đụng nhau). Mỗi kết nối Hermes nhận đúng 1 bản:
- kết nối có module work (profile Work / hermes_profile_ted) → báo cáo `general`;
- kết nối chỉ có module coach → báo cáo `learning` (chỉ học tập, không số liệu công việc/sức khỏe).
"""

import json
import logging
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Dict, FrozenSet, List, Optional

from src.bridge.openai_json_contract_request import request_openai_json_contract as request_json
from src.bridge.openai_offline_probe_and_backoff import OfflineBackoff, OfflineProbe
from src.core.gamification.growth_report_aggregation import (
    GrowthSources, collect_day, collect_week, is_active, learning_badge_ids)
from src.core.gamification.growth_report_contract_schemas import ProgressReportSavedReply
from src.core.gamification.growth_report_payload_builder import (
    GENERAL, LEARNING, build_daily_payload, build_weekly_payload)
from src.core.gamification.learner_scope_ledger_and_badges import LearnerScope, ScopedXpLedger
from src.core.gamification.level_progression_engine import week_start_of
from src.engines.coach.coach_data_models import ProgressReportOutbox
from src.engines.coach.coach_progress_report_outbox import ProgressReportOutboxRepository
from src.engines.coach.coach_request_envelope import envelope

logger = logging.getLogger("ted")

TAG = "TED_GROWTH_REPORT"
BACKFILL_DAYS = 7
BACKFILL_WEEKS = 4
FAILED_PERMANENTLY = "failed_permanently"
GENERAL_LEARNER = "user"


@dataclass(frozen=True)
class GrowthTarget:
    conn_id: str
    report_kind: str   # learning | general
    learner: str
    modules: FrozenSet[str] = frozenset()   # module coach của learner này (chỉ dùng cho báo cáo learning)
    include_meetings: bool = False          # phiên họp không gắn module → chỉ đưa vào khi chỉ có 1 learner

    @property
    def daily_key(self) -> str:
        return f"growth.daily@{self.conn_id}"

    @property
    def weekly_key(self) -> str:
        return f"growth.weekly@{self.conn_id}"


class GrowthReportOutboxSender:
    def __init__(self, sources: GrowthSources, registry: Any, client_pool: Any,
                 now: Optional[Callable[[], datetime]] = None, local_today: Optional[Callable[[], date]] = None):
        self._src, self._registry, self._pool = sources, registry, client_pool
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._today = local_today or date.today
        self._learn = learning_badge_ids()
        ProgressReportOutbox.__table__.create(sources.engine, checkfirst=True)
        self.outbox = ProgressReportOutboxRepository(sources.engine)
        self._backoff: Dict[str, OfflineBackoff] = {}
        self._running = False

    def targets(self) -> List[GrowthTarget]:
        """Gom module đang bật theo kết nối Hermes; kết nối không phân giải được (None) bị bỏ qua."""
        groups: Dict[str, list] = {}
        for manifest in self._registry.enabled():
            conn = self._pool.connection_id_for_module(manifest.id)
            if conn:
                groups.setdefault(conn, []).append(manifest)
        out = []
        for conn, manifests in groups.items():
            if any(m.engine == "work" for m in manifests):
                out.append(GrowthTarget(conn, GENERAL, GENERAL_LEARNER))
                continue
            learner = next((m.learner_id for m in manifests if getattr(m, "learner_id", None)), None)
            if learner:
                coach_ids = frozenset(m.id for m in manifests if m.engine == "coach")
                out.append(GrowthTarget(conn, LEARNING, learner, coach_ids))
        learners = [t for t in out if t.report_kind == LEARNING]
        if len(learners) == 1:
            out = [replace(t, include_meetings=True) if t.report_kind == LEARNING else t for t in out]
        return out

    def _sources_for(self, target: GrowthTarget) -> GrowthSources:
        """Báo cáo learning đọc qua sổ cái giới hạn theo module của learner (H1: không lẫn dữ liệu giữa các con)."""
        if target.report_kind != LEARNING:
            return self._src
        scope = LearnerScope(target.modules, target.include_meetings)
        return replace(self._src, ledger=ScopedXpLedger(self._src.engine, scope))

    def enqueue_missing(self) -> int:
        """Ngày đã qua (≤7, không gồm hôm nay) + tuần đã kết thúc (≤4) có hoạt động mà chưa có dòng → đóng băng."""
        today, now, added = self._today(), self._now(), 0
        targets = self.targets()
        if not targets:
            return 0
        days: Dict[Any, Any] = {}
        weeks: Dict[Any, Any] = {}
        for target in targets:
            learning = target.report_kind == LEARNING
            src = self._sources_for(target)
            # general dùng chung 1 phép gom; learning gom riêng theo learner (khóa theo kết nối)
            ck = target.conn_id if learning else None
            for back in range(1, BACKFILL_DAYS + 1):
                day = today - timedelta(days=back)
                if self.outbox.get(target.daily_key, day.isoformat()) is not None:
                    continue
                agg = days.setdefault((ck, day), collect_day(src, day, self._learn))
                if is_active(agg.signals, agg.coach_xp, learning):
                    payload = build_daily_payload(target.report_kind, target.learner, agg)
                    added += self.outbox.upsert_report(target.daily_key, day.isoformat(), payload, now)
            this_week = week_start_of(today)
            for k in range(1, BACKFILL_WEEKS + 1):
                week = this_week - timedelta(weeks=k)
                if self.outbox.get(target.weekly_key, week.isoformat()) is not None:
                    continue
                agg = weeks.setdefault((ck, week), collect_week(src, week, self._learn))
                if agg.coach_xp and learning or any(is_active(s, 0, learning) for s in agg.ctx.days):
                    payload = build_weekly_payload(target.report_kind, target.learner, agg)
                    added += self.outbox.upsert_report(target.weekly_key, week.isoformat(), payload, now)
        return added

    async def flush(self) -> int:
        """Mỗi target: ngày cũ → mới rồi tuần; offline → lùi lịch (không tốn lượt) và dừng target đó;
        lỗi hợp đồng → attempts+1, chạm max → failed_permanently và đi tiếp. Trả số báo cáo đã gửi."""
        sent = 0
        for target in self.targets():
            backoff = self._backoff.setdefault(target.conn_id, OfflineBackoff())
            client = self._pool.get(target.conn_id)
            if client is None or backoff.blocked(self._now()):
                continue
            for key in (target.daily_key, target.weekly_key):
                done, offline = await self._flush_key(client, backoff, key)
                sent += done
                if offline:
                    break
        return sent

    async def _flush_key(self, client: Any, backoff: OfflineBackoff, key: str):
        sent = 0
        for row in self.outbox.pending_reports(key):
            probe = OfflineProbe(client)
            try:
                reply = await request_json(probe, envelope(TAG, json.loads(row.payload_json)), ProgressReportSavedReply)
            except Exception:  # noqa: BLE001 - outbox không được làm hỏng luồng nền
                logger.exception("Gửi báo cáo tăng trưởng %s/%s lỗi bất ngờ", key, row.date)
                reply = None
            if reply is not None and reply.saved:
                self.outbox.mark_sent(key, row.date, self._now())
                sent += 1
                backoff.reset()
                continue
            if probe.offline:   # mất mạng KHÔNG tốn lượt thử (tránh failed_permanently = mất dữ liệu)
                backoff.on_offline(self._now())
                return sent, True
            error = "không có phản hồi" if reply is None else (reply.error or "saved=false")
            if self.outbox.mark_failed(key, row.date, error, self._now()) != FAILED_PERMANENTLY:
                break
        return sent, False

    async def run_cycle(self) -> int:
        if self._running:   # chống chạy chồng (timer + startup)
            return 0
        self._running = True
        try:
            self.enqueue_missing()
            return await self.flush()
        finally:
            self._running = False
