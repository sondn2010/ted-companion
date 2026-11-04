"""Backend dự phòng trong app: phím thật (QTest) phải kích hoạt khi một cửa sổ Ted đang active.

Hồi quy: bản cũ gắn QShortcut vào QWidget ẩn → Qt bỏ qua, phím dự phòng không bao giờ chạy.
"""

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLineEdit, QWidget

from tests.qt_offscreen_app_helper import get_qapp

_CTRL_ALT = Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier


def _active_window_with_edit():
    win = QWidget()
    edit = QLineEdit(win)
    win.show()
    win.activateWindow()
    QTest.qWaitForWindowActive(win, 1000)
    edit.setFocus()
    return win, edit


def test_registered_combo_fires_and_unregistered_does_not():
    get_qapp()
    from src.core.hotkeys.app_level_qshortcut_backend import AppLevelQShortcutBackend
    backend, hits = AppLevelQShortcutBackend(), []
    backend.activated.connect(hits.append)
    win, edit = _active_window_with_edit()
    try:
        assert backend.register(7, "Ctrl+Alt+P") == (True, "")
        QTest.keyClick(edit, Qt.Key.Key_P, _CTRL_ALT)
        assert hits == [7]
        backend.unregister(7)
        QTest.keyClick(edit, Qt.Key.Key_P, _CTRL_ALT)
        assert hits == [7]
    finally:
        win.close()


def test_combo_owned_by_other_id_is_rejected_and_owner_kept():
    get_qapp()
    from src.core.hotkeys.app_level_qshortcut_backend import AppLevelQShortcutBackend
    backend = AppLevelQShortcutBackend()
    assert backend.register(1, "Ctrl+Alt+K") == (True, "")
    assert backend.register(2, "Ctrl+Alt+K") == (False, "os_taken")
    backend.unregister(2)   # huỷ id trùng không được xoá phím của id 1
    assert backend.register(3, "Ctrl+Alt+K") == (False, "os_taken")
