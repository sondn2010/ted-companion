"""Test GlobalHotkeyManager với backend giả: đăng ký, rebind + rollback, suspend/resume, fallback, callback lỗi."""

from PySide6.QtCore import QObject, Signal

from src.core.hotkeys.global_hotkey_manager import GlobalHotkeyManager


class FakeBackend(QObject):
    activated = Signal(int)

    def __init__(self, is_global=True, taken=()):
        super().__init__()
        self.is_global = is_global
        self.taken = {t.lower() for t in taken}
        self.registered: dict[int, str] = {}

    def register(self, hid, seq):
        if seq.lower() in self.taken:
            return False, "os_taken"
        self.registered[hid] = seq
        return True, ""

    def unregister(self, hid):
        self.registered.pop(hid, None)


def make_manager(native=None, app=None):
    native = native if native is not None else FakeBackend()
    app = app if app is not None else FakeBackend(is_global=False)
    mgr = GlobalHotkeyManager(platform="win32", native_factory=lambda: native, app_factory=lambda: app)
    return mgr, native, app


def bind_all(mgr, calls):
    for aid in ("focus.toggle", "focus.stop", "pet.toggle"):
        mgr.bind_callback(aid, lambda a=aid: calls.append(a))


def test_apply_registers_available_only_and_marks_inert_actions_unavailable():
    mgr, native, _ = make_manager()
    bind_all(mgr, [])
    mgr.bind_callback("hub.open", lambda: None, available=lambda: False)
    statuses = mgr.apply({})
    assert statuses["focus.toggle"] == "global"
    assert statuses["untangle.open"] == "unavailable"   # chưa gắn handler
    assert statuses["hub.open"] == "unavailable"        # available() = False
    assert len(native.registered) == 3
    assert mgr.display_text("focus.toggle") == "Ctrl+Alt+P"
    assert mgr.display_text("untangle.open") == ""


def test_late_bind_registers_immediately():
    mgr, native, _ = make_manager()
    mgr.apply({})
    mgr.bind_callback("untangle.open", lambda: None)
    assert mgr.status("untangle.open") == "global"
    assert "Ctrl+Alt+Space" in native.registered.values()


def test_activation_calls_callback_and_swallows_exceptions():
    mgr, native, _ = make_manager()
    calls = []
    mgr.bind_callback("focus.toggle", lambda: calls.append("ok"))
    mgr.bind_callback("focus.stop", lambda: 1 / 0)
    mgr.apply({})
    native.activated.emit(2)   # focus.toggle
    native.activated.emit(3)   # focus.stop → exception được nuốt + log
    assert calls == ["ok"]


def test_try_rebind_success_updates_overrides():
    mgr, native, _ = make_manager()
    bind_all(mgr, [])
    mgr.apply({})
    assert mgr.try_rebind("focus.toggle", "ctrl+alt+f") == (True, "")
    assert mgr.overrides == {"focus.toggle": {"seq": "Ctrl+Alt+F", "enabled": True}}
    assert sorted(native.registered.values()).count("Ctrl+Alt+F") == 1
    assert "Ctrl+Alt+P" not in native.registered.values()


def test_try_rebind_rejects_invalid_and_app_duplicates():
    mgr, native, _ = make_manager()
    bind_all(mgr, [])
    mgr.apply({})
    assert mgr.try_rebind("focus.toggle", "P") == (False, "invalid")
    assert mgr.try_rebind("focus.toggle", "Alt+Tab") == (False, "invalid")
    assert mgr.try_rebind("focus.toggle", "Ctrl+Alt+X") == (False, "conflict_app")
    assert mgr.sequence("focus.toggle") == "Ctrl+Alt+P" and "Ctrl+Alt+P" in native.registered.values()


def test_try_rebind_os_taken_rolls_back_to_old_key():
    native = FakeBackend(taken=["Ctrl+Alt+F"])
    mgr, native, _ = make_manager(native=native)
    bind_all(mgr, [])
    mgr.apply({})
    assert mgr.try_rebind("focus.toggle", "Ctrl+Alt+F") == (False, "conflict_os")
    assert mgr.sequence("focus.toggle") == "Ctrl+Alt+P"
    assert mgr.status("focus.toggle") == "global"
    assert "Ctrl+Alt+P" in native.registered.values()
    assert mgr.overrides == {}


def test_startup_os_taken_marks_failed_but_registers_app_fallback():
    native = FakeBackend(taken=["Ctrl+Alt+P"])
    mgr, native, app = make_manager(native=native)
    bind_all(mgr, [])
    assert mgr.apply({})["focus.toggle"] == "failed"
    assert "Ctrl+Alt+P" in app.registered.values()


def test_native_backend_load_failure_falls_back_to_app_level():
    app = FakeBackend(is_global=False)

    def boom():
        raise OSError("không nạp được")

    mgr = GlobalHotkeyManager(platform="win32", native_factory=boom, app_factory=lambda: app)
    bind_all(mgr, [])
    assert mgr.apply({})["focus.toggle"] == "app_only"
    assert "Ctrl+Alt+P" in app.registered.values()


def test_set_enabled_unregisters_immediately_and_persists_as_override():
    mgr, native, _ = make_manager()
    bind_all(mgr, [])
    mgr.apply({})
    mgr.set_enabled("pet.toggle", False)
    assert mgr.status("pet.toggle") == "disabled"
    assert "Ctrl+Alt+H" not in native.registered.values()
    assert mgr.overrides["pet.toggle"]["enabled"] is False
    mgr.set_enabled("pet.toggle", True)
    assert mgr.overrides == {} and mgr.status("pet.toggle") == "global"


def test_enabling_disabled_action_whose_key_is_taken_is_refused_with_reason():
    mgr, native, _ = make_manager()
    bind_all(mgr, [])
    mgr.apply({"pet.toggle": {"seq": "Ctrl+Alt+P", "enabled": False}})   # trùng phím mặc định của focus.toggle (đang bật)
    assert mgr.sequence("focus.toggle") == "Ctrl+Alt+P"
    assert mgr.set_enabled("pet.toggle", True) == (False, "conflict_app")
    assert not mgr.is_enabled("pet.toggle") and mgr.status("pet.toggle") == "disabled"
    assert mgr.set_enabled("pet.toggle", False) == (True, "")


def test_reset_restores_default():
    mgr, _, _ = make_manager()
    bind_all(mgr, [])
    mgr.apply({"focus.toggle": {"seq": "Ctrl+Alt+F", "enabled": True}})
    assert mgr.reset("focus.toggle") == (True, "")
    assert mgr.overrides == {}


def test_suspend_and_resume():
    mgr, native, _ = make_manager()
    calls = []
    bind_all(mgr, calls)
    mgr.apply({})
    mgr.suspend()
    assert native.registered == {}
    native.activated.emit(2)
    assert calls == []
    mgr.resume()
    assert len(native.registered) == 3
    assert mgr.try_rebind("focus.toggle", "Ctrl+Alt+F") == (True, "")


def test_duplicate_overrides_keep_first_action_only():
    mgr, native, _ = make_manager()
    bind_all(mgr, [])
    mgr.apply({"focus.stop": {"seq": "Ctrl+Alt+P", "enabled": True}})
    assert mgr.status("focus.toggle") == "global" and mgr.status("focus.stop") == "failed"


def test_unregister_all_and_unknown_action():
    import pytest
    mgr, native, app = make_manager()
    bind_all(mgr, [])
    mgr.apply({})
    mgr.unregister_all()
    assert native.registered == {} and app.registered == {}
    with pytest.raises(KeyError):
        mgr.bind_callback("nope", lambda: None)
