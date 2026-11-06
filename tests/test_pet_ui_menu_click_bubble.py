"""Widget UI (QApplication offscreen): thứ tự menu theo module, click đơn vs đúp, bubble auto-hide + một-cái-một-lúc."""

from types import SimpleNamespace

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMenu, QWidget

from tests.qt_offscreen_app_helper import get_qapp

from src.core.focus_engine import FocusState
from src.modules_runtime.engine_fixed_menus import ENGINE_MENUS
from src.modules_runtime.module_manifest_schema import ModuleManifest
from src.ui.button_text_escape import btn_text
from src.ui.companion_context_menu_builder import build_companion_context_menu
from src.ui.pet_click_controller import PetClickController
from src.ui.pet_speech_bubble_widget import PetSpeechBubble

WORK = ModuleManifest(id="work", name="Công việc", icon="💼", engine="work", connection="work", enabled=True)
COACH = ModuleManifest(id="thcs", name="THCS", icon="📚", engine="coach", connection="thcs", learner_id="con")


def _ctx(enabled, active):
    dispatched, activated = [], []
    registry = SimpleNamespace(
        active=lambda: active, enabled=lambda: enabled, set_active=activated.append,
    )
    focus = SimpleNamespace(
        state=FocusState.IDLE, pause_or_resume=lambda: None, stop_session=lambda completed=False: None,
        start_break=lambda: None, set_character=lambda k: None,
    )
    ctx = SimpleNamespace(
        focus_engine=focus, registry=registry, audio=SimpleNamespace(is_ambient_playing=False, toggle_ambient=lambda: None),
        engine_host=SimpleNamespace(dispatch=lambda m, a: dispatched.append((m, a))),
        dashboard=SimpleNamespace(open_settings=lambda: None),
    )
    return ctx, dispatched, activated


def _build(ctx):
    get_qapp()
    host = QWidget()
    menu = build_companion_context_menu(QMenu(host), ctx, SimpleNamespace(open_dashboard=lambda: None, hide=lambda: None))
    return host, menu


def test_menu_only_work_enabled_has_module_actions_first_and_no_module_submenu():
    ctx, dispatched, _ = _ctx([WORK], WORK)
    _host, menu = _build(ctx)
    actions = menu.actions()
    expected = [a.label for a in ENGINE_MENUS["work"]]
    n = len(expected)
    assert [a.text() for a in actions[:n]] == expected
    assert actions[n].isSeparator()
    assert [a.menu() for a in actions if a.menu() is not None and "▸" in a.text() and "nhân vật" not in a.text()] == []
    actions[[a.id for a in ENGINE_MENUS["work"]].index("ask")].trigger()
    assert dispatched == [("work", "ask")]


def test_menu_adds_submenu_for_other_enabled_module_with_set_active():
    ctx, dispatched, activated = _ctx([WORK, COACH], WORK)
    _host, menu = _build(ctx)
    sub = next(a.menu() for a in menu.actions() if a.menu() is not None and "THCS" in a.text())
    texts = [a.text() for a in sub.actions() if not a.isSeparator()]
    assert texts[:5] == [btn_text(a.label) for a in ENGINE_MENUS["coach"]] and texts[-1] == "⭐ Đặt làm module chính"
    sub.actions()[1].trigger()
    sub.actions()[-1].trigger()
    assert dispatched == [("thcs", "review_now")] and activated == ["thcs"]


def test_click_controller_single_deferred_and_double_cancels_single():
    get_qapp()
    events = []
    ctl = PetClickController(lambda: events.append("single"), lambda: events.append("double"), interval_ms=lambda: 20)

    ctl.on_release(dragged=False)
    assert events == []  # chưa bắn ngay
    QTest.qWait(60)
    assert events == ["single"]

    events.clear()
    ctl.on_release(dragged=False)  # release của lần click 1
    ctl.on_double_click()
    ctl.on_release(dragged=False)  # release thứ 2 của double click phải bị bỏ qua
    QTest.qWait(60)
    assert events == ["double"]

    events.clear()
    ctl.on_release(dragged=True)  # kéo thả không phải click
    QTest.qWait(60)
    assert events == []


