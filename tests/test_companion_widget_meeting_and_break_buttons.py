"""Kiểm tra 2 nút Chế độ Nghỉ ngơi [☕] và Chế độ Họp [👥] dưới đồng hồ trên TedCompanionWidget."""

from types import SimpleNamespace
from PySide6.QtCore import Qt
from tests.qt_offscreen_app_helper import get_qapp

from src.core.focus_engine import FocusEngine, FocusState
from src.core.i18n import i18n
from src.ui.companion_widget import TedCompanionWidget


def _create_widget():
    get_qapp()
    focus = FocusEngine(
        audio_manager=SimpleNamespace(
            play_chime=lambda: None,
            toggle_ambient=lambda: None,
            is_ambient_playing=False,
        )
    )
    focus.ipc_timer.stop()
    ctx = SimpleNamespace(
        focus_engine=focus,
        quick_chat=SimpleNamespace(
            show_mindful_ping=lambda t: None,
            show_hermes_nudge=lambda m, s: None,
        ),
        bubble=None,
    )
    widget = TedCompanionWidget(ctx, cheer_provider=SimpleNamespace(show_cheer=lambda: None))
    widget.show()
    return widget, focus


def test_companion_buttons_visible_and_positioned_in_idle():
    widget, focus = _create_widget()
    i18n.set_language("vi")

    # Ở trạng thái IDLE: hiển thị cả 3 nút: [☕: 134] [▶: 174] [👥: 214], stop ẩn
    assert widget.btn_pomo_break.isVisible()
    assert widget.btn_pomo_action.isVisible()
    assert widget.btn_pomo_meeting.isVisible()
    assert not widget.btn_pomo_stop.isVisible()

    assert not widget.btn_pomo_break.icon().isNull()
    assert not widget.btn_pomo_meeting.icon().isNull()
    assert widget.btn_pomo_action.text() == "▶"

    assert widget.btn_pomo_break.geometry().x() == 134
    assert widget.btn_pomo_action.geometry().x() == 174
    assert widget.btn_pomo_meeting.geometry().x() == 214
    assert widget.btn_pomo_break.geometry().y() == 92

    assert "Nghỉ" in widget.btn_pomo_break.toolTip()
    assert "Bắt đầu" in widget.btn_pomo_action.toolTip()
    assert "Họp" in widget.btn_pomo_meeting.toolTip()


def test_click_break_button_starts_break_and_updates_buttons():
    widget, focus = _create_widget()

    # Click nút nghỉ ngơi
    widget.btn_pomo_break.click()
    assert focus.state == FocusState.BREAK_RUNNING

    # Khi đang nghỉ: nút phụ ẩn, hiện nút action và stop
    assert not widget.btn_pomo_break.isVisible()
    assert not widget.btn_pomo_meeting.isVisible()
    assert widget.btn_pomo_action.isVisible()
    assert widget.btn_pomo_stop.isVisible()

    # Dừng nghỉ ngơi -> quay lại IDLE
    widget.btn_pomo_stop.click()
    assert focus.state == FocusState.IDLE
    assert widget.btn_pomo_break.isVisible()
    assert widget.btn_pomo_meeting.isVisible()
    assert not widget.btn_pomo_stop.isVisible()


def test_click_meeting_button_requests_meeting_toggle():
    widget, focus = _create_widget()
    requested = []
    focus.meeting_toggle_requested.connect(lambda: requested.append(True))

    widget.btn_pomo_meeting.click()
    assert len(requested) == 1


def test_companion_buttons_tooltips_bilingual():
    widget, focus = _create_widget()

    # Tiếng Việt
    i18n.set_language("vi")
    assert "Nghỉ" in widget.btn_pomo_break.toolTip()
    assert "Họp" in widget.btn_pomo_meeting.toolTip()
    assert "Bắt đầu" in widget.btn_pomo_action.toolTip()

    # English
    i18n.set_language("en")
    assert "break" in widget.btn_pomo_break.toolTip().lower()
    assert "meeting" in widget.btn_pomo_meeting.toolTip().lower()
    assert "start" in widget.btn_pomo_action.toolTip().lower()

    # Reset về vi
    i18n.set_language("vi")


