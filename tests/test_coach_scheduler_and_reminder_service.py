"""Scheduler ôn + dịch vụ nhắc: Qt thật (offscreen) nhưng bubble/focus/kv giả; thời gian cố định."""

from datetime import datetime, timedelta

from coach_test_support import seed
from coach_ui_test_support import LOCAL_NOW, LOCAL_TZ, make_services, save_plan
from qt_offscreen_app_helper import get_qapp

from src.core.focus_engine import FocusState
from src.engines.coach.coach_prompt_round_robin_arbiter import RoundRobinArbiter
from src.engines.coach.coach_reminder_service import CoachReminderService
from src.engines.coach.coach_review_scheduler import CoachReviewScheduler


def _scheduler(engine, started=None, refills=None, arbiter=None):
    get_qapp()
    services, ctx = make_services(engine)
    seed(engine, ["Q1", "Q2"], now=LOCAL_NOW - timedelta(days=1))
    sched = CoachReviewScheduler(
        services, start_review=lambda n: started.append(n) if started is not None else None,
        refill=lambda: refills.append(1) if refills is not None else None, arbiter=arbiter or RoundRobinArbiter())
    return sched, services, ctx


def test_idle_tick_shows_bubble_with_three_actions(memory_engine):
    started: list = []
    sched, _, ctx = _scheduler(memory_engine, started)
    assert sched.tick() == "prompted"
    bubble = ctx.bubble.shown[0]
    assert bubble["text"] == "Có 2 câu ôn nè 🧠" and bubble["mood"] == "GENTLE_NUDGE"
    assert [c for c, _ in bubble["actions"]] == ["Làm", "10' nữa", "Bỏ qua hôm nay"]
    bubble["actions"][0][1]()
    assert started == [3]


def test_deep_work_and_paused_never_prompt_for_three_ticks(memory_engine):
    refills: list = []
    sched, _, ctx = _scheduler(memory_engine, refills=refills)
    for state in (FocusState.DEEP_WORK_RUNNING, FocusState.PAUSED):
        ctx.focus_engine.state = state
        assert [sched.tick() for _ in range(3)] == ["focus_session"] * 3
    assert ctx.bubble.shown == []
    assert len(refills) == 3          # PAUSED vẫn refill; DEEP_WORK thì không (3 tick PAUSED)


def test_break_transition_triggers_immediate_check(memory_engine):
    sched, _, ctx = _scheduler(memory_engine)
    sched.start()
    ctx.focus_engine.state = FocusState.BREAK_RUNNING
    ctx.focus_engine.state_changed.emit(FocusState.BREAK_RUNNING, "REST")
    assert len(ctx.bubble.shown) == 1
    sched.stop()


def test_snooze_and_skip_today_via_bubble_buttons(memory_engine):
    sched, services, ctx = _scheduler(memory_engine)
    sched.tick()
    ctx.bubble.shown[0]["actions"][1][1]()                       # 10' nữa
    assert sched.tick() == "snoozed"
    services._clock = lambda: LOCAL_NOW + timedelta(minutes=11)
    assert sched.tick() == "prompted"
    ctx.bubble.shown[-1]["actions"][2][1]()                      # Bỏ qua hôm nay
    assert sched.tick() == "skipped_today"
    services._clock = lambda: LOCAL_NOW + timedelta(days=1)
    assert sched.tick() == "prompted"


def test_busy_bubble_skips_and_round_robin_gives_waiting_module_its_turn(memory_engine):
    arbiter = RoundRobinArbiter()
    sched, services, ctx = _scheduler(memory_engine, arbiter=arbiter)
    ctx.bubble.busy = True
    assert sched.tick() == "bubble_busy"
    assert "thcs" in arbiter.waiting
    ctx.bubble.busy = False
    arbiter.record_prompt("duhoc", LOCAL_NOW)                    # module khác vừa được nhắc
    assert sched.tick() == "prompted"                            # thcs chờ lâu hơn → được ưu tiên


def test_policy_interval_change_rearms_timer(memory_engine):
    sched, services, _ = _scheduler(memory_engine)
    sched.start()
    assert sched._timer.interval() == 15 * 60_000
    save_plan(services, policy={"review_interval_mins": 30, "daily_cap": 20, "new_per_day": 10,
                                "leitner_days": [0.007, 1, 3, 7, 14, 30]})
    sched.tick()
    assert sched._timer.interval() == 30 * 60_000
    sched.stop()


# ---- nhắc agenda / mốc ----
def _reminders(engine, at: datetime, **plan):
    get_qapp()
    services, ctx = make_services(engine, now=at)
    save_plan(services, **plan)
    launched: list = []
    return CoachReminderService(services, launched.append), services, ctx, launched


AGENDA = [{"id": "a1", "kind": "quiz", "title": "Ôn câu điều kiện", "minutes": 15, "when": "19:30", "topic": "english.x"}]


def _at(h, m=0, day=19):
    return datetime(2026, 10, day, h, m, tzinfo=LOCAL_TZ)


def test_agenda_reminder_once_with_start_action(memory_engine):
    svc, services, ctx, launched = _reminders(memory_engine, _at(19, 26), agenda=AGENDA)
    assert svc.check() == "agenda"
    shown = ctx.bubble.shown[0]
    assert shown["text"] == "⏰ 19:30: Ôn câu điều kiện (15')"
    assert [c for c, _ in shown["actions"]] == ["Bắt đầu", "Để sau"]
    shown["actions"][0][1]()
    assert [i.id for i in launched] == ["a1"]
    assert svc.check() == "none"                                  # đã nhắc hôm nay


def test_agenda_reminder_blocked_by_deep_work_then_retried(memory_engine):
    svc, services, ctx, _ = _reminders(memory_engine, _at(19, 30), agenda=AGENDA)
    ctx.focus_engine.state = FocusState.DEEP_WORK_RUNNING
    assert svc.check() == "focus_session"
    ctx.focus_engine.state = FocusState.IDLE
    services._clock = lambda: _at(19, 45)
    assert svc.check() == "agenda"


def test_agenda_reminder_waits_when_bubble_busy(memory_engine):
    svc, _, ctx, _ = _reminders(memory_engine, _at(19, 30), agenda=AGENDA)
    ctx.bubble.busy = True
    assert svc.check() == "bubble_busy"
    ctx.bubble.busy = False
    assert svc.check() == "agenda"


def test_milestone_reminder_once_and_pruned_keys(memory_engine):
    ms = [{"id": "m1", "title": "Thi HSK3", "due_date": "2026-10-26"}]
    svc, services, ctx, _ = _reminders(memory_engine, _at(10), milestones=ms)
    assert svc.check() == "milestone"
    assert ctx.bubble.shown[0]["text"] == "🗓️ Còn 7 ngày: Thi HSK3 (26/10/2026)"
    assert svc.check() == "none"
    ctx.kv.set_json("coach.thcs.reminded", {"old": "2026-10-01", "m1x": "2026-10-19"})
    svc._remember("new")
    assert set(ctx.kv.get_json("coach.thcs.reminded")) == {"m1x", "new"}   # mục > 2 ngày bị xoá


def test_reminders_suppressed_when_paused(memory_engine):
    svc, _, ctx, _ = _reminders(memory_engine, _at(19, 30), agenda=AGENDA)
    ctx.focus_engine.state = FocusState.PAUSED
    assert svc.check() == "focus_session"
