"""Hub phase 13 (UI): popup chủ đề (Enter/Bỏ qua đều bắt đầu), coordinator, hotkey, menu, nhắc bị chặn khi họp, sức khỏe sau họp."""

import random
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMenu, QWidget

from tests.qt_offscreen_app_helper import get_qapp

from src.config import settings
from src.core.app_state_key_value_store import KeyValueStore
from src.core.focus_engine import FocusEngine, FocusState
from src.core.gamification.health_break_rotation_state import HealthBreakRotationState
from src.core.gamification.wellbeing_daily_repository import WellbeingDailyRepository
from src.core.hotkeys.hotkey_action_catalog import ACTIONS_BY_ID
from src.core.i18n import TRANSLATIONS
from src.core.idea_untangle.untangle_nudge_watcher import UntangleNudgeWatcher
from src.core.meeting_mode.meeting_session_table_model_and_repository import MeetingSessionRepository
from src.ui import health_break_prompt_after_focus as prompt_mod
from src.ui.companion_context_menu_builder import build_companion_context_menu
from src.ui.companion_pet_painter import countdown_text, meeting_elapsed_text
from src.ui.health_break_prompt_after_focus import HealthBreakPromptController
from src.ui.meeting_mode.meeting_toggle_coordinator import MeetingToggleCoordinator
from src.ui.meeting_mode.meeting_topic_popup_dialog import MeetingTopicDialog


@pytest.fixture
def engine_and_calls(memory_engine):
    get_qapp()
    eng = FocusEngine(SimpleNamespace(play_chime=lambda: None))
    eng.ipc_timer.stop()
    eng.meeting_repo = MeetingSessionRepository(memory_engine)
    yield eng
    eng.tick_timer.stop()


# ---- popup ----
def test_enter_starts_with_topic_and_selected_kind():
    get_qapp()
    dlg = MeetingTopicDialog("Prefill", "team_meeting")
    got = []
    dlg.chosen.connect(lambda t, k: got.append((t, k)))
    assert dlg.txt_topic.text() == "Prefill" and dlg.chips["team_meeting"].isChecked()
    dlg.chips["teacher"].click()
    dlg.txt_topic.setText("  Giải tích 2 ")
    QTest.keyClick(dlg.txt_topic, Qt.Key.Key_Return)
    assert got == [("Giải tích 2", "teacher")]


def test_skip_starts_immediately_without_topic_but_keeps_kind():
    get_qapp()
    dlg = MeetingTopicDialog("Gợi ý lịch", "team_study")
    got = []
    dlg.chosen.connect(lambda t, k: got.append((t, k)))
    dlg.btn_skip.click()
    assert got == [("", "team_study")]


def test_escape_cancels_without_starting():
    get_qapp()
    dlg = MeetingTopicDialog("x", "other")
    got = []
    dlg.chosen.connect(lambda t, k: got.append((t, k)))
    dlg.reject()
    assert got == []


def test_coordinator_opens_popup_then_starts_and_second_toggle_stops(engine_and_calls):
    eng = engine_and_calls
    dialogs = []

    def factory(topic, kind):
        dlg = MeetingTopicDialog(topic, kind)
        dialogs.append(dlg)
        return dlg

    coordinator = MeetingToggleCoordinator(eng, lambda: ("Họp lịch", "team_meeting"), None, factory)
    eng.request_meeting_toggle()
    assert len(dialogs) == 1 and dialogs[0].txt_topic.text() == "Họp lịch" and not eng.in_meeting
    eng.request_meeting_toggle()                              # popup đang mở → không mở cái thứ hai
    assert len(dialogs) == 1
    dialogs[0].btn_skip.click()
    assert eng.in_meeting and eng.meeting_topic == ""
    eng.request_meeting_toggle()                              # đang họp → dừng
    assert not eng.in_meeting
    assert coordinator is not None


def test_coordinator_survives_prefill_failure(engine_and_calls):
    eng = engine_and_calls

    def boom():
        raise RuntimeError("lịch hỏng")

    dialogs = []
    coordinator = MeetingToggleCoordinator(eng, boom, None, lambda t, k: dialogs.append(MeetingTopicDialog(t, k)) or dialogs[-1])
    eng.request_meeting_toggle()
    assert dialogs[0].txt_topic.text() == "" and coordinator is not None


# ---- hotkey / menu / i18n ----
def test_hotkey_action_default_keys_and_label_parity():
    action = ACTIONS_BY_ID["meeting.toggle"]
    assert action.default_for("win32") == "Ctrl+Alt+M" and action.default_for("darwin") == "Meta+Alt+M"
    assert TRANSLATIONS["vi"][action.label_key] and TRANSLATIONS["en"][action.label_key]


