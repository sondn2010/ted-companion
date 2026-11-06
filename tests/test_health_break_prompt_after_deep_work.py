"""Phase 11: gợi ý sức khỏe nhỏ sau Deep Work: trigger, setting, bubble bận, xoay vòng offline, bonus Health, hợp đồng JSON."""

import asyncio
import random
from datetime import date, datetime, timezone

import pytest
from PySide6.QtCore import QObject, Signal

from src.config import settings
from src.core.app_state_key_value_store import KeyValueStore
from src.core.focus_engine import FocusState
from src.core.gamification import health_break_hermes_suggestion_fetcher as fetcher
from src.core.gamification.day_signals_collector import DaySignals, collect_day_signals
from src.core.gamification.growth_report_payload_builder import wellbeing_block_of_day
from src.core.gamification.health_break_contract_schema import HealthBreakSuggestion
from src.core.gamification.health_break_rotation_state import HealthBreakRotationState
from src.core.gamification.health_break_suggestions import KINDS, pick_offline_suggestion
from src.core.gamification.wellbeing_daily_repository import WellbeingDailyRepository
from src.core.gamification.wellbeing_stat_formulas import MICRO_BREAK_BONUS_CAP, health_stat
from src.core.gamification.xp_ledger_repository import XpLedgerRepository
from src.ui import health_break_prompt_after_focus as prompt_mod
from src.ui.health_break_prompt_after_focus import HealthBreakPromptController

NOW = datetime(2026, 10, 22, 10, 0, tzinfo=timezone.utc)


class FakeFocus(QObject):
    session_completed = Signal(str, int, int)
    meeting_completed = Signal(str, int)

    def __init__(self):
        super().__init__()
        self.state = FocusState.IDLE
        self.moods = []

    def set_mood(self, mood):
        self.moods.append(mood)


class FakeBubble:
    def __init__(self):
        self.shown, self.busy = [], False

    def is_busy(self):
        return self.busy

    def show_message(self, text, mood=None, actions=(), timeout_ms=0, **_):
        self.shown.append((text, mood, list(actions)))


@pytest.fixture(autouse=True)
def _prompt_enabled(monkeypatch):
    monkeypatch.setattr(settings, "health_break_prompt_enabled", True)


@pytest.fixture
def env(memory_engine):
    focus, bubble = FakeFocus(), FakeBubble()
    repo = WellbeingDailyRepository(memory_engine)
    state = HealthBreakRotationState(KeyValueStore(memory_engine))
    route = {"value": (None, False)}
    ctrl = HealthBreakPromptController(
        focus, bubble, repo, state, lambda: route["value"], now_fn=lambda: NOW,
        rng=random.Random(1), settle_delay_ms=0)
    return focus, bubble, repo, state, route, ctrl


def _offer(ctrl, mins=25):
    return asyncio.run(ctrl.offer(mins))


# ---- trigger / setting / suppression ----
def test_signal_schedules_offer_only_for_completed_session_with_minutes(env, monkeypatch):
    focus, _bubble, _repo, _state, _route, ctrl = env
    spawned = []
    monkeypatch.setattr(prompt_mod.QTimer, "singleShot", staticmethod(lambda _ms, fn: fn()))
    monkeypatch.setattr(prompt_mod, "spawn_background_task", lambda coro, name: (spawned.append(name), coro.close()))
    ctrl.connect_signals()
    focus.session_completed.emit("việc", 0, 0)       # phiên rỗng → không hỏi
    assert spawned == []
    focus.session_completed.emit("việc", 25, 1)
    assert spawned == ["health-break-offer"]


def test_setting_off_blocks_signal_and_offer(env, monkeypatch):
    focus, bubble, *_rest, ctrl = env
    monkeypatch.setattr(settings, "health_break_prompt_enabled", False)
    spawned = []
    monkeypatch.setattr(prompt_mod.QTimer, "singleShot", staticmethod(lambda _ms, fn: fn()))
    monkeypatch.setattr(prompt_mod, "spawn_background_task", lambda coro, name: (spawned.append(name), coro.close()))
    ctrl.connect_signals()
    focus.session_completed.emit("việc", 25, 0)
    assert spawned == [] and _offer(ctrl) is False and bubble.shown == []


@pytest.mark.parametrize("state", [FocusState.DEEP_WORK_RUNNING, FocusState.PAUSED, FocusState.MEETING_RUNNING])
def test_never_prompts_mid_session(env, state):
    focus, bubble, *_rest, ctrl = env
    focus.state = state
    assert _offer(ctrl) is False and bubble.shown == []


