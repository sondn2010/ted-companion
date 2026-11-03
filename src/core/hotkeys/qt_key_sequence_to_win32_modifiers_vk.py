"""Văn bản phím Qt → (modifier Win32, mã VK) cho RegisterHotKey (thuần)."""

from typing import Optional

from src.core.hotkeys.hotkey_key_sequence_text_parser import parse_key_sequence

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x0001, 0x0002, 0x0004, 0x0008, 0x4000

_NAMED_VK = {
    "Space": 0x20, "Tab": 0x09, "Return": 0x0D, "Esc": 0x1B, "Backspace": 0x08,
    "PgUp": 0x21, "PgDown": 0x22, "End": 0x23, "Home": 0x24,
    "Left": 0x25, "Up": 0x26, "Right": 0x27, "Down": 0x28, "Ins": 0x2D, "Del": 0x2E,
    ";": 0xBA, "=": 0xBB, ",": 0xBC, "-": 0xBD, ".": 0xBE, "/": 0xBF, "`": 0xC0,
    "[": 0xDB, "\\": 0xDC, "]": 0xDD, "'": 0xDE,
}


def _vk_for_key(key: str) -> Optional[int]:
    if key in _NAMED_VK:
        return _NAMED_VK[key]
    if len(key) == 1 and key.isascii() and key.isalnum():
        return ord(key)   # 'A'-'Z' (đã upper) và '0'-'9' trùng mã VK
    if key.startswith("F") and key[1:].isdigit() and 1 <= int(key[1:]) <= 24:
        return 0x70 + int(key[1:]) - 1
    return None


def to_win32_modifiers_vk(seq: str) -> Optional[tuple[int, int]]:
    """"Ctrl+Alt+P" → (MOD_CONTROL|MOD_ALT|MOD_NOREPEAT, 0x50); None nếu phím chưa hỗ trợ. Meta → phím Windows."""
    parsed = parse_key_sequence(seq)
    if parsed is None:
        return None
    mods, key = parsed
    vk = _vk_for_key(key)
    if vk is None:
        return None
    flags = MOD_NOREPEAT
    for name, bit in (("Ctrl", MOD_CONTROL), ("Alt", MOD_ALT), ("Shift", MOD_SHIFT), ("Meta", MOD_WIN)):
        if name in mods:
            flags |= bit
    return flags, vk
