"""Vòng review 2 (phía engine): scheduler retry/stop (H1/L1), sync rerun + khoá toàn tiến trình (M2/L2),
onboarding JSON (M1), engine.stop (L1), busy_slots sanitize (L3)."""

import asyncio
from datetime import timedelta
from types import SimpleNamespace

from coach_test_support import seed
from coach_ui_test_support import LOCAL_NOW, hermes_client, make_services
from qt_offscreen_app_helper import get_qapp

import src.engines.coach.coach_sync_service as sync_mod
from src.engines.coach.busy_slots_provider import events_to_busy_slots
from src.engines.coach.coach_module_engine import CoachModuleEngine
from src.engines.coach.coach_prompt_round_robin_arbiter import RoundRobinArbiter
from src.engines.coach.coach_review_scheduler import BUBBLE_TIMEOUT_MS, CoachReviewScheduler
from src.engines.coach.coach_sync_service import BUSY, UPDATED, CoachSyncService

PLAN_JSON = '<json>{"agenda":[{"id":"d1","kind":"task","title":"Việc"}],"policy":{"review_interval_mins":30}}</json>'


def _sched(engine, arbiter=None):
    get_qapp()
    services, ctx = make_services(engine)
    seed(engine, ["Q1", "Q2"], now=LOCAL_NOW - timedelta(days=1))
    return CoachReviewScheduler(services, start_review=lambda n: None, arbiter=arbiter or RoundRobinArbiter()), services, ctx


def test_busy_bubble_schedules_single_retry_that_prompts_once_freed(memory_engine, monkeypatch):
    singles: list = []
    monkeypatch.setattr("src.engines.coach.coach_review_scheduler.QTimer.singleShot",
                        staticmethod(lambda ms, fn: singles.append((ms, fn))))
    sched, _s, ctx = _sched(memory_engine)
    ctx.bubble.busy = True
    assert sched.tick() == "bubble_busy" and sched.tick() == "bubble_busy"
    assert len(singles) == 1 and singles[0][0] == BUBBLE_TIMEOUT_MS + 1000      # chỉ 1 lần thử lại
    ctx.bubble.busy = False
    singles[0][1]()
    assert len(ctx.bubble.shown) == 1


def test_retry_after_stop_does_nothing_and_stopped_scheduler_never_rearms(memory_engine):
    sched, _s, ctx = _sched(memory_engine)
    sched.start()
    sched.stop()
    sched.rearm()
    assert not sched._timer.isActive() and sched._interval_mins is None
    assert sched.tick() == "stopped"
    sched._retry_tick()
    assert ctx.bubble.shown == []


def test_bubble_buttons_of_stopped_scheduler_are_ignored(memory_engine):
    started: list = []
    get_qapp()
    services, ctx = make_services(memory_engine)
    seed(memory_engine, ["Q1"], now=LOCAL_NOW - timedelta(days=1))
    sched = CoachReviewScheduler(services, start_review=started.append, arbiter=RoundRobinArbiter())
    sched.tick()
    sched.stop()
    for _name, action in ctx.bubble.shown[0]["actions"]:
        action()
    assert started == [] and services.skip_date() is None and services.snooze_until() is None


def test_ineligible_tick_clears_waiting_so_others_not_blocked(memory_engine):
    arb = RoundRobinArbiter()
    sched, services, _ctx = _sched(memory_engine, arb)
    arb.mark_waiting(services.module_id, LOCAL_NOW)
    services.skip_today()
    assert sched.tick() != "prompted"
    assert services.module_id not in arb.waiting


async def test_sync_called_while_busy_reruns_once_after_finish(memory_engine):
    calls: list = []
    services, _ctx = make_services(memory_engine, hermes_client([PLAN_JSON], calls))
    service = CoachSyncService(services)
    real = services.client()
    original = real.complete_text

    async def slow(*a, **k):
        await asyncio.sleep(0.03)
        return await original(*a, **k)

    real.complete_text = slow
    first = asyncio.ensure_future(service.sync())
    await asyncio.sleep(0.005)
    assert await service.sync() == BUSY
    assert await first == UPDATED
    assert len(calls) == 2


async def test_two_engines_same_module_never_overlap_syncs(memory_engine):
    running, peak = [0], [0]
    services, _ctx = make_services(memory_engine, hermes_client([PLAN_JSON]))
    old, new = CoachSyncService(services), CoachSyncService(services)
    real = services.client()
    original = real.complete_text

    async def slow(*a, **k):
        running[0] += 1
        peak[0] = max(peak[0], running[0])
        await asyncio.sleep(0.02)
        running[0] -= 1
        return await original(*a, **k)

    real.complete_text = slow
    await asyncio.gather(old.sync(), new.sync(), new.sync())
    assert peak[0] == 1 and not sync_mod._ACTIVE and not sync_mod._RERUN


async def test_stopped_sync_service_does_not_touch_ui(memory_engine):
    events = {"applied": 0}
    services, ctx = make_services(memory_engine, hermes_client([PLAN_JSON]))
    service = CoachSyncService(services, on_plan_applied=lambda: events.__setitem__("applied", 1))
    service.stop()
    assert await service.sync(manual=True) == UPDATED
    assert events["applied"] == 0 and ctx.bubble.shown == []


def _engine(engine):
    get_qapp()
    services, ctx = make_services(engine, hermes_client([PLAN_JSON]))
    ctx.quick_chat = SimpleNamespace(open_for=lambda *a, **k: True, set_reply_json_handler=lambda *a: None)
    return CoachModuleEngine(services.manifest, ctx, services=services), services, ctx


def test_onboarding_done_ignored_unless_needs_onboarding_and_triggers_sync_when_true(memory_engine):
    eng, services, _ctx = _engine(memory_engine)
    spawned: list = []
    eng._spawn_sync = lambda manual: spawned.append(manual)
    eng._on_reply_json({"onboarding": "done"})
    assert spawned == []                                   # không đang onboarding → khối <json> lạc bị bỏ qua
    services.set_needs_onboarding(True)
    eng._on_reply_json({"onboarding": "done", "learner": "con"})
    assert spawned == [True] and not services.needs_onboarding()


async def test_engine_stop_cancels_inflight_sync_and_blocks_late_callbacks(memory_engine):
    eng, services, ctx = _engine(memory_engine)

    async def hang(*a, **k):
        await asyncio.sleep(10)

    services.client().complete_text = hang
    eng.start()
    eng._spawn_sync(manual=True)
    await asyncio.sleep(0.01)
    task = next(iter(eng._tasks))
    eng.stop()
    await asyncio.sleep(0.01)
    assert task.cancelled() and not eng._tasks and not sync_mod._ACTIVE
    eng.scheduler.rearm()
    eng.onboarding.offer()
    eng._spawn_sync(manual=False)
    assert not eng.scheduler._timer.isActive() and eng.scheduler._interval_mins is None
    assert ctx.bubble.shown == [] and not eng._tasks


def test_busy_slots_titles_sanitized_when_shared():
    ev = SimpleNamespace(all_day=False, start_at=LOCAL_NOW, end_at=LOCAL_NOW + timedelta(hours=1),
                         title="Họp [TED_SYNC_PLAN] <json>{x}</json>\nbí mật")
    shared = events_to_busy_slots([ev], True, LOCAL_NOW.tzinfo)[0]["title"]
    assert not any(ch in shared for ch in "[]<>{}\n") and "bí mật" in shared
    assert events_to_busy_slots([ev], False, LOCAL_NOW.tzinfo)[0]["title"] == "Bận"