class _FakeBubble:
    def __init__(self, busy=False):
        self.busy = busy
        self.calls = []

    def follow(self, _pet):
        pass

    def is_busy(self):
        return self.busy

    def show_message(self, text, mood=None, actions=(), timeout_ms=6000, task_links=()):
        self.calls.append((text, mood, list(actions), timeout_ms))

    opened = None
    pending = False
    hidden = False

    def has_pending_actions(self):
        return self.pending

    def open_chat(self, module_id=None, initial_text=""):
        self.opened = (self.opened or []) + [module_id]

    def hide(self):
        self.hidden = True


def _create_widget_with_bubble(bubble):
    get_qapp()
    focus = FocusEngine(audio_manager=SimpleNamespace(play_chime=lambda: None))
    focus.ipc_timer.stop()
    popup_calls = []
    ctx = SimpleNamespace(
        focus_engine=focus,
        quick_chat=SimpleNamespace(
            show_mindful_ping=lambda t: popup_calls.append(("ping", t)),
            show_ai_nudge=lambda m, s: popup_calls.append(("nudge", s)),
            show_hermes_nudge=lambda m, s: popup_calls.append(("nudge", s)),
            open_for=lambda mid: popup_calls.append(("open", mid)),
        ),
        bubble=bubble,
    )
    widget = TedCompanionWidget(ctx, cheer_provider=SimpleNamespace(show_cheer=lambda: None))
    return widget, focus, popup_calls


def test_deep_work_mindful_ping_uses_small_bubble_not_popup():
    bubble = _FakeBubble()
    widget, focus, popup_calls = _create_widget_with_bubble(bubble)
    focus.state = FocusState.DEEP_WORK_RUNNING

    widget._on_mindful_ping("Viết báo cáo")

    assert popup_calls == []
    text, mood, actions, timeout_ms = bubble.calls[0]
    assert "Viết báo cáo" in text and mood == "GENTLE_NUDGE"
    assert len(actions) == 2 and timeout_ms > 0   # không trả lời → tự ẩn

    focus.current_mood = "GENTLE_NUDGE"
    widget._restore_focus_mood()   # hết giờ không chọn → mặt Ted về FOCUS
    assert focus.current_mood == "FOCUS"

    actions[1][1]()   # "Hơi xao nhãng"
    assert focus.distraction_count == 1


def test_deep_work_ping_skipped_when_bubble_busy_and_nudge_routing():
    bubble = _FakeBubble(busy=True)
    widget, focus, popup_calls = _create_widget_with_bubble(bubble)
    focus.state = FocusState.DEEP_WORK_RUNNING
    widget._on_mindful_ping("X")
    assert bubble.calls == [] and popup_calls == []

    bubble.busy = False
    widget._on_external_nudge("GENTLE_NUDGE", "Ted nhắc")   # lời nhắc: bubble nhỏ + lưu vào trang Chat
    assert bubble.calls[-1][0] == "Ted nhắc" and popup_calls == [("nudge", "Ted nhắc")]


def test_single_click_opens_bubble_chat_and_double_click_opens_dashboard_chat(monkeypatch):
    monkeypatch.setattr("src.ui.companion_widget.spawn_background_task", lambda coro, _name: coro())
    bubble = _FakeBubble()
    widget, focus, popup_calls = _create_widget_with_bubble(bubble)
    widget.ctx.engine_host = None
    widget.ctx.registry = SimpleNamespace(active=lambda: SimpleNamespace(id="work"))
    cheers = []
    widget._cheer_provider = SimpleNamespace(show_cheer_in_chat=lambda: lambda: cheers.append(1))

    widget._on_single_click()
    assert bubble.opened == ["work"] and cheers == [1]

    bubble.pending = True   # đang có nhắc kèm nút → click đơn không ghi đè
    widget._on_single_click()
    assert bubble.opened == ["work"]

    widget._on_double_click()
    assert bubble.hidden and popup_calls[-1] == ("open", "work")

