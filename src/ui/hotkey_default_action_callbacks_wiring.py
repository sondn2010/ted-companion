"""Nối từng hành động phím tắt vào điểm vào có sẵn của app (focus engine, dashboard, chat nhanh, tray).

`untangle.open` KHÔNG nối ở đây (gắn ở phase Untangle) → luôn "unavailable" tới khi có handler.
`hub.open` chỉ khả dụng khi dashboard có `open_hub`.
"""

from src.core.hotkeys.global_hotkey_manager import GlobalHotkeyManager, hotkey_manager
from src.ui.meeting_mode.meeting_entry_point_helpers import meeting_active, request_meeting_toggle


def wire_default_hotkey_actions(ctx, companion, tray, manager: GlobalHotkeyManager = hotkey_manager) -> None:
    focus = ctx.focus_engine

    def open_quick_chat(focus_parking: bool = False) -> None:
        active = ctx.registry.active()
        ctx.quick_chat.open_for(active.id if active else "work")   # mở trang Chat trong Dashboard
        if focus_parking:
            ctx.quick_chat.focus_parking_input()

    manager.bind_callback("focus.toggle", focus.pause_or_resume)
    manager.bind_callback("focus.stop", lambda: focus.stop_session(completed=False))
    manager.bind_callback("break.start", lambda: focus.start_break())
    manager.bind_callback("dashboard.open", companion.open_dashboard)
    manager.bind_callback("quick_chat.open", open_quick_chat)
    manager.bind_callback("parking.quick_park", lambda: open_quick_chat(focus_parking=True))
    manager.bind_callback("pet.toggle", tray.toggle_companion)
    manager.bind_callback("meeting.toggle", lambda: request_meeting_toggle(focus))   # coordinator (install_meeting_mode) xử lý
    manager.bind_callback("hub.open", lambda: ctx.dashboard.open_hub(),
                          available=lambda: hasattr(ctx.dashboard, "open_hub"))
