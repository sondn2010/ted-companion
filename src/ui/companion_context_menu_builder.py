from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QMenu

from src.core.focus_engine import FocusState
from src.core.i18n import tr
from src.modules_runtime.engine_fixed_menus import ENGINE_MENUS
from src.ui.button_text_escape import btn_text
from src.ui.hotkey_menu_label_hint import with_hotkey_hint
from src.ui.meeting_mode.meeting_entry_point_helpers import meeting_active, request_meeting_toggle

def apply_overlay_menu_window_flags(menu: QMenu) -> None:
    """Menu nổi bo góc (QMenu[overlay="true"] trong 00-base.qss): cần nền trong suốt + bỏ bóng native, nếu không góc vuông lộ ra."""
    menu.setProperty("overlay", True)
    menu.setWindowFlags(menu.windowFlags() | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint)
    menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)


def _add(menu: QMenu, label: str, slot, hotkey_id: str = "") -> QAction:
    """`hotkey_id`: id hành động phím tắt → nối gợi ý phím vào cột phải của mục menu."""
    text = btn_text(label)
    action = QAction(with_hotkey_hint(text, hotkey_id) if hotkey_id else text, menu)
    action.triggered.connect(lambda checked=False: slot())
    menu.addAction(action)
    return action


def _add_module_actions(menu: QMenu, host, manifest) -> None:
    for item in ENGINE_MENUS.get(manifest.engine, []):
        _add(menu, item.label, lambda mid=manifest.id, aid=item.id: host.dispatch(mid, aid))


def build_companion_context_menu(menu: QMenu, ctx, companion) -> QMenu:
    """
    Thứ tự: (1) action của module chính; (2) submenu mỗi module bật khác + "Đặt làm module chính";
    (3) Pomodoro; (4) nhân vật, tiếng mưa, Trung tâm quản lý, Trợ giúp, Cài đặt, Ẩn, Thoát.
    """
    apply_overlay_menu_window_flags(menu)
    focus, registry, host = ctx.focus_engine, ctx.registry, ctx.engine_host

    from src.core.tts_service import tts_service
    if tts_service.is_speaking():  # chỉ hiện khi Ted đang nói, đặt đầu menu để bấm nhanh
        _add(menu, tr("menu_stop_speaking"), tts_service.stop)
        menu.addSeparator()

    active = registry.active()
    if active is not None:
        _add_module_actions(menu, host, active)
    for manifest in registry.enabled():
        if active is not None and manifest.id == active.id:
            continue
        sub = menu.addMenu(btn_text(f"{manifest.icon} {manifest.name} ▸".strip()))
        apply_overlay_menu_window_flags(sub)
        _add_module_actions(sub, host, manifest)
        sub.addSeparator()
        _add(sub, tr("menu_set_active_module"), lambda mid=manifest.id: registry.set_active(mid))
    menu.addSeparator()

    running = focus.state == FocusState.DEEP_WORK_RUNNING
    pomo_label = tr("menu_pause_pomo") if running else tr("menu_start_pomo")
    _add(menu, pomo_label, focus.pause_or_resume, "focus.toggle")
    _add(menu, tr("menu_stop_session"), lambda: focus.stop_session(completed=False), "focus.stop")
    _add(menu, tr("menu_meeting_stop" if meeting_active(focus) else "menu_meeting_start"),
         lambda: request_meeting_toggle(focus), "meeting.toggle")
    _add(menu, tr("menu_break_short"), lambda: focus.start_break(), "break.start")
    untangle = getattr(companion, "untangle_dialog", None)   # gắn bởi wire_idea_untangle; chưa gắn thì ẩn mục
    if untangle is not None:
        _add(menu, tr("menu_untangle"), untangle.open_menu, "untangle.open")
    menu.addSeparator()

    _add(menu, tr("menu_change_skin"), getattr(ctx.dashboard, "open_character_gallery", ctx.dashboard.open_settings))   # 1 mục thay cho danh sách nhân vật dài

    rain = tr("menu_rain_off") if ctx.audio.is_ambient_playing else tr("menu_rain_on")
    _add(menu, rain, lambda: ctx.audio.toggle_ambient())
    _add(menu, tr("menu_dashboard"), companion.open_dashboard, "dashboard.open")
    if hasattr(companion, "trigger_activity_report"):
        _add(menu, tr("menu_end_of_day_report"), companion.trigger_activity_report)
    if getattr(ctx, "gamification", None) is not None:
        _add(menu, tr("menu_hub"), ctx.dashboard.open_hub, "hub.open")
    _add(menu, tr("menu_help"), getattr(ctx.dashboard, "open_help", ctx.dashboard.open_settings))
    _add(menu, tr("menu_settings"), ctx.dashboard.open_settings)
    menu.addSeparator()
    _add(menu, tr("menu_hide_ted"), companion.hide, "pet.toggle")
    _add(menu, tr("menu_quit"), QApplication.instance().quit)
    return menu
