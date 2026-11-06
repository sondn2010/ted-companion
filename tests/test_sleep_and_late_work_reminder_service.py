"""Unit tests cho SleepReminderService (nhắc ngủ sớm & cảnh báo làm việc muộn)."""

from datetime import date, datetime, timedelta, timezone
import pytest
from PySide6.QtCore import QObject, Signal

from src.config import settings
from src.core.app_state_key_value_store import KeyValueStore
from src.core.focus_engine import FocusState
from src.core.sleep_reminder.sleep_reminder_service import (
    SleepReminderService,
    night_cycle_date,
    parse_bedtime,
)


class FakeFocus(QObject):
    state_changed = Signal(str, str)

    def __init__(self, state=FocusState.IDLE):
        super().__init__()
        self.state = state
        self.current_mood = "IDLE"
        self.moods = []

    def set_mood(self, mood):
        self.current_mood = mood
        self.moods.append(mood)

    def pause_or_resume(self):
        if self.state == FocusState.DEEP_WORK_RUNNING:
            self.state = FocusState.PAUSED


class FakeBubble:
    def __init__(self):
        self.shown = []
        self.busy = False

    def is_busy(self):
        return self.busy

    def has_pending_actions(self):
        return False

    def show_message(self, text, mood=None, actions=(), timeout_ms=0, **_):
        self.shown.append((text, mood, list(actions)))


class FakeAudio:
    def __init__(self):
        self.chimes = 0

    def play_chime(self):
        self.chimes += 1


@pytest.fixture
def env(memory_engine):
    focus = FakeFocus()
    bubble = FakeBubble()
    audio = FakeAudio()
    kv = KeyValueStore(memory_engine)
    now_ref = {"dt": datetime(2026, 10, 27, 21, 0, tzinfo=timezone.utc)}

    service = SleepReminderService(
        focus_engine=focus,
        bubble=bubble,
        audio_manager=audio,
        kv=kv,
        now_fn=lambda: now_ref["dt"],
    )
    return focus, bubble, audio, kv, now_ref, service


def test_parse_bedtime():
    assert parse_bedtime("23:00") == (23, 0)
    assert parse_bedtime("22:30") == (22, 30)
    assert parse_bedtime("00:45") == (0, 45)
    assert parse_bedtime("invalid") == (23, 0)
    assert parse_bedtime("") == (23, 0)


def test_night_cycle_date():
    tz = timezone.utc
    assert night_cycle_date(datetime(2026, 10, 27, 22, 30, tzinfo=tz)) == date(2026, 10, 27)
    assert night_cycle_date(datetime(2026, 10, 28, 1, 30, tzinfo=tz)) == date(2026, 10, 27)
    assert night_cycle_date(datetime(2026, 10, 28, 4, 59, tzinfo=tz)) == date(2026, 10, 27)
    assert night_cycle_date(datetime(2026, 10, 28, 7, 0, tzinfo=tz)) == date(2026, 10, 28)


def test_approaching_bedtime_triggers_at_warning_time(env):
    focus, bubble, audio, kv, now_ref, service = env
    settings.sleep_reminder_enabled = True
    settings.bedtime_target = "23:00"
    settings.bedtime_warning_mins = 15

    # 22:40 (chưa đến mốc 22:45) -> không kích hoạt
    now_ref["dt"] = datetime(2026, 10, 27, 22, 40, tzinfo=timezone.utc)
    assert service.tick() is None

    # 22:45 (đúng mốc 15p trước giờ ngủ) -> kích hoạt approaching
    now_ref["dt"] = datetime(2026, 10, 27, 22, 45, tzinfo=timezone.utc)
    res = service.tick()
    assert res == "approaching"
    assert len(bubble.shown) == 1
    assert "Sắp đến giờ đi ngủ" in bubble.shown[0][0]
    assert audio.chimes == 1
    assert focus.current_mood == "REST"

    # Tick lại cùng đêm -> không kích hoạt trùng lặp
    now_ref["dt"] = datetime(2026, 10, 27, 22, 50, tzinfo=timezone.utc)
    assert service.tick() is None


