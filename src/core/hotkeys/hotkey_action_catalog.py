"""Danh mục hành động phím tắt (dữ liệu thuần): id, khoá i18n của nhãn, phím mặc định cho Windows và macOS.

Văn bản phím theo định dạng Qt portable. Trên macOS Qt đảo nghĩa: `Ctrl` = ⌘ Cmd, `Meta` = ⌃ Control.
Mặc định mac tránh các tổ hợp hệ thống: ⌃Space/⌃⌥Space (đổi bộ gõ), ⌘⌥Space (Finder), ⌃⌘Space (emoji).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class HotkeyAction:
    id: str
    label_key: str       # khoá i18n của nhãn hiển thị trong Cài đặt
    default_win: str     # phím mặc định Windows / Linux (Qt text)
    default_mac: str     # phím mặc định macOS (Qt text, Meta = ⌃)

    def default_for(self, platform: str) -> str:
        return self.default_mac if platform == "darwin" else self.default_win


HOTKEY_ACTIONS: tuple[HotkeyAction, ...] = (
    HotkeyAction("untangle.open", "hotkey_action_untangle_open", "Ctrl+Alt+Space", "Ctrl+Alt+Meta+Space"),
    HotkeyAction("focus.toggle", "hotkey_action_focus_toggle", "Ctrl+Alt+P", "Meta+Alt+P"),
    HotkeyAction("focus.stop", "hotkey_action_focus_stop", "Ctrl+Alt+X", "Meta+Alt+X"),
    HotkeyAction("break.start", "hotkey_action_break_start", "Ctrl+Alt+B", "Meta+Alt+B"),
    HotkeyAction("dashboard.open", "hotkey_action_dashboard_open", "Ctrl+Alt+D", "Meta+Alt+D"),
    HotkeyAction("quick_chat.open", "hotkey_action_quick_chat_open", "Ctrl+Alt+C", "Meta+Alt+C"),
    HotkeyAction("parking.quick_park", "hotkey_action_quick_park", "Ctrl+Alt+N", "Meta+Alt+N"),
    HotkeyAction("pet.toggle", "hotkey_action_pet_toggle", "Ctrl+Alt+H", "Meta+Alt+H"),
    HotkeyAction("hub.open", "hotkey_action_hub_open", "Ctrl+Alt+G", "Meta+Alt+G"),
    HotkeyAction("meeting.toggle", "hotkey_action_meeting_toggle", "Ctrl+Alt+M", "Meta+Alt+M"),
)

ACTIONS_BY_ID: dict[str, HotkeyAction] = {a.id: a for a in HOTKEY_ACTIONS}
