"""Gắn gợi ý phím tắt vào nhãn menu: QMenu hiển thị phần sau '\\t' ở cột phím tắt (không dùng QAction.setShortcut
để tránh 1 phím tắt thứ hai tranh chấp với đăng ký toàn cục)."""

from src.core.hotkeys.global_hotkey_manager import hotkey_manager


def with_hotkey_hint(label: str, action_id: str) -> str:
    """"⏸ Tạm dừng" + "focus.toggle" → "⏸ Tạm dừng\\tCtrl+Alt+P"; không có phím (tắt/chưa khả dụng) → giữ nguyên nhãn."""
    hint = hotkey_manager.display_text(action_id)
    return f"{label}\t{hint}" if hint else label
