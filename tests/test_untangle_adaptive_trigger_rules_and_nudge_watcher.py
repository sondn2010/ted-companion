"""Phase 04: ngưỡng thích nghi, đánh giá trigger, cooldown/backoff, tín hiệu coach, watcher end-to-end (giả lập 1 giờ)."""
from datetime import datetime, timedelta, timezone

import pytest
from PySide6.QtCore import QObject, Signal
from sqlalchemy import create_engine
from sqlmodel import Session, SQLModel

from src.config import AppConfig, settings
from src.core.app_state_key_value_store import KeyValueStore
from src.core.focus_engine import FocusState
from src.core.idea_untangle.untangle_adaptive_trigger_rules import (
    NudgeState, Snapshot, Thresholds, compute_thresholds, cooldown_allows, distraction_limit,
    evaluate_untangle_trigger, record_accepted, record_shown, required_gap)
from src.core.idea_untangle.untangle_coach_stuck_signals import coach_signals, wrong_streak_kind
from src.core.idea_untangle.untangle_nudge_watcher import NUDGE_KV_KEY, UntangleNudgeWatcher
from src.core.models import Task
from src.engines.coach.coach_data_models import Attempt, QuizItem, content_hash

NOW = datetime(2026, 10, 22, 10, 0, tzinfo=timezone.utc)


# ---------- ngưỡng ----------
def test_cold_start_uses_defaults():
    th = compute_thresholds([2.0] * 4, [5] * 4, [9.0] * 4)
    assert th == Thresholds(1.5, 3, 0.0)


def test_slow_user_gets_higher_overrun_ratio_and_clamped():
    assert compute_thresholds([2.0] * 5, [], []).overrun_ratio == 2.5
    assert compute_thresholds([1.0] * 5, [], []).overrun_ratio == 1.5      # sàn
    assert compute_thresholds([9.0] * 5, [], []).overrun_ratio == 4.0      # trần


def test_streak_threshold_follows_history():
    assert compute_thresholds([], [1, 2, 2, 1, 2], []).streak_sessions == 3
    assert compute_thresholds([], [4, 4, 4, 4, 4], []).streak_sessions == 6


def test_distraction_limit_scales_with_baseline_but_floor_3():
    assert distraction_limit(Thresholds(distraction_rate=0.0), 3000) == 3
    assert distraction_limit(Thresholds(distraction_rate=4.0), 3000) == 16   # 2×4×50/25


# ---------- evaluate ----------
def _snap(**kw) -> Snapshot:
    base = dict(running_deep_work=True, elapsed_secs=900)
    base.update(kw)
    return Snapshot(**base)


def test_evaluate_requires_running_and_10_minutes():
    th = Thresholds()
    assert evaluate_untangle_trigger(_snap(elapsed_secs=599, distraction_count=9), th) is None
    assert evaluate_untangle_trigger(_snap(running_deep_work=False, distraction_count=9), th) is None


def test_evaluate_reasons_and_priority():
    th = Thresholds()
    assert evaluate_untangle_trigger(_snap(estimated_mins=25, task_focus_mins_before=25), th) == "overrun"   # 40 ≥ 37.5
    assert evaluate_untangle_trigger(_snap(estimated_mins=25, task_focus_mins_before=10), th) is None
    assert evaluate_untangle_trigger(_snap(consecutive_sessions=3), th) == "streak"
    assert evaluate_untangle_trigger(_snap(distraction_count=3), th) == "distracted"
    assert evaluate_untangle_trigger(_snap(distraction_count=3, consecutive_sessions=3, coach_wrong_streak=True), th) == "wrong_streak"
    assert evaluate_untangle_trigger(_snap(), th) is None