def test_prompts_during_automatic_break_after_deep_work(env):
    focus, bubble, *_rest, ctrl = env
    focus.state = FocusState.BREAK_RUNNING
    assert _offer(ctrl) is True and len(bubble.shown) == 1


def test_busy_bubble_still_suppresses_during_break(env):
    focus, bubble, *_rest, ctrl = env
    focus.state, bubble.busy = FocusState.BREAK_RUNNING, True
    assert _offer(ctrl) is False and bubble.shown == []


def test_busy_bubble_or_open_untangle_dialog_suppresses(env):
    focus, bubble, repo, state, route, _ctrl = env
    bubble.busy = True
    assert _offer(env[5]) is False and bubble.shown == []
    bubble.busy = False
    ctrl = HealthBreakPromptController(focus, bubble, repo, state, lambda: route["value"],
                                       is_untangle_dialog_visible=lambda: True, now_fn=lambda: NOW)
    assert _offer(ctrl) is False and bubble.shown == []


# ---- bubble + record ----
def test_offline_bubble_has_done_and_skip_and_done_records_without_xp(env, memory_engine):
    _focus, bubble, repo, state, _route, ctrl = env
    assert _offer(ctrl) is True
    text, mood, actions = bubble.shown[0]
    assert mood == "REST" and text and [a[0] for a in actions] == ["✅ Đã làm", "⏭ Bỏ qua"]
    assert state.recent_kinds() == ["water"]                  # chưa biết lần uống nước → ưu tiên nước
    actions[0][1]()                                            # bấm "Đã làm"
    day = repo.get(NOW.date())
    assert (day.micro_breaks_done, day.micro_water_done, day.micro_move_done) == (1, 1, 0)
    assert state.minutes_since_water(NOW) == 0
    assert bubble.shown[-1][1] == "CHEER"                      # xác nhận ngắn
    assert XpLedgerRepository(memory_engine).daily_totals(date(2026, 10, 22), date(2026, 10, 22)) == {}   # không XP


def test_skip_does_not_record_done(env):
    _focus, bubble, repo, *_ = env
    _offer(env[5])
    bubble.shown[0][2][1][1]()
    assert repo.get(NOW.date()).micro_breaks_done == 0


def test_coach_route_uses_kid_safe_offline_without_calling_hermes(env, monkeypatch):
    _focus, bubble, _repo, _state, route, ctrl = env
    route["value"] = (None, True)
    called = []
    monkeypatch.setattr(prompt_mod, "fetch_hermes_suggestion", lambda *a, **k: called.append(1))
    for _ in range(20):
        assert _offer(ctrl) is True
    assert called == [] and not any("chống đẩy" in t for t, _m, _a in bubble.shown)


def test_hermes_suggestion_used_when_work_client_answers(env, monkeypatch):
    _focus, bubble, _repo, _state, route, ctrl = env
    route["value"] = (object(), False)
    sug = HealthBreakSuggestion(action_id="rule_20_20_20", text_vi="Nhìn xa nhé", text_en="Look away",
                                duration_sec=20, kind="eyes")

    async def fake_fetch(_client, _ctx):
        return sug
    monkeypatch.setattr(prompt_mod, "fetch_hermes_suggestion", fake_fetch)
    assert _offer(ctrl) is True and bubble.shown[0][0] == "Nhìn xa nhé"


def test_hermes_timeout_falls_back_to_offline_within_budget(env, monkeypatch):
    _focus, bubble, _repo, _state, route, ctrl = env
    route["value"] = (object(), False)

    async def slow(*_a, **_k):
        await asyncio.sleep(10)
    monkeypatch.setattr(fetcher, "request_json", slow)
    monkeypatch.setattr(fetcher, "HERMES_TIMEOUT_SECS", 0.05)
    monkeypatch.setattr(prompt_mod, "fetch_hermes_suggestion",
                        lambda c, x: fetcher.fetch_hermes_suggestion(c, x, timeout=0.05))
    assert _offer(ctrl) is True and bubble.shown      # vẫn có gợi ý offline


def test_session_started_while_waiting_for_hermes_drops_prompt(env, monkeypatch):
    focus, bubble, _repo, _state, route, ctrl = env
    route["value"] = (object(), False)

    async def user_starts_new_session(_client, _ctx):
        focus.state = FocusState.DEEP_WORK_RUNNING
        return None
    monkeypatch.setattr(prompt_mod, "fetch_hermes_suggestion", user_starts_new_session)
    assert _offer(ctrl) is False and bubble.shown == []