def test_bubble_auto_hides_sticky_and_replaces_previous_message():
    get_qapp()
    bubble = PetSpeechBubble()
    clicked = []
    bubble.show_message("xin chào", timeout_ms=30)
    assert bubble.is_busy()
    QTest.qWait(80)
    assert not bubble.is_busy()

    bubble.show_message("giữ nguyên", timeout_ms=0, actions=[("OK", lambda: clicked.append(1))])
    QTest.qWait(50)
    assert bubble.is_busy()
    bubble.show_message("thay thế", timeout_ms=0)
    assert bubble._label.text() == "thay thế" and bubble._buttons.count() == 0
    bubble.show_message("có nút", timeout_ms=0, actions=[("OK", lambda: clicked.append(1))])
    bubble._buttons.itemAt(0).widget().click()
    assert clicked == [1] and not bubble.is_busy()


def test_bubble_sizing_proportions_and_no_word_collapse():
    get_qapp()
    bubble = PetSpeechBubble()

    # Câu cheer không được sụp xuống 1 từ 1 dòng (bề rộng toothpick < 100px)
    bubble.show_message("Đừng lo, từng việc một thôi, không vội đâu.")
    w, h = bubble.width(), bubble.height()
    assert 180 <= w <= 255
    assert w > h, f"Bubble phải nằm ngang cân đối ({w}x{h})"

    # Cập nhật text cũng giữ tỉ lệ hợp lý
    bubble.update_text("Ngắn gọn")
    assert bubble.width() >= 180

    # Có action buttons: bề rộng đủ chứa các nút mà không bị xén
    bubble.show_message("Bạn có muốn tiếp tục?", actions=[("Đồng ý", lambda: None), ("Bỏ qua", lambda: None)])
    assert bubble.width() >= 180
    assert bubble._buttons.count() == 2


def test_bubble_chat_and_parking_lot_ux():
    get_qapp()
    parked = []
    focus = SimpleNamespace(
        record_distraction=lambda parked_idea_text: parked.append(parked_idea_text),
        get_context_snapshot=lambda: {},
        set_mood=lambda m: None,
    )
    bubble = PetSpeechBubble(focus_engine=focus)
    bubble.open_chat()
    assert bubble.isVisible()

    # 1. Gửi vào Bãi đỗ bằng nút 🅿️ Bãi đỗ
    bubble._input_field.setText("Mua cafe chiều nay")
    bubble.btn_park.click()
    assert parked == ["Mua cafe chiều nay"]
    assert "Đã cất vào Bãi đỗ" in bubble._label.text()
    assert bubble._input_field.text() == ""

    # 2. Chat trực tiếp bằng nút 💬 Chat (fallback khi chưa có kết nối)
    bubble._input_field.setText("Chào Ted")
    bubble.btn_chat.click()
    assert "Bạn: Chào Ted" in bubble._label.text()
    assert "Chưa có kết nối Hermes" in bubble._label.text()
    assert bubble._input_field.text() == ""


def test_bubble_keyboard_shortcuts():
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtCore import QEvent, Qt

    get_qapp()
    parked = []
    focus = SimpleNamespace(
        record_distraction=lambda parked_idea_text: parked.append(parked_idea_text),
        get_context_snapshot=lambda: {},
        set_mood=lambda m: None,
    )
    bubble = PetSpeechBubble(focus_engine=focus)
    bubble.open_chat()

    # Ctrl+Enter -> Cất vào Bãi đỗ
    bubble._input_field.setText("Ý tưởng mới")
    ctrl_enter = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)
    bubble._input_key_press_event(ctrl_enter)
    assert parked == ["Ý tưởng mới"]
    assert "Đã cất vào Bãi đỗ" in bubble._label.text()

    # Enter -> Chat
    bubble._input_field.setText("Hỏi nhanh")
    enter_key = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)
    bubble._input_key_press_event(enter_key)
    assert "Bạn: Hỏi nhanh" in bubble._label.text()

    # Esc -> Ẩn bong bóng
    assert bubble.isVisible()
    esc_key = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
    bubble._input_key_press_event(esc_key)
    assert not bubble.isVisible()


