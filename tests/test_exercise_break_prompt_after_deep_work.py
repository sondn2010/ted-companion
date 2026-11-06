"""Unit tests cho tính năng nhắc tập thể dục tại chỗ sau Deep Work (chống đẩy, kéo xà, gập lưng...)."""

import asyncio
from datetime import datetime, timezone
import random
import pytest
from PySide6.QtCore import QObject, Signal

from src.config import settings
from src.core.app_state_key_value_store import KeyValueStore
from src.core.focus_engine import FocusState
from src.core.gamification.health_break_rotation_state import HealthBreakRotationState
from src.core.gamification.health_break_suggestions import (
    EXERCISE_ACTION_IDS,
    pick_exercise_suggestion,
)
from src.core.gamification.wellbeing_daily_repository import WellbeingDailyRepository
from src.ui.health_break_prompt_after_focus import HealthBreakPromptController

NOW = datetime(2026, 10, 27, 10, 0, tzinfo=timezone.utc)


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
        self.shown = []
        self.busy = False

    def is_busy(self):
        return self.busy

    def show_message(self, text, mood=None, actions=(), timeout_ms=0, **_):
        self.shown.append((text, mood, list(actions)))


@pytest.fixture
def env(memory_engine):
    focus = FakeFocus()
    bubble = FakeBubble()
    repo = WellbeingDailyRepository(memory_engine)
    kv = KeyValueStore(memory_engine)
    state = HealthBreakRotationState(kv)
    # Đã uống nước gần đây (0 phút trước) để không kích hoạt nhắc nước
    state.record_done("water", NOW)
    route = {"value": (None, False)}
    ctrl = HealthBreakPromptController(
        focus_engine=focus,
        bubble=bubble,
        wellbeing=repo,
        state=state,
        resolve_route=lambda: route["value"],
        now_fn=lambda: NOW,
        rng=random.Random(42),
        settle_delay_ms=0,
    )
    return focus, bubble, repo, state, ctrl


def test_exercise_action_ids_contain_core_exercises():
    assert "pushups_set" in EXERCISE_ACTION_IDS
    assert "pullups_bar" in EXERCISE_ACTION_IDS
    assert "back_bend_stretch" in EXERCISE_ACTION_IDS
    assert "squats_set" in EXERCISE_ACTION_IDS
    assert "back_arch_chest" in EXERCISE_ACTION_IDS


def test_pick_exercise_suggestion_filters_strong_on_late_night_or_kids():
    rng = random.Random(123)
    # Đêm khuya (23h) -> không chọn chống đẩy, kéo xà mạnh
    for _ in range(50):
        s = pick_exercise_suggestion(local_hour=23, kid_safe=False, rng=rng)
        assert s.action_id not in ("pushups_set", "pullups_bar", "squats_set")


def test_exercise_prompt_offered_after_deep_work_with_progress(env):
    focus, bubble, repo, state, ctrl = env
    settings.exercise_reminder_enabled = True
    settings.exercise_daily_target = 4

    assert asyncio.run(ctrl.offer(25)) is True
    assert len(bubble.shown) == 1
    text, mood, actions = bubble.shown[0]

    assert mood == "REST"
    assert "Thể dục tại chỗ sau Deep Work" in text
    assert "(Lần 1/4 hôm nay)" in text
    assert len(actions) == 3
    # Actions: [Đã làm, Bỏ qua, Đổi bài]
    assert "Đã làm" in actions[0][0]
    assert "Bỏ qua" in actions[1][0]
    assert "Đổi bài" in actions[2][0]


def test_exercise_done_increments_count_and_gives_progress_ack(env):
    focus, bubble, repo, state, ctrl = env
    settings.exercise_reminder_enabled = True
    settings.exercise_daily_target = 4

    asyncio.run(ctrl.offer(25))
    actions = bubble.shown[0][2]
    actions[0][1]()   # Click "Đã làm"

    assert state.exercise_count_today(NOW) == 1
    # Check ack message shows progress (1/4)
    last_text, last_mood, _ = bubble.shown[-1]
    assert last_mood == "CHEER"
    assert "1/4" in last_text


def test_exercise_reaches_target_shows_celebration(env):
    focus, bubble, repo, state, ctrl = env
    settings.exercise_reminder_enabled = True
    settings.exercise_daily_target = 4

    # Đã tập 3 lần trước đó
    for _ in range(3):
        state.record_exercise_done(NOW)
    assert state.exercise_count_today(NOW) == 3

    asyncio.run(ctrl.offer(25))
    text, _, actions = bubble.shown[-1]
    assert "(Lần 4/4 hôm nay)" in text

    actions[0][1]()   # Hoàn thành lần thứ 4
    assert state.exercise_count_today(NOW) == 4
    last_text, last_mood, _ = bubble.shown[-1]
    assert last_mood == "CHEER"
    assert "Tuyệt vời" in last_text
    assert "4/4" in last_text


def test_switch_exercise_rotates_suggestion(env):
    focus, bubble, repo, state, ctrl = env
    settings.exercise_reminder_enabled = True
    settings.exercise_daily_target = 4

    asyncio.run(ctrl.offer(25))
    initial_text = bubble.shown[0][0]
    switch_action = bubble.shown[0][2][2][1]

    # Bấm đổi bài
    switch_action()
    assert len(bubble.shown) >= 2
    switched_text = bubble.shown[-1][0]
    assert "Thể dục tại chỗ sau Deep Work" in switched_text