def test_meeting_i18n_vi_en_parity():
    from src.core.i18n_meeting_strings import MEETING_EN, MEETING_VI
    assert set(MEETING_VI) == set(MEETING_EN)
    assert all(MEETING_VI[k].strip() and MEETING_EN[k].strip() for k in MEETING_VI)


def _menu_texts(in_meeting):
    get_qapp()
    calls = []
    focus = SimpleNamespace(state=FocusState.IDLE, in_meeting=in_meeting, pause_or_resume=lambda: None,
                            stop_session=lambda completed=False: None, start_break=lambda: None,
                            request_meeting_toggle=lambda: calls.append("toggle"))
    ctx = SimpleNamespace(focus_engine=focus, registry=SimpleNamespace(active=lambda: None, enabled=lambda: []),
                          audio=SimpleNamespace(is_ambient_playing=False, toggle_ambient=lambda: None),
                          engine_host=SimpleNamespace(dispatch=lambda *_: None),
                          dashboard=SimpleNamespace(open_settings=lambda: None))
    host = QWidget()
    menu = build_companion_context_menu(QMenu(host), ctx, SimpleNamespace(open_dashboard=lambda: None, hide=lambda: None))
    return host, menu, calls


def test_context_menu_meeting_entry_toggles_label_and_calls_request():
    from src.core.i18n import tr
    _host, menu, calls = _menu_texts(False)
    entry = next(a for a in menu.actions() if tr("menu_meeting_start").split(" ", 1)[1] in a.text())
    entry.trigger()
    assert calls == ["toggle"]
    _host2, menu2, _ = _menu_texts(True)
    assert any(tr("menu_meeting_stop").split(" ", 1)[1] in a.text() for a in menu2.actions())


# ---- nhắc bị chặn khi họp ----
class _WatcherFocus(QObject):
    session_started = Signal(str, str)
    timer_tick = Signal(int, int, str)

    def __init__(self):
        super().__init__()
        self.state = FocusState.MEETING_RUNNING
        self.elapsed_seconds = 3600
        self.distraction_count = 9
        self.active_task_id = ""
        self.active_task_title = "Họp"


def test_untangle_nudge_is_suppressed_during_meeting(memory_engine, monkeypatch):
    monkeypatch.setattr(settings, "untangle_nudge_enabled", True)
    focus, offers = _WatcherFocus(), []
    watcher = UntangleNudgeWatcher(focus, memory_engine, KeyValueStore(memory_engine), lambda: ("work", "work"),
                                   offers.append, is_suppressed=lambda: False)
    watcher.connect_signals()
    assert watcher.check(3600) is None and offers == []


class _HealthFocus(QObject):
    session_completed = Signal(str, int, int)
    meeting_completed = Signal(str, int)

    def __init__(self):
        super().__init__()
        self.state = FocusState.IDLE

    def set_mood(self, _mood):
        pass


class _Bubble:
    def __init__(self):
        self.shown = []

    def is_busy(self):
        return False

    def show_message(self, text, mood=None, actions=(), timeout_ms=0, **_):
        self.shown.append(text)


def test_health_break_prompt_also_runs_after_meeting_ends_not_during(memory_engine, monkeypatch):
    monkeypatch.setattr(settings, "health_break_prompt_enabled", True)
    focus, bubble, spawned = _HealthFocus(), _Bubble(), []
    ctrl = HealthBreakPromptController(
        focus, bubble, WellbeingDailyRepository(memory_engine), HealthBreakRotationState(KeyValueStore(memory_engine)),
        lambda: (None, False), now_fn=lambda: datetime(2026, 10, 22, 10, 0, tzinfo=timezone.utc),
        rng=random.Random(1), settle_delay_ms=0)
    monkeypatch.setattr(prompt_mod.QTimer, "singleShot", staticmethod(lambda _ms, fn: fn()))
    monkeypatch.setattr(prompt_mod, "spawn_background_task", lambda coro, name: (spawned.append(name), coro.close()))
    ctrl.connect_signals()
    focus.meeting_completed.emit("team_meeting", 0)           # họp rỗng → không hỏi
    assert spawned == []
    focus.meeting_completed.emit("teacher", 45)
    assert spawned == ["health-break-offer"]
    import asyncio
    focus.state = FocusState.MEETING_RUNNING                  # đang họp → bị chặn
    assert asyncio.run(ctrl.offer(45)) is False and bubble.shown == []
    focus.state = FocusState.IDLE                             # họp xong (IDLE) → hiện gợi ý
    assert asyncio.run(ctrl.offer(45)) is True and len(bubble.shown) == 1


# ---- đồng hồ pet ----
def test_pet_clock_texts():
    assert countdown_text(125) == "02:05"
    assert meeting_elapsed_text(0) == "00:00" and meeting_elapsed_text(125) == "02:05"
    assert meeting_elapsed_text(3725) == "1:02:05"
