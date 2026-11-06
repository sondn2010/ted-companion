"""Phase 02 gamification: reconciler (focus/task/coach/untangle), idempotent, migration cột, Hub service refresh."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import text
from sqlmodel import Session

from src.core.app_state_key_value_store import KeyValueStore
from src.core.gamification.gamification_columns_migration import ensure_gamification_columns
from src.core.gamification.gamification_hub_service import GamificationHubService
from src.core.gamification.xp_ledger_repository import XpLedgerRepository
from src.core.gamification.xp_source_reconciler import XpSourceReconciler
from src.core.models import DatabaseManager, FocusSession, Task
from src.engines.coach.coach_data_models import AgendaDone, Attempt, WritingSubmission


def _now():
    return datetime.now(timezone.utc)


@pytest.fixture
def ledger(memory_engine):
    return XpLedgerRepository(memory_engine)


@pytest.fixture
def rec(memory_engine, ledger):
    return XpSourceReconciler(memory_engine, ledger, KeyValueStore(memory_engine), lambda mid: "coach")


def _add(engine, *rows):
    with Session(engine, expire_on_commit=False) as s:  # giữ id đọc được sau khi session đóng
        s.add_all(rows)
        s.commit()


def _kinds(ledger):
    return dict(ledger.lifetime_counts())


def test_focus_only_completed_sessions_and_idempotent(memory_engine, ledger, rec):
    now = _now()
    _add(memory_engine,
         FocusSession(actual_minutes=25, distraction_count=0, focus_rating=5, ended_at=now),
         FocusSession(actual_minutes=10, focus_rating=4, ended_at=now),      # dừng giữa chừng: không XP
         FocusSession(actual_minutes=0, focus_rating=5, ended_at=now))       # 0 phút: bỏ qua
    assert rec.run(now) == 1
    assert ledger.daily_totals(now.astimezone().date(), now.astimezone().date()) == {now.astimezone().date(): 35}
    assert rec.run(now) == 0


def test_stop_session_completed_writes_rating_5(memory_engine, monkeypatch):
    """Khoá giả định: heuristic 'hoàn thành' = focus_rating == 5 đúng bằng stop_session(completed=True)."""
    from src.core import focus_engine as fe
    monkeypatch.setattr(fe, "db", DatabaseManager.for_engine(memory_engine))
    eng = fe.FocusEngine(audio_manager=SimpleNamespace(play_chime=lambda: None))
    eng.start_focus_session("x", 25)
    eng.elapsed_seconds = 25 * 60
    eng.stop_session(completed=True)
    eng.start_focus_session("y", 25)
    eng.elapsed_seconds = 10 * 60
    eng.stop_session(completed=False)
    with Session(memory_engine) as s:
        ratings = sorted(r.focus_rating for r in s.exec(__import__("sqlmodel").select(FocusSession)).all())
    assert ratings == [4, 5]


def test_task_done_undone_redone_cycle_and_parked_idea(memory_engine, ledger, rec):
    now = _now()
    t = Task(title="a", status="done", updated_at=now)
    p = Task(title="p", category="parked_idea", status="done", updated_at=now)
    _add(memory_engine, t, p)
    tid = t.id
    assert rec.run(now) == 2
    assert ledger.task_net_xp(tid) == (15, 1)
    with Session(memory_engine) as s:
        s.get(Task, tid).status = "todo"
        s.get(Task, tid).updated_at = now + timedelta(minutes=1)
        s.commit()
    assert rec.run(now + timedelta(minutes=2)) == 1
    assert ledger.task_net_xp(tid) == (0, 1)
    with Session(memory_engine) as s:
        s.get(Task, tid).status = "done"
        s.get(Task, tid).updated_at = now + timedelta(minutes=3)
        s.commit()
    assert rec.run(now + timedelta(minutes=4)) == 1
    assert ledger.task_net_xp(tid) == (15, 2)
    assert rec.run(now + timedelta(minutes=5)) == 0
    day = now.astimezone().date()
    assert ledger.daily_totals(day, day)[day] == 15 + 5


def test_deleted_done_task_keeps_xp_and_archived_not_revoked(memory_engine, ledger, rec):
    now = _now()
    t = Task(title="a", status="done", updated_at=now)
    _add(memory_engine, t)
    rec.run(now)
    with Session(memory_engine) as s:
        s.delete(s.get(Task, t.id))
        s.commit()
    assert rec.run(now + timedelta(minutes=1)) == 0
    assert ledger.task_net_xp(t.id) == (15, 1)


def test_coach_sources_and_regrade_caught_within_7_days(memory_engine, ledger, rec):
    now = _now()
    a_ok = Attempt(item_id="i", module_id="thcs", answered_at=now, correct=True)
    a_bad = Attempt(item_id="j", module_id="thcs", answered_at=now, correct=False)
    _add(memory_engine, a_ok, a_bad,
         AgendaDone(module_id="thcs", agenda_id="d1", done_at=now),
         WritingSubmission(module_id="duhoc", prompt="p", text="t", result_json="{}", created_at=now),
         WritingSubmission(module_id="duhoc", prompt="p", text="t", result_json="", created_at=now))
    assert rec.run(now) == 5   # 2 answered + 1 correct + agenda + writing
    kinds = _kinds(ledger)
    assert kinds["quiz_answered"] == 2 and kinds["quiz_correct"] == 1 and kinds["writing_graded"] == 1
    bad_id = a_bad.id
    with Session(memory_engine) as s:   # "Mình đúng mà": chấm lại sau
        s.get(Attempt, bad_id).correct = True
        s.commit()
    assert rec.run(now + timedelta(hours=1)) == 1
    assert rec.run(now + timedelta(hours=2)) == 0


def test_non_coach_module_ignored(memory_engine, ledger):
    now = _now()
    r = XpSourceReconciler(memory_engine, ledger, KeyValueStore(memory_engine), lambda mid: "work")
    _add(memory_engine, Attempt(item_id="i", module_id="w", answered_at=now, correct=True))
    assert r.run(now) == 0


def test_first_run_only_backfills_current_week(memory_engine, ledger, rec):
    now = _now()
    _add(memory_engine, FocusSession(actual_minutes=25, focus_rating=5, ended_at=now - timedelta(days=30)))
    assert rec.run(now) == 0


def test_event_ts_is_source_time_not_scan_time(memory_engine, ledger, rec):
    now = _now()
    ended = now - timedelta(hours=1)
    _add(memory_engine, FocusSession(actual_minutes=20, focus_rating=5, ended_at=ended))
    rec.run(now)
    assert ledger.has_key(f"focus:{_focus_id(memory_engine)}")
    assert ledger.daily_totals(ended.astimezone().date(), ended.astimezone().date())


def _focus_id(engine):
    with Session(engine) as s:
        return s.exec(__import__("sqlmodel").select(FocusSession.id)).first()


def test_untangle_completed_sessions_awarded_once(memory_engine, ledger, rec):
    from src.core.idea_untangle.untangle_session_table_model import UntangleSession
    UntangleSession.__table__.create(memory_engine, checkfirst=True)
    now = _now()
    done = UntangleSession(completed_at=now)
    _add(memory_engine, done, UntangleSession(completed_at=None))
    assert rec.run(now) == 1
    assert ledger.has_key(f"untangle:{done.id}")
    assert _kinds(ledger) == {"idea_untangled": 1}
    assert rec.run(now) == 0


def test_failed_scan_does_not_advance_cursor(memory_engine, ledger, rec, monkeypatch):
    def boom(since):
        raise RuntimeError("x")
    monkeypatch.setattr(rec, "_scan_focus", boom)
    rec.run(_now())
    assert KeyValueStore(memory_engine).get("gamify.reconcile_since") is None


def test_ensure_gamification_columns_adds_missing_late_night(memory_engine):
    with memory_engine.begin() as c:
        c.execute(text("ALTER TABLE dailywellbeing DROP COLUMN late_night_minutes"))
    ensure_gamification_columns(memory_engine)
    with memory_engine.begin() as c:
        cols = {r[1] for r in c.execute(text('PRAGMA table_info("dailywellbeing")'))}
    assert "late_night_minutes" in cols
    ensure_gamification_columns(memory_engine)   # idempotent


class _Bubble:
    def __init__(self, busy=False):
        self.busy, self.said = busy, []

    def is_busy(self):
        return self.busy

    def show_message(self, text, mood=None, **_):
        self.said.append(text)


def _service(engine, bubble):
    ctx = SimpleNamespace(kv=KeyValueStore(engine), registry=None, focus_engine=None, bubble=bubble)
    return GamificationHubService(ctx, engine)


def test_hub_refresh_builds_snapshot_and_announces_badge_once(memory_engine):
    bubble = _Bubble()
    svc = _service(memory_engine, bubble)
    now = _now()
    _add(memory_engine, *[Task(title=str(i), status="done", updated_at=now) for i in range(20)])
    got = []
    svc.snapshot_changed.connect(got.append)
    snap = svc.refresh()
    assert snap is got[0] and snap.week_xp == 300 and 0 <= snap.pct <= 100 and snap.level >= 5
    assert snap.distinct_badge_count >= 1 and any("🏅" in m for m in bubble.said)
    said = len(bubble.said)
    svc.refresh()
    assert len(bubble.said) == said   # badge không báo lại


def test_hub_busy_bubble_keeps_one_pending_message(memory_engine):
    bubble = _Bubble(busy=True)
    svc = _service(memory_engine, bubble)
    svc._bubble.say("a")
    svc._bubble.say("b")
    assert bubble.said == []
    bubble.busy = False
    svc._bubble.flush()
    assert bubble.said == ["b"]


def test_hub_level_change_in_same_week_emits_signal(memory_engine):
    svc = _service(memory_engine, _Bubble())
    base = svc.refresh()
    kv = svc.kv
    kv.set("gamify.last_level", f"{base.week_start.isoformat()}:{base.level + 1}")
    changes = []
    svc.level_changed.connect(lambda a, b: changes.append((a, b)))
    svc.refresh()
    assert changes == [(base.level + 1, base.level)]


def test_hub_refresh_swallows_errors(memory_engine, monkeypatch):
    svc = _service(memory_engine, _Bubble())
    monkeypatch.setattr(svc.reconciler, "run", lambda now: (_ for _ in ()).throw(RuntimeError("boom")))
    assert svc.refresh() is None