# ---- offline rotation ----
def test_rotation_never_repeats_last_two_kinds_and_covers_all_kinds():
    rng, recent, seen = random.Random(7), [], set()
    for _ in range(200):
        s = pick_offline_suggestion(recent, minutes_since_water=10, local_hour=14, rng=rng)
        assert s.kind not in recent[-2:]
        recent.append(s.kind)
        seen.add(s.kind)
    assert seen == set(KINDS)


def test_water_due_after_90_minutes_but_not_twice_in_a_row():
    assert pick_offline_suggestion(["move", "eyes"], 120, 14, rng=random.Random(0)).kind == "water"
    assert pick_offline_suggestion(["eyes", "water"], 120, 14, rng=random.Random(0)).kind != "water"


@pytest.mark.parametrize("hour,kid", [(23, False), (3, False), (14, True)])
def test_no_intense_moves_late_night_or_kid_safe(hour, kid):
    rng = random.Random(3)
    for _ in range(300):
        assert pick_offline_suggestion([], 10, hour, kid_safe=kid, rng=rng).action_id != "pushups_small"


# ---- Health bonus + repo + payload ----
def test_health_bonus_is_three_per_done_capped_at_fifteen():
    base = health_stat(DaySignals())
    assert health_stat(DaySignals(micro_breaks=2)) == base + 6
    assert health_stat(DaySignals(micro_breaks=5)) == base + MICRO_BREAK_BONUS_CAP
    assert health_stat(DaySignals(micro_breaks=50)) == base + MICRO_BREAK_BONUS_CAP


def test_micro_break_counts_flow_into_signals_export_and_payload_block(memory_engine):
    repo, ledger = WellbeingDailyRepository(memory_engine), XpLedgerRepository(memory_engine)
    day = date(2026, 10, 22)
    for kind in ("water", "move", "posture", "eyes"):
        repo.log_micro_break(day, kind)
    sig = collect_day_signals(memory_engine, ledger, repo, day)
    assert (sig.micro_breaks, sig.micro_water, sig.micro_move) == (4, 1, 2)
    exported = repo.export_range(day, day)[0]
    assert exported["micro_breaks_done"] == 4 and exported["micro_water_done"] == 1
    from src.core.gamification.wellbeing_stat_formulas import compute_day_stats
    block = wellbeing_block_of_day(type("A", (), {"signals": sig, "stats": compute_day_stats(sig)})())
    assert (block["micro_breaks"], block["micro_water"], block["micro_move"]) == (4, 1, 2)


def test_old_database_gets_new_wellbeing_columns(memory_engine):
    from sqlalchemy import text
    from src.core.gamification.gamification_columns_migration import ensure_gamification_columns
    WellbeingDailyRepository(memory_engine)
    with memory_engine.begin() as c:
        c.execute(text("ALTER TABLE dailywellbeing DROP COLUMN micro_breaks_done"))
    ensure_gamification_columns(memory_engine)
    WellbeingDailyRepository(memory_engine).log_micro_break(date(2026, 10, 22), "water")
    assert WellbeingDailyRepository(memory_engine).get(date(2026, 10, 22)).micro_breaks_done == 1


# ---- JSON contract ----
def test_contract_accepts_valid_and_rejects_bad_payloads():
    ok = {"action_id": "box_breathing", "text_vi": "Hít thở nhé", "text_en": "Breathe", "duration_sec": 60, "kind": "breath"}
    assert HealthBreakSuggestion.model_validate(ok).text_for("en") == "Breathe"
    for bad in ({**ok, "kind": "pushup"}, {**ok, "duration_sec": 900}, {**ok, "action_id": "../x"},
                {**ok, "text_vi": ""}, {**ok, "extra": 1}):
        with pytest.raises(Exception):
            HealthBreakSuggestion.model_validate(bad)


def test_prompt_contains_tag_and_only_aggregates():
    ctx = fetcher.HealthBreakContext(25, 2, 1, None, 45.0, 14, 61, ("eyes",), "vi")
    text = fetcher.build_health_break_prompt(ctx)
    assert text.startswith("[TED_HEALTH_BREAK] session_minutes=25") and "since_water_min=unknown" in text
    assert "since_move_min=45" in text and "recent_kinds=eyes" in text


def test_fetch_returns_none_on_hermes_error_without_raising():
    class Boom:
        async def complete_text(self, *_a, **_k):
            raise RuntimeError("boom")
    ctx = fetcher.HealthBreakContext(25, 0, 0, None, None, 9, None)
    assert asyncio.run(fetcher.fetch_hermes_suggestion(Boom(), ctx, timeout=0.5)) is None
