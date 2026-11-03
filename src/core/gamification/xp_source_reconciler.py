"""Chuyển dữ kiện engine đã lưu DB thành sự kiện XP (không sửa engine nào). Quét lại bao nhiêu lần cũng không cộng đôi.

Quy ước đã chốt:
- Focus "hoàn thành" = focus_rating == 5 (đúng giá trị stop_session(completed=True) ghi; có test khoá).
- Task done→todo: ghi bù trừ task_undone:<id>:<n> (xp = −ròng); done lại: task_done:<id>:<n+1>.
  Chỉ thu hồi khi status todo/in_progress (archived/xoá giữ XP vì task từng hoàn thành).
- Ts sự kiện = thời điểm nguồn → local_date là ngày thật, không phải ngày quét.
- Lần chạy đầu chỉ backfill tuần hiện tại (không đổ lịch sử cũ vào XP).
"""

import logging
from datetime import datetime, time, timedelta, timezone
from typing import Callable

from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from src.core.app_state_key_value_store import KeyValueStore
from src.core.gamification.coach_xp_source_scans import scan_agenda, scan_attempts, scan_writing
from src.core.gamification.level_progression_engine import week_start_of
from src.core.gamification.xp_ledger_repository import XpLedgerRepository
from src.core.models import FocusSession, Task

logger = logging.getLogger("ted")

KV_CURSOR = "gamify.reconcile_since"
OVERLAP = timedelta(minutes=10)
LOOKBACK_COACH = timedelta(days=7)
COMPLETED_FOCUS_RATING = 5
REVOCABLE_STATUSES = ("todo", "in_progress")


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def week_floor_utc(now: datetime) -> datetime:
    """00:00 Thứ Hai tuần hiện tại (giờ máy) → UTC."""
    monday = week_start_of(now.astimezone().date())
    return datetime.combine(monday, time.min).astimezone(timezone.utc)


class XpSourceReconciler:
    def __init__(self, engine: Engine, ledger: XpLedgerRepository, kv: KeyValueStore,
                 module_engine_of: Callable[[str], str]):
        self._engine, self._ledger, self._kv = engine, ledger, kv
        self._module_engine_of = module_engine_of

    def _window(self, now: datetime):
        """(since, since_coach): since cho nguồn có mốc thời gian chính xác, since_coach lùi 7 ngày cho chấm muộn."""
        raw, floor = self._kv.get(KV_CURSOR), week_floor_utc(now)
        try:
            cursor = _aware(datetime.fromisoformat(raw)) if raw else None
        except ValueError:
            logger.warning("%s hỏng, quét lại từ đầu tuần: %r", KV_CURSOR, raw)
            cursor = None
        if cursor is None or cursor > now:  # cursor ở tương lai (đồng hồ bị chỉnh lùi) → quét lại cả tuần (idempotent)
            return floor, floor
        since = cursor - OVERLAP
        return since, min(since, now - LOOKBACK_COACH)

    def run(self, now: datetime) -> int:
        """Quét mọi nguồn; trả số event mới. Mỗi nguồn lỗi riêng không chặn nguồn khác; lỗi → không dời cursor."""
        now = _aware(now)
        since, since_coach = self._window(now)
        scans = (
            ("focus", lambda: self._scan_focus(since)),
            ("tasks", lambda: self._scan_tasks(since)),
            ("attempts", lambda: scan_attempts(self._engine, self._ledger, since_coach, self._module_engine_of)),
            ("agenda", lambda: scan_agenda(self._engine, self._ledger, since, self._module_engine_of)),
            ("writing", lambda: scan_writing(self._engine, self._ledger, since_coach, self._module_engine_of)),
            ("untangle", lambda: self._scan_untangle(since)),
            ("meetings", lambda: self._scan_meetings(since)),
        )
        created, failed = 0, False
        for name, scan in scans:
            try:
                created += scan()
            except Exception:  # noqa: BLE001 - gamification không được làm hỏng app
                failed = True
                logger.exception("Quét XP nguồn %s thất bại", name)
        if not failed:
            self._kv.set(KV_CURSOR, now.isoformat())
        return created

    def _scan_focus(self, since: datetime) -> int:
        with Session(self._engine) as s:
            rows = s.exec(select(FocusSession).where(
                FocusSession.ended_at >= since, FocusSession.actual_minutes > 0,
                FocusSession.focus_rating == COMPLETED_FOCUS_RATING)).all()
        return sum(self._ledger.add(
            f"focus:{r.id}", _aware(r.ended_at), "focus", "focus", "session_completed",
            {"mins": r.actual_minutes, "distractions": r.distraction_count}) is not None for r in rows)

    def _scan_meetings(self, since: datetime) -> int:
        """Phiên Họp/Học nhóm đã kết thúc → meeting_completed (key meeting:<id>, ts = ended_at). Bảng riêng nên KHÔNG lẫn Deep Work."""
        from src.core.meeting_mode.meeting_session_table_model_and_repository import MeetingSession
        MeetingSession.__table__.create(self._engine, checkfirst=True)
        with Session(self._engine) as s:
            rows = s.exec(select(MeetingSession).where(
                MeetingSession.ended_at >= since, MeetingSession.actual_minutes > 0)).all()
        return sum(self._ledger.add(
            f"meeting:{r.id}", _aware(r.ended_at), "meeting", "meeting", "meeting_completed",
            {"mins": r.actual_minutes, "kind": r.kind}) is not None for r in rows)

    def _scan_tasks(self, since: datetime) -> int:
        with Session(self._engine) as s:
            rows = s.exec(select(Task).where(Task.updated_at >= since)).all()
        created = 0
        for t in rows:
            net, n = self._ledger.task_net_xp(t.id)
            ts = _aware(t.updated_at)
            if t.status == "done" and net == 0:
                created += self._ledger.add(f"task_done:{t.id}:{n + 1}", ts, "work", "work", "task_done",
                                            {"category": t.category}) is not None
            elif t.status in REVOCABLE_STATUSES and net > 0:
                created += self._ledger.add(f"task_undone:{t.id}:{n}", ts, "work", "work", "task_undone",
                                            {"category": t.category}, xp=-net) is not None
        return created

    def _scan_untangle(self, since: datetime) -> int:
        """Phiên Gỡ Rối đã hoàn tất → idea_untangled (key untangle:<id>, ts = completed_at). Chưa có module → bỏ qua."""
        try:
            from src.core.idea_untangle.untangle_session_table_model import UntangleSession
        except ImportError:
            return 0
        UntangleSession.__table__.create(self._engine, checkfirst=True)
        with Session(self._engine) as s:
            rows = s.exec(select(UntangleSession).where(UntangleSession.completed_at >= since)).all()
        return sum(self._ledger.add(
            f"untangle:{r.id}", _aware(r.completed_at), "core", "core", "idea_untangled",
            {"problem_kind": r.problem_kind}) is not None for r in rows)
