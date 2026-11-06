"""Smoke test backend Windows thật (user32.RegisterHotKey) – chỉ chạy trên Windows."""

import sys

import pytest

from tests.qt_offscreen_app_helper import get_qapp

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="chỉ Windows")


def test_register_unregister_and_duplicate_is_os_taken():
    get_qapp()
    from src.core.hotkeys.windows_register_hotkey_backend import WindowsRegisterHotKeyBackend
    first, second = WindowsRegisterHotKeyBackend(), WindowsRegisterHotKeyBackend()
    seq = "Ctrl+Alt+Shift+F23"   # tổ hợp hiếm, khó đụng app khác
    try:
        assert first.register(101, seq) == (True, "")
        assert second.register(102, seq) == (False, "os_taken")   # cùng process vẫn bị từ chối (1409)
        assert first.register(103, "Ctrl+Alt+€")[1] == "unsupported_key"
    finally:
        first.unregister(101)
        second.unregister(102)
    assert second.register(102, seq) == (True, "")
    second.unregister(102)
