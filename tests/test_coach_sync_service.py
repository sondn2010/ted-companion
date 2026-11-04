"""CoachSyncService: [TED_SYNC_PLAN] thật qua HermesBrainClient + httpx.MockTransport, DB SQLite in-memory."""

import asyncio
import json

import httpx
import pytest
from coach_test_support import MODULE, quiz
from coach_ui_test_support import LOCAL_NOW, hermes_client, make_services

from src.engines.coach.coach_policy_clamp import DEFAULT_POLICY
from src.engines.coach.coach_sync_service import (
    BUSY, FAILED, FAILED_TEXT, NEEDS_ONBOARDING, NO_CONNECTION_TEXT, UPDATED, CoachSyncService, last_sync_key)

POLICY = {"review_interval_mins": 30, "daily_cap": 12, "new_per_day": 4, "quiet_hours": ["22:00-06:30"],
          "study_windows": ["19:30-21:30"], "leitner_days": [0.007, 1, 3, 7, 14, 30], "rationale": "Gần thi"}
PLAN = {"display": {"title": "Ôn thi vào 10", "phase": "Nền tảng"}, "policy": POLICY,
        "agenda": [{"id": "ag-1", "kind": "quiz", "title": "Ôn điều kiện", "minutes": 15, "topic": "english.cond"},
                   {"id": "ag-2", "kind": "task", "title": "Làm hộ chiếu"}],
        "milestones": [], "checklist": [], "srs_overrides": []}


def _reply(data: dict) -> str:
    return "<json>" + json.dumps(data, ensure_ascii=False) + "</json>"


def _request(calls: list, index: int = 0) -> dict:
    content = calls[index]["messages"][-1]["content"]
    assert content.startswith("[TED_SYNC_PLAN]")
    return json.loads(content.split("<json>")[1].split("</json>")[0])


def _setup(engine, replies, busy=None, calls=None):
    calls = calls if calls is not None else []
    services, ctx = make_services(engine, hermes_client(replies, calls))
    events = {"onboarding": 0, "applied": 0}
    service = CoachSyncService(
        services, busy_slots=lambda: busy,
        on_needs_onboarding=lambda: events.__setitem__("onboarding", events["onboarding"] + 1),
        on_plan_applied=lambda: events.__setitem__("applied", events["applied"] + 1))
    return service, services, ctx, events, calls


async def test_payload_saves_snapshot_clamps_policy_applies_overrides_and_marks_done(memory_engine):
    service, services, ctx, events, _ = _setup(memory_engine, ["placeholder"])
    services.items.insert_items_dedup(MODULE, [quiz("Câu cần retire")], LOCAL_NOW)
    victim = services.items.select_for_review(MODULE, LOCAL_NOW, 5, 5, LOCAL_NOW)[0]
    plan = {**PLAN, "policy": dict(POLICY, review_interval_mins=5, daily_cap=99),   # ngoài khoảng → bị kẹp
            "srs_overrides": [{"item_id": victim.id, "action": "retire"}]}
    services.ctx.client_pool.for_module = lambda _m: hermes_client([_reply(plan)])
    services.plans.mark_done(MODULE, "ag-old", LOCAL_NOW)
    assert await service.sync(manual=True) == UPDATED
    snapshot = services.plans.get_snapshot(MODULE)
    assert [a.id for a in snapshot.agenda] == ["ag-1", "ag-2"] and snapshot.display.title == "Ôn thi vào 10"
    assert snapshot.policy.review_interval_mins == 10 and snapshot.policy.daily_cap == 40   # kẹp 10–120 / 5–40
    assert services.items.get(victim.id).retired is True
    assert services.plans.unreported_done_ids(MODULE) == []                                 # ag-old đã được báo
    assert ctx.kv.get(last_sync_key(MODULE)) == "2026-10-19" and not services.needs_onboarding()
    assert events == {"onboarding": 0, "applied": 1}
    assert ctx.bubble.shown[-1]["text"] == "Đã cập nhật kế hoạch: 2 việc hôm nay"


async def test_needs_onboarding_keeps_snapshot_sets_flag_and_offers_onboarding(memory_engine):
    service, services, ctx, events, _ = _setup(memory_engine, [_reply(PLAN), _reply({"needs_onboarding": True})])
    await service.sync()
    before = services.plans.get_snapshot(MODULE).model_dump()
    assert await service.sync(manual=True) == NEEDS_ONBOARDING
    assert services.plans.get_snapshot(MODULE).model_dump() == before
    assert services.needs_onboarding() and events["onboarding"] == 1


async def test_garbage_twice_then_offline_keep_snapshot(memory_engine):
    service, services, ctx, events, calls = _setup(memory_engine, [_reply(PLAN)])
    await service.sync()
    before = services.plans.get_snapshot(MODULE).model_dump()
    garbage = hermes_client(["không có json", "{} vẫn không phải kế hoạch"], calls := [])
    services.ctx.client_pool.for_module = lambda _m: garbage
    assert await service.sync(manual=True) == FAILED and len(calls) == 2   # 1 retry theo request_json
    assert ctx.bubble.shown[-1]["text"] == FAILED_TEXT
    offline = hermes_client([httpx.ConnectError("down")])
    services.ctx.client_pool.for_module = lambda _m: offline
    assert await service.sync(manual=True) == FAILED
    assert services.plans.get_snapshot(MODULE).model_dump() == before and events["applied"] == 1