def test_bedtime_due_triggers_at_bedtime(env):
    focus, bubble, audio, kv, now_ref, service = env
    settings.sleep_reminder_enabled = True
    settings.bedtime_target = "23:00"

    # 23:00 -> đúng giờ đi ngủ
    now_ref["dt"] = datetime(2026, 10, 27, 23, 0, tzinfo=timezone.utc)
    res = service.tick()
    assert res == "due"
    assert len(bubble.shown) == 1
    assert "Đã đến giờ đi ngủ" in bubble.shown[0][0]

    # Không kích hoạt lại trong cùng đêm
    now_ref["dt"] = datetime(2026, 10, 27, 23, 5, tzinfo=timezone.utc)
    assert service.tick() is None


def test_late_night_working_triggers_with_deep_work_warning(env):
    focus, bubble, audio, kv, now_ref, service = env
    settings.sleep_reminder_enabled = True
    settings.bedtime_target = "23:00"
    settings.late_work_nudge_interval_mins = 30
    focus.state = FocusState.DEEP_WORK_RUNNING

    # 23:30 (quá giờ ngủ + 15p, đang chạy Deep Work)
    now_ref["dt"] = datetime(2026, 10, 27, 23, 30, tzinfo=timezone.utc)
    res = service.tick()
    assert res == "late_work"
    assert len(bubble.shown) == 1
    assert "làm việc quá khuya" in bubble.shown[0][0].lower()
    assert "Deep Work" in bubble.shown[0][0]

    # Tick sau 10p (chưa đủ 30p interval) -> không lặp lại
    now_ref["dt"] = datetime(2026, 10, 27, 23, 40, tzinfo=timezone.utc)
    assert service.tick() is None

    # Sau 30p (00:01 sáng) -> kích hoạt đợt nhắc tiếp theo
    now_ref["dt"] = datetime(2026, 10, 28, 0, 1, tzinfo=timezone.utc)
    res = service.tick()
    assert res == "late_work"
    assert len(bubble.shown) == 2


def test_snooze_suppresses_reminders(env):
    focus, bubble, audio, kv, now_ref, service = env
    settings.sleep_reminder_enabled = True
    settings.bedtime_target = "23:00"

    # 23:00 -> due
    now_ref["dt"] = datetime(2026, 10, 27, 23, 0, tzinfo=timezone.utc)
    service.tick()
    actions = bubble.shown[0][2]

    # Bấm "Thêm 15 phút" (snooze)
    snooze_cb = actions[1][1]
    snooze_cb()

    # 23:10 (vẫn trong khoảng 15p snooze) -> không nhắc
    now_ref["dt"] = datetime(2026, 10, 27, 23, 10, tzinfo=timezone.utc)
    assert service.tick() is None

    # 23:16 (hết 15p snooze) -> có thể kích hoạt
    now_ref["dt"] = datetime(2026, 10, 27, 23, 20, tzinfo=timezone.utc)
    # Chưa đến mốc late_work (cần >= 23:15 và interval), lúc này 23:20 >= 23:15
    res = service.tick()
    assert res == "late_work"


def test_record_user_sleep_sets_mood_and_suppresses_idle(env):
    focus, bubble, audio, kv, now_ref, service = env
    settings.sleep_reminder_enabled = True
    settings.bedtime_target = "23:00"
    focus.state = FocusState.DEEP_WORK_RUNNING

    now_ref["dt"] = datetime(2026, 10, 27, 23, 0, tzinfo=timezone.utc)
    service.tick()

    # Bấm "Đi ngủ ngay"
    actions = bubble.shown[0][2]
    sleep_cb = actions[0][1]
    sleep_cb()

    assert focus.current_mood == "REST"
    assert focus.state == FocusState.PAUSED
    assert "Chúc bạn ngủ thật ngon" in bubble.shown[-1][0]

    # Nửa đêm (01:00 sáng) khi máy idle -> không làm phiền vì user đã bảo đi ngủ
    focus.state = FocusState.IDLE
    now_ref["dt"] = datetime(2026, 10, 28, 1, 0, tzinfo=timezone.utc)
    assert service.tick() is None


def test_disabled_setting_blocks_all(env):
    focus, bubble, audio, kv, now_ref, service = env
    settings.sleep_reminder_enabled = False
    now_ref["dt"] = datetime(2026, 10, 27, 23, 0, tzinfo=timezone.utc)
    assert service.tick() is None
    assert len(bubble.shown) == 0