# ---------- cooldown ----------
def test_cooldown_caps_per_task_and_per_day_and_gap():
    st = record_accepted(record_shown(NudgeState(), "t1", NOW))
    assert not cooldown_allows(st, "t2", NOW + timedelta(minutes=89))        # chưa đủ 90'
    assert not cooldown_allows(st, "t1", NOW + timedelta(minutes=95))        # cùng task/ngày
    later = NOW + timedelta(minutes=95)
    assert cooldown_allows(st, "t2", later)
    st2 = record_accepted(record_shown(st, "t2", later))
    assert not cooldown_allows(st2, "t3", later + timedelta(minutes=100))    # đã đủ 2/ngày


def test_ignored_backoff_doubles_gap_and_caps():
    assert required_gap(0) == timedelta(minutes=90)
    assert required_gap(1) == timedelta(minutes=180)
    assert required_gap(3) == required_gap(10) == timedelta(minutes=720)
    st = NudgeState()
    for i in range(3):                                   # 3 nudge bị bỏ qua
        st = record_shown(st, f"t{i}", NOW)
    assert st.ignored == 3
    assert not cooldown_allows(st, "x", NOW + timedelta(hours=11))          # ≤1/ngày thực tế
    assert record_accepted(st).ignored == 0


def test_corrupt_state_is_safe():
    assert NudgeState.from_json("garbage") == NudgeState()
    assert NudgeState.from_json({"count_today": "x"}) == NudgeState()
    naive = NudgeState(last_shown="2026-01-01T08:00:00")   # mốc không múi giờ: không được ném TypeError
    assert cooldown_allows(naive, "t", datetime(2026, 1, 2, tzinfo=timezone.utc)) is True


# ---------- coach ----------
def test_wrong_streak_kind_same_item_and_topic():
    rows = [("a", "frac", "step", False)] * 3
    assert wrong_streak_kind(rows) == "math_problem"
    rows = [("a", "gram", "mcq", False), ("b", "gram", "mcq", False), ("c", "gram", "short", False)]
    assert wrong_streak_kind(rows) == "concept"                              # cùng chủ đề, khác câu
    assert wrong_streak_kind([("a", "t", "mcq", False)] * 2) is None
    assert wrong_streak_kind([("a", "t", "mcq", False), ("a", "t", "mcq", True), ("a", "t", "mcq", False)]) is None


@pytest.fixture
def engine(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 't.db'}")
    SQLModel.metadata.create_all(eng)
    return eng


def _quiz(engine, topic="frac", typ="step") -> str:
    with Session(engine) as s:
        q = QuizItem(module_id="coach1", topic=topic, type=typ, question="q" + topic + typ,
                     content_hash=content_hash(topic, "q" + typ))
        s.add(q)
        s.commit()
        return q.id


def _attempts(engine, item_id, results, module_id="coach1"):
    now = datetime.now(timezone.utc)
    with Session(engine) as s:
        for i, ok in enumerate(results):
            s.add(Attempt(item_id=item_id, module_id=module_id, answered_at=now - timedelta(seconds=60 - i), correct=ok))
        s.commit()


def test_coach_signals_from_db(engine):
    item = _quiz(engine)
    assert not coach_signals(engine, "coach1", datetime.now(timezone.utc)).wrong_streak
    _attempts(engine, item, [False, False, False])
    sig = coach_signals(engine, "coach1", datetime.now(timezone.utc))
    assert sig.wrong_streak and sig.kind == "math_problem"
    assert not coach_signals(engine, "other-module", datetime.now(timezone.utc)).wrong_streak   # khoá theo module


def test_coach_time_stuck_kind_from_recent_step_attempt(engine):
    _attempts(engine, _quiz(engine, "alg", "step"), [True])
    sig = coach_signals(engine, "coach1", datetime.now(timezone.utc))
    assert (sig.wrong_streak, sig.kind) == (False, "math_problem")


# ---------- watcher ----------
class FakeFocus(QObject):
    session_started = Signal(str, str)
    timer_tick = Signal(int, int, str)

    def __init__(self):
        super().__init__()
        self.state = FocusState.DEEP_WORK_RUNNING
        self.elapsed_seconds = 0
        self.distraction_count = 5
        self.active_task_id = ""
        self.active_task_title = "Việc"