async def test_automatic_sync_failure_is_silent(memory_engine):
    service, services, ctx, *_ = _setup(memory_engine, [httpx.ConnectError("down")])
    assert await service.sync(manual=False) == FAILED
    assert ctx.bubble.shown == []


async def test_invalid_policy_in_valid_payload_saves_snapshot_and_keeps_old_policy(memory_engine):
    service, services, *_ = _setup(memory_engine, [_reply({**PLAN, "policy": {"review_interval_mins": "x"}})])
    assert await service.sync() == UPDATED
    assert len(services.plans.get_snapshot(MODULE).agenda) == 2
    assert services.policy() == DEFAULT_POLICY


async def test_concurrent_sync_never_overlaps_and_reruns_once(memory_engine):
    service, _services, _ctx, _events, calls = _setup(memory_engine, [_reply(PLAN)])
    real = _services.client()
    original = real.complete_text

    async def slow(*args, **kwargs):
        await asyncio.sleep(0.05)                          # giữ request "đang bay" để lệnh sync thứ 2 đến giữa chừng
        return await original(*args, **kwargs)

    real.complete_text = slow
    results = await asyncio.gather(service.sync(), service.sync())
    real.complete_text = original
    assert sorted(results) == sorted([UPDATED, BUSY])
    assert len(calls) == 2                       # lệnh đến lúc bận KHÔNG mất: chạy lại đúng 1 lần sau khi xong
    assert await service.sync() == UPDATED and len(calls) == 3           # nhả khoá sau khi xong


async def test_request_contains_stats_policy_and_unacknowledged_done_ids(memory_engine):
    service, services, _ctx, _events, calls = _setup(memory_engine, [_reply(PLAN)])
    services.plans.mark_done(MODULE, "agenda-hôm-qua", LOCAL_NOW.replace(day=18))   # tick muộn chưa được báo
    services.plans.mark_done(MODULE, "agenda-hôm-nay", LOCAL_NOW)
    await service.sync()
    request = _request(calls)
    assert request["learner"] == "con" and request["now"] == "2026-10-19T12:00:00+07:00"
    assert request["done_today"] == ["agenda-hôm-qua", "agenda-hôm-nay"]
    assert set(request["stats"]) == {"last7_answered", "last7_correct", "weak_topics", "due_reviews", "unseen_items",
                                     "streak_days"}
    assert request["current_policy"] == {"review_interval_mins": 15, "daily_cap": 20, "new_per_day": 10}
    assert "busy_slots" not in request                                            # không có module work → bỏ khoá


async def test_busy_slots_included_when_provider_has_them(memory_engine):
    busy = [{"start": "2026-10-19T14:00+07:00", "end": "2026-10-19T15:00+07:00", "title": "Bận"}]
    service, _s, _c, _e, calls = _setup(memory_engine, [_reply(PLAN)], busy=busy)
    await service.sync()
    assert _request(calls)["busy_slots"] == busy


async def test_done_ticked_while_in_flight_stays_unreported_for_next_sync(memory_engine):
    service, services, _ctx, _events, calls = _setup(memory_engine, [_reply(PLAN)])
    services.plans.mark_done(MODULE, "sent-id", LOCAL_NOW)
    real = services.client()
    original = real.complete_text

    async def tick_during_flight(*args, **kwargs):
        services.mark_done("late-id")                    # người dùng tick xong khi request đang bay
        return await original(*args, **kwargs)

    real.complete_text = tick_during_flight
    await service.sync()
    assert services.plans.unreported_done_ids(MODULE) == ["late-id"]
    real.complete_text = original
    await service.sync()
    assert _request(calls, 1)["done_today"] == ["late-id"]
    assert services.plans.unreported_done_ids(MODULE) == []
    with pytest.raises(AssertionError):                   # sent-id không bị gửi lại lần 2
        assert "sent-id" in _request(calls, 1)["done_today"]


async def test_missing_client_or_learner_is_skipped_with_bubble_on_manual(memory_engine):
    service, services, ctx, *_ = _setup(memory_engine, ["x"])
    services.ctx.client_pool.for_module = lambda _m: None
    assert await service.sync(manual=True) == "skipped"
    assert ctx.bubble.shown[-1]["text"] == NO_CONNECTION_TEXT


def test_is_due_today_follows_last_sync_date(memory_engine):
    service, services, ctx, *_ = _setup(memory_engine, ["x"])
    assert service.is_due_today()
    ctx.kv.set(last_sync_key(MODULE), "2026-10-18")
    assert service.is_due_today()
    ctx.kv.set(last_sync_key(MODULE), services.today().isoformat())
    assert not service.is_due_today()
