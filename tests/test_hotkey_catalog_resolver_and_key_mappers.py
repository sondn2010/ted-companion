"""Test thuần cho phím tắt: danh mục, resolver, validator, trùng phím, mapper Win32 / Carbon, fourcc."""

from src.core.hotkeys.hotkey_action_catalog import HOTKEY_ACTIONS
from src.core.hotkeys.hotkey_binding_resolution_and_conflicts import (
    Binding, conflicting_action, find_duplicates, overrides_from_bindings, resolve_bindings, validate_sequence,
)
from src.core.hotkeys.hotkey_key_sequence_text_parser import native_display_text, normalize_key_sequence
from src.core.hotkeys.qt_key_sequence_to_macos_carbon_keycode import (
    CMD_KEY, CONTROL_KEY, OPTION_KEY, fourcc, to_carbon_modifiers_keycode,
)
from src.core.hotkeys.qt_key_sequence_to_win32_modifiers_vk import (
    MOD_ALT, MOD_CONTROL, MOD_NOREPEAT, MOD_WIN, to_win32_modifiers_vk,
)


def test_catalog_defaults_valid_and_unique_on_both_platforms():
    for platform in ("win32", "darwin"):
        seqs = [normalize_key_sequence(a.default_for(platform)) for a in HOTKEY_ACTIONS]
        assert len(set(seqs)) == len(seqs)
        assert all(validate_sequence(a.default_for(platform), platform)[0] for a in HOTKEY_ACTIONS)
        assert find_duplicates(resolve_bindings({}, platform)) == {}


def test_resolve_bindings_applies_overrides_and_ignores_malformed():
    result = resolve_bindings({
        "focus.toggle": {"seq": "ctrl+alt+f", "enabled": False},
        "focus.stop": {"seq": "X"},          # thiếu modifier → dùng mặc định
        "break.start": "rác",                # sai kiểu
        "unknown.action": {"seq": "Ctrl+Alt+Q"},
    }, "win32")
    assert result["focus.toggle"] == Binding("Ctrl+Alt+F", False)
    assert result["focus.stop"].seq == "Ctrl+Alt+X"
    assert result["break.start"].seq == "Ctrl+Alt+B"
    assert "unknown.action" not in result
    assert resolve_bindings("không phải dict", "win32")["untangle.open"].seq == "Ctrl+Alt+Space"


def test_validate_sequence_rules():
    assert validate_sequence("Ctrl+Alt+P", "win32") == (True, "")
    assert validate_sequence("P", "win32") == (False, "invalid")
    assert validate_sequence("Shift+P", "win32") == (False, "invalid")
    assert validate_sequence("Ctrl+K, Ctrl+C", "win32") == (False, "invalid")
    assert validate_sequence("", "win32") == (False, "invalid")
    assert validate_sequence("Alt+Tab", "win32") == (False, "reserved")
    assert validate_sequence("Ctrl+Alt+Del", "win32") == (False, "reserved")
    assert validate_sequence("Ctrl+Space", "darwin") == (False, "reserved")   # ⌘Space
    assert validate_sequence("Ctrl+Space", "win32")[0] is True


def test_duplicates_and_conflicting_action_ignore_disabled():
    b = resolve_bindings({}, "win32")
    assert conflicting_action(b, "focus.toggle", "ctrl+alt+x") == "focus.stop"
    b["focus.stop"] = Binding("Ctrl+Alt+X", False)
    assert conflicting_action(b, "focus.toggle", "Ctrl+Alt+X") is None
    b["focus.stop"] = Binding("Ctrl+Alt+P", True)
    assert find_duplicates(b) == {"Ctrl+Alt+P": ["focus.toggle", "focus.stop"]}


def test_overrides_from_bindings_only_non_default():
    b = resolve_bindings({}, "win32")
    assert overrides_from_bindings(b, "win32") == {}
    b["pet.toggle"] = Binding("Ctrl+Alt+J", True)
    b["hub.open"] = Binding("Ctrl+Alt+G", False)
    assert overrides_from_bindings(b, "win32") == {
        "pet.toggle": {"seq": "Ctrl+Alt+J", "enabled": True}, "hub.open": {"seq": "Ctrl+Alt+G", "enabled": False}}


def test_win32_mapper():
    assert to_win32_modifiers_vk("Ctrl+Alt+P") == (MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, 0x50)
    assert to_win32_modifiers_vk("Ctrl+Alt+Space") == (MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, 0x20)
    assert to_win32_modifiers_vk("Meta+F5") == (MOD_WIN | MOD_NOREPEAT, 0x74)
    assert to_win32_modifiers_vk("Ctrl+Alt+7")[1] == 0x37
    assert to_win32_modifiers_vk("Ctrl+Alt+Left")[1] == 0x25
    assert to_win32_modifiers_vk("Ctrl+Alt+F24")[1] == 0x87
    assert to_win32_modifiers_vk("Ctrl+Alt+F25") is None
    assert to_win32_modifiers_vk("Ctrl+Alt+€") is None
    assert to_win32_modifiers_vk("") is None


def test_carbon_mapper_qt_ctrl_is_cmd_and_meta_is_control():
    assert to_carbon_modifiers_keycode("Meta+Alt+P") == (CONTROL_KEY | OPTION_KEY, 0x23)
    assert to_carbon_modifiers_keycode("Ctrl+Alt+Meta+Space") == (CMD_KEY | OPTION_KEY | CONTROL_KEY, 0x31)
    assert to_carbon_modifiers_keycode("Ctrl+F1") == (CMD_KEY, 0x7A)
    assert to_carbon_modifiers_keycode("Ctrl+Alt+F25") is None


def test_fourcc():
    assert fourcc("TEDh") == 0x54454468
    assert fourcc("----") == 0x2D2D2D2D


def test_native_display_text():
    assert native_display_text("Ctrl+Alt+Meta+Space", "darwin") == "⌃⌥⌘Space"
    assert native_display_text("Meta+Alt+P", "darwin") == "⌃⌥P"
    assert native_display_text("Ctrl+Alt+P", "win32") == "Ctrl+Alt+P"
    assert native_display_text("Meta+Shift+P", "win32") == "Shift+Win+P"
