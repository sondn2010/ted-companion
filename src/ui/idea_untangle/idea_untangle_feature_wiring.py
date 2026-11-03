"""Nối tính năng Gỡ Rối Ý Tưởng vào app: hộp thoại + phím tắt `untangle.open` + watcher nudge + điểm vào menu/tray."""

import logging

from PySide6.QtGui import QGuiApplication

from src.core.hotkeys.global_hotkey_manager import GlobalHotkeyManager, hotkey_manager
from src.ui.idea_untangle.untangle_dialog_window import UntangleDialog
from src.ui.idea_untangle.untangle_nudge_bubble_installer import install_untangle_nudge_watcher

logger = logging.getLogger("ted")


def _place_near_companion(dlg: UntangleDialog, companion) -> None:
    """Đặt hộp thoại cạnh Ted (kẹp trong màn hình); chỉ khi chưa hiện để không giật cửa sổ đang mở."""
    if dlg.isVisible():
        return
    screen = QGuiApplication.screenAt(companion.pos()) or QGuiApplication.primaryScreen()
    area = screen.availableGeometry()
    x = min(max(area.left() + 10, companion.pos().x() - dlg.width() + companion.width()), area.right() - dlg.width() - 10)
    y = min(max(area.top() + 10, companion.pos().y() - dlg.height() - 12), area.bottom() - dlg.height() - 10)
    dlg.move(x, y)


def wire_idea_untangle(ctx, companion, manager: GlobalHotkeyManager = hotkey_manager) -> UntangleDialog:
    """Tạo hộp thoại, gắn vào `companion.untangle_dialog` (menu/tray dùng getattr), bind hotkey, cài nudge watcher."""
    dlg = UntangleDialog(ctx.focus_engine, ctx.client_pool, ctx.registry, kv=ctx.kv)

    def open_dialog(trigger: str, module_id=None, task_id=None, kind=None) -> None:
        _place_near_companion(dlg, companion)
        dlg.open_from(trigger, module_id=module_id, task_id=task_id or None, kind=kind)

    def module_context():
        active = ctx.registry.active()
        return (active.id, active.engine) if active else ("work", "work")

    dlg.open_menu = lambda: open_dialog("menu")   # điểm vào cho context menu / tray
    companion.untangle_dialog = dlg
    manager.bind_callback("untangle.open", lambda: open_dialog("hotkey"))
    try:
        from src.core.models import db
        watcher = install_untangle_nudge_watcher(ctx.focus_engine, ctx.bubble, db.engine, ctx.kv, module_context,
                                                 is_untangle_dialog_visible=dlg.isVisible, parent=dlg)
        watcher.nudge_requested.connect(lambda mid, tid, kind, _reason: open_dialog("nudge", mid, tid, kind))
    except Exception:   # nudge lỗi không được làm hỏng phím tắt/menu
        logger.exception("Không cài được nudge Gỡ Rối, tiếp tục không có nudge")
    return dlg
