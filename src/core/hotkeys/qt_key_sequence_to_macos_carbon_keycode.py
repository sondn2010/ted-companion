"""Văn bản phím Qt → (modifier Carbon, mã kVK) cho RegisterEventHotKey (thuần) + helper fourcc.

Qt trên macOS: `Ctrl` = ⌘ (cmdKey), `Meta` = ⌃ (controlKey).
"""

from typing import Optional

from src.core.hotkeys.hotkey_key_sequence_text_parser import parse_key_sequence

CMD_KEY, SHIFT_KEY, OPTION_KEY, CONTROL_KEY = 0x100, 0x200, 0x800, 0x1000

_KVK = {
    "A": 0x00, "S": 0x01, "D": 0x02, "F": 0x03, "H": 0x04, "G": 0x05, "Z": 0x06, "X": 0x07, "C": 0x08,
    "V": 0x09, "B": 0x0B, "Q": 0x0C, "W": 0x0D, "E": 0x0E, "R": 0x0F, "Y": 0x10, "T": 0x11,
    "1": 0x12, "2": 0x13, "3": 0x14, "4": 0x15, "6": 0x16, "5": 0x17, "=": 0x18, "9": 0x19, "7": 0x1A,
    "-": 0x1B, "8": 0x1C, "0": 0x1D, "]": 0x1E, "O": 0x1F, "U": 0x20, "[": 0x21, "I": 0x22, "P": 0x23,
    "L": 0x25, "J": 0x26, "'": 0x27, "K": 0x28, ";": 0x29, "\\": 0x2A, ",": 0x2B, "/": 0x2C,
    "N": 0x2D, "M": 0x2E, ".": 0x2F, "`": 0x32,
    "Return": 0x24, "Tab": 0x30, "Space": 0x31, "Backspace": 0x33, "Esc": 0x35, "Del": 0x75, "Ins": 0x72,
    "Home": 0x73, "End": 0x77, "PgUp": 0x74, "PgDown": 0x79,
    "Left": 0x7B, "Right": 0x7C, "Down": 0x7D, "Up": 0x7E,
    "F1": 0x7A, "F2": 0x78, "F3": 0x63, "F4": 0x76, "F5": 0x60, "F6": 0x61, "F7": 0x62, "F8": 0x64,
    "F9": 0x65, "F10": 0x6D, "F11": 0x67, "F12": 0x6F, "F13": 0x69, "F14": 0x6B, "F15": 0x71,
    "F16": 0x6A, "F17": 0x40, "F18": 0x4F, "F19": 0x50, "F20": 0x5A,
}


def fourcc(code: str) -> int:
    """OSType 4 ký tự → số nguyên big-endian, vd fourcc('TEDh')."""
    raw = code.encode("ascii")
    if len(raw) != 4:
        raise ValueError(f"fourcc cần đúng 4 ký tự: {code!r}")
    return int.from_bytes(raw, "big")


def to_carbon_modifiers_keycode(seq: str) -> Optional[tuple[int, int]]:
    """"Meta+Alt+P" → (controlKey|optionKey, 0x23); None nếu phím chưa hỗ trợ."""
    parsed = parse_key_sequence(seq)
    if parsed is None or parsed[1] not in _KVK:
        return None
    mods, key = parsed
    flags = 0
    for name, bit in (("Ctrl", CMD_KEY), ("Meta", CONTROL_KEY), ("Alt", OPTION_KEY), ("Shift", SHIFT_KEY)):
        if name in mods:
            flags |= bit
    return flags, _KVK[key]
