"""Test phase 02: settings.hotkeys round-trip, card Phím tắt (offscreen), gợi ý phím trong menu, wiring callback."""

import json
from types import SimpleNamespace

from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QMenu

from src.config import AppConfig, settings
from src.core.hotkeys.global_hotkey_manager import GlobalHotkeyManager, hotkey_manager
from src.core.hotkeys.hotkey_action_catalog import ACTIONS_BY_ID
from src.core.i18n import TRANSLATIONS, i18n
from tests.qt_offscreen_app_helper import get_qapp
from tests.test_global_hotkey_manager_with_fake_backends import FakeBackend


def make_manager():
    native, app = FakeBackend(), FakeBackend(is_global=False)
    return GlobalHotkeyManager(platform="win32", native_factory=lambda: native, app_factory=lambda: app), native


def test_settings_hotkeys_round_trip_and_malformed_dropped(tmp_path):
    (tmp_path / "settings.json").write_text(json.dumps({
        "schema_version": 2,
        "hotkeys": {"focus.toggle": {"seq": "Ctrl+Alt+F", "enabled": True}, "bad": "x", "n": 5},
    }), encoding="utf-8")
    cfg = AppConfig(data_dir=tmp_path)
    assert cfg.hotkeys == {"focus.toggle": {"seq": "Ctrl+Alt+F", "enabled": True}}
    cfg.hotkeys = {}
    cfg.save()
    assert json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))["hotkeys"] == {}
    (tmp_path / "settings.json").write_text(json.dumps({"schema_version": 2, "hotkeys": "rác"}), encoding="utf-8")
    assert AppConfig(data_dir=tmp_path).hotkeys == {}


def test_i18n_hotkey_keys_have_vi_en_parity():
    keys = {a.label_key for a in ACTIONS_BY_ID.values()}
    keys |= {"settings_hotkeys_group_title", "settings_hotkey_conflict_app", "settings_hotkey_conflict_os",
             "settings_hotkey_invalid", "hotkey_status_global", "hotkey_status_app_only", "hotkey_status_failed",
             "hotkey_status_disabled", "settings_hotkey_reset_all", "settings_hotkeys_hint", "settings_hotkeys_mac_note"}
    for key in keys:
        assert key in TRANSLATIONS["vi"] and key in TRANSLATIONS["en"], key


def test_card_rebind_conflict_reset_disable_and_persist(monkeypatch):
    get_qapp()
    from src.ui.dashboard_tabs.hotkey_settings_group_widget import HotkeySettingsGroupWidget
    saves = []
    monkeypatch.setattr(settings, "hotkeys", {})
    monkeypatch.setattr(settings, "save", lambda: saves.append(json.dumps(settings.hotkeys, sort_keys=True)))
    mgr, native = make_manager()
    for aid in ("focus.toggle", "focus.stop", "pet.toggle"):
        mgr.bind_callback(aid, lambda: None)
    mgr.apply({})
    group = HotkeySettingsGroupWidget(mgr)
    rows = {r.action.id: r for r in group._rows}
    assert set(rows) == {"focus.toggle", "focus.stop", "pet.toggle"}   # chỉ hành động khả dụng

    row = rows["focus.toggle"]
    row.edit.setKeySequence(QKeySequence("Ctrl+Alt+F"))
    row._on_editing_finished()
    assert settings.hotkeys == {"focus.toggle": {"seq": "Ctrl+Alt+F", "enabled": True}} and saves

    row.edit.setKeySequence(QKeySequence("Ctrl+Alt+X"))   # trùng focus.stop
    row._on_editing_finished()
    assert not row.lbl_warning.isHidden()
    assert row.edit.keySequence().toString() == "Ctrl+Alt+F"   # ô trả về phím cũ
    assert "Ctrl+Alt+F" in native.registered.values()

    row._on_reset_clicked()
    assert settings.hotkeys == {} and row.lbl_warning.isHidden()
    assert row.edit.keySequence().toString() == "Ctrl+Alt+P"

    rows["pet.toggle"].chk_enabled.setChecked(False)
    assert "Ctrl+Alt+H" not in native.registered.values()
    assert settings.hotkeys["pet.toggle"]["enabled"] is False
    group._on_reset_all()
    assert settings.hotkeys == {} and "Ctrl+Alt+H" in native.registered.values()