def test_dashboard_module_tabs_rebuild_and_settings_stays_last(tmp_path):
    from PySide6.QtWidgets import QLabel

    from src.config import AppConfig
    from src.modules_runtime.module_registry_loader import ModuleRegistry
    from src.ui.dashboard_window import DashboardWindow

    get_qapp()
    registry = ModuleRegistry(AppConfig(data_dir=tmp_path), dirs=[])
    engine = SimpleNamespace(manifest=COACH, build_dashboard_tab=lambda: QLabel("coach"))
    host = SimpleNamespace(engines={})
    win = DashboardWindow(SimpleNamespace(
        tasks_updated=SimpleNamespace(connect=lambda f: None),
        character_changed=SimpleNamespace(connect=lambda f: None),
        set_character=lambda k: None,
    ), registry)
    win.bind_modules(host)
    assert win.tabs.count() == 6   # tasks, journal, analytics, nhân vật, trợ giúp, cài đặt
    host.engines["thcs"] = engine
    registry.modules_changed.emit()
    assert win.tabs.count() == 7
    assert win.tabs.tabText(4) == "📚 THCS" and win.tabs.widget(6) is win.settings_tab
    host.engines.clear()
    registry.modules_changed.emit()
    assert win.tabs.count() == 6 and win.tabs.widget(5) is win.settings_tab


def test_companion_widget_pomodoro_buttons():
    from unittest.mock import MagicMock
    from src.core.focus_engine import FocusEngine
    from src.ui.companion_widget import TedCompanionWidget

    get_qapp()
    focus = FocusEngine(audio_manager=SimpleNamespace(play_chime=lambda: None, toggle_ambient=lambda: None, is_ambient_playing=False))
    ctx = SimpleNamespace(
        focus_engine=focus,
        quick_chat=SimpleNamespace(show_mindful_ping=lambda t: None, show_hermes_nudge=lambda m, s: None),
        bubble=None,
    )
    widget = TedCompanionWidget(ctx, cheer_provider=SimpleNamespace(show_cheer=lambda: None))
    widget.show()

    # IDLE state: single start button
    assert widget.btn_pomo_action.isVisible()
    assert not widget.btn_pomo_stop.isVisible()
    assert widget.btn_pomo_action.text() == "▶"
    assert "Bắt đầu" in widget.btn_pomo_action.toolTip()

    # Click start button -> DEEP_WORK_RUNNING
    widget.btn_pomo_action.click()
    assert focus.state == FocusState.DEEP_WORK_RUNNING
    assert widget.btn_pomo_action.isVisible()
    assert widget.btn_pomo_stop.isVisible()
    assert widget.btn_pomo_action.text() == "⏸"
    assert "Tạm dừng" in widget.btn_pomo_action.toolTip()
    assert widget.btn_pomo_stop.text() == "⏹"
    assert "Kết thúc" in widget.btn_pomo_stop.toolTip()

    # Click pause button -> PAUSED
    widget.btn_pomo_action.click()
    assert focus.state == FocusState.PAUSED
    assert widget.btn_pomo_action.text() == "▶"
    assert "Tiếp tục" in widget.btn_pomo_action.toolTip()

    # Click resume button -> DEEP_WORK_RUNNING
    widget.btn_pomo_action.click()
    assert focus.state == FocusState.DEEP_WORK_RUNNING

    # Click stop button -> IDLE
    widget.btn_pomo_stop.click()
    assert focus.state == FocusState.IDLE
    assert widget.btn_pomo_action.isVisible()
    assert not widget.btn_pomo_stop.isVisible()
    assert widget.btn_pomo_action.text() == "▶"
    assert "Bắt đầu" in widget.btn_pomo_action.toolTip()