class Clock:
    def __init__(self):
        self.now = datetime.now(timezone.utc)


def _watcher(engine, focus, offers, ctx=("work", "work"), suppressed=lambda: False, clock=None):
    clock = clock or Clock()
    w = UntangleNudgeWatcher(focus, engine, KeyValueStore(engine), lambda: ctx, offers.append,
                             is_suppressed=suppressed, now_fn=lambda: clock.now)
    w.connect_signals()
    return w


def _run(focus, seconds, clock=None):
    for sec in range(1, seconds + 1):
        focus.elapsed_seconds = sec
        if clock:
            clock.now += timedelta(seconds=1)
        focus.timer_tick.emit(0, 0, "")


@pytest.fixture(autouse=True)
def _enabled(monkeypatch):
    monkeypatch.setattr(settings, "untangle_nudge_enabled", True)


def test_one_hour_all_rules_true_gives_exactly_one_offer(engine):
    focus, offers, clock = FakeFocus(), [], Clock()
    w = _watcher(engine, focus, offers, clock=clock)   # giữ tham chiếu: QObject không parent sẽ bị GC
    focus.session_started.emit("", "Việc")
    _run(focus, 3600, clock)
    assert len(offers) == 1 and offers[0].reason == "distracted" and offers[0].kind == "other"


def test_disabled_setting_and_suppression_block_offer(engine, monkeypatch):
    focus, offers = FakeFocus(), []
    w = _watcher(engine, focus, offers, suppressed=lambda: True)
    focus.session_started.emit("", "Việc")
    _run(focus, 900)
    assert offers == []
    monkeypatch.setattr(settings, "untangle_nudge_enabled", False)
    w2 = _watcher(engine, focus, offers)
    assert w2.check(900) is None and offers == []


def test_coach_wrong_streak_offer_preselects_coach_kind_and_open_emits_signal(engine):
    _attempts(engine, _quiz(engine), [False, False, False])
    focus, offers = FakeFocus(), []
    focus.distraction_count = 0
    w = _watcher(engine, focus, offers, ctx=("coach1", "coach"))
    got = []
    w.nudge_requested.connect(lambda *a: got.append(a))
    focus.session_started.emit("", "Ôn toán")
    _run(focus, 600)
    assert len(offers) == 1 and offers[0].reason == "wrong_streak"
    w.open_offer()
    assert got == [("coach1", "", "math_problem", "wrong_streak")]
    assert KeyValueStore(engine).get_json(NUDGE_KV_KEY)["ignored"] == 0     # accept reset


def test_overrun_uses_task_history_and_estimate(engine):
    with Session(engine) as s:
        t = Task(title="x", estimated_pomodoros=1)
        s.add(t)
        s.commit()
        tid = t.id
    focus, offers = FakeFocus(), []
    focus.distraction_count, focus.active_task_id = 0, tid
    w = _watcher(engine, focus, offers)
    focus.session_started.emit(tid, "x")
    assert w.check(900) is None                      # 15' < 37.5'
    assert w.check(2400) is not None and offers[0].reason == "overrun"


def test_db_error_never_raises_into_tick(engine):
    focus, offers = FakeFocus(), []
    w = _watcher(engine, focus, offers)
    w._kv = None                                     # hỏng KV → check phải nuốt lỗi
    assert w.check(900) is None


def test_connect_is_idempotent(engine):
    focus, offers = FakeFocus(), []
    w = _watcher(engine, focus, offers)
    w.connect_signals()
    focus.session_started.emit("", "Việc")
    _run(focus, 600)
    assert len(offers) == 1
    w.disconnect_signals()
    w.disconnect_signals()


def test_untangle_nudge_setting_persists(tmp_path):
    cfg = AppConfig(data_dir=tmp_path)
    assert cfg.untangle_nudge_enabled is True
    cfg.untangle_nudge_enabled = False
    cfg.save()
    assert AppConfig(data_dir=tmp_path).untangle_nudge_enabled is False