def test_card_focus_suspends_and_resumes_and_rebuilds_when_action_becomes_available():
    get_qapp()
    from src.ui.dashboard_tabs.hotkey_settings_group_widget import HotkeySettingsGroupWidget
    mgr, native = make_manager()
    mgr.bind_callback("focus.toggle", lambda: None)
    mgr.apply({})
    group = HotkeySettingsGroupWidget(mgr)
    row = group._rows[0]
    row.edit.focus_changed.emit(True)
    assert native.registered == {}
    row.edit.focus_changed.emit(False)
    assert len(native.registered) == 1
    mgr.bind_callback("hub.open", lambda: None)   # gắn muộn → card dựng thêm dòng
    assert {r.action.id for r in group._rows} == {"focus.toggle", "hub.open"}


def test_menu_hint_appended_only_when_bound(monkeypatch):
    get_qapp()
    from src.ui.hotkey_menu_label_hint import with_hotkey_hint
    mgr, _ = make_manager()
    mgr.bind_callback("focus.toggle", lambda: None)
    monkeypatch.setattr("src.ui.hotkey_menu_label_hint.hotkey_manager", mgr)
    assert with_hotkey_hint("⏸ Tạm dừng", "focus.toggle") == "⏸ Tạm dừng"   # chưa apply → chưa có phím
    mgr.apply({})
    assert with_hotkey_hint("⏸ Tạm dừng", "focus.toggle") == "⏸ Tạm dừng\tCtrl+Alt+P"
    assert with_hotkey_hint("x", "focus.stop") == "x"   # chưa gắn callback → không gợi ý


def test_context_menu_shows_hint_for_pomodoro(monkeypatch):
    get_qapp()
    from src.ui.companion_context_menu_builder import _add
    mgr, _ = make_manager()
    mgr.bind_callback("focus.toggle", lambda: None)
    mgr.apply({})
    monkeypatch.setattr("src.ui.hotkey_menu_label_hint.hotkey_manager", mgr)
    menu = QMenu()
    action = _add(menu, "⏸ Tạm dừng Pomodoro", lambda: None, "focus.toggle")
    assert action.text() == "⏸ Tạm dừng Pomodoro\tCtrl+Alt+P"
    assert _add(menu, "Không phím", lambda: None).text() == "Không phím"


def test_default_wiring_binds_actions_and_hub_availability():
    get_qapp()
    from src.ui.hotkey_default_action_callbacks_wiring import wire_default_hotkey_actions
    calls = []
    focus = SimpleNamespace(pause_or_resume=lambda: calls.append("pause"),
                            stop_session=lambda completed: calls.append(("stop", completed)),
                            start_break=lambda: calls.append("break"))
    quick = SimpleNamespace(open_for=lambda mid: calls.append(("chat", mid)), activateWindow=lambda: None,
                            focus_parking_input=lambda: calls.append("park"))
    ctx = SimpleNamespace(focus_engine=focus, quick_chat=quick, dashboard=SimpleNamespace(),
                          registry=SimpleNamespace(active=lambda: SimpleNamespace(id="coach1")))
    companion = SimpleNamespace(open_dashboard=lambda: calls.append("dash"), _position_popup_near_ted=lambda: None)
    tray = SimpleNamespace(toggle_companion=lambda: calls.append("pet"))
    mgr, native = make_manager()
    wire_default_hotkey_actions(ctx, companion, tray, mgr)
    statuses = mgr.apply({})
    assert statuses["untangle.open"] == "unavailable" and statuses["hub.open"] == "unavailable"
    assert statuses["quick_chat.open"] == "global"
    for int_id in range(1, 10):
        native.activated.emit(int_id)
    assert calls == ["pause", ("stop", False), "break", "dash", ("chat", "coach1"), ("chat", "coach1"), "park", "pet"]
    ctx.dashboard.open_hub = lambda: calls.append("hub")
    mgr.apply({})
    assert mgr.status("hub.open") == "global"


def test_card_retranslates_on_language_switch():
    get_qapp()
    from src.ui.dashboard_tabs.hotkey_settings_group_widget import HotkeySettingsGroupWidget
    group = HotkeySettingsGroupWidget(hotkey_manager)
    i18n.set_language("en")
    group.retranslate_ui()
    assert "shortcuts" in group.lbl_title.text()
    i18n.set_language("vi")
    group.retranslate_ui()
    assert "Phím tắt" in group.lbl_title.text()
