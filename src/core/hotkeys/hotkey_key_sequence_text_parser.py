"""Phân tích văn bản phím Qt portable ("Ctrl+Alt+P") thành (tập modifier, phím) + chuẩn hoá + hiển thị native (thuần)."""

from typing import Optional

MODIFIER_ORDER = ("Ctrl", "Alt", "Shift", "Meta")
_MOD_ALIASES = {"ctrl": "Ctrl", "control": "Ctrl", "alt": "Alt", "shift": "Shift", "meta": "Meta", "win": "Meta"}
_KEY_ALIASES = {"del": "Del", "delete": "Del", "ins": "Ins", "insert": "Ins", "esc": "Esc", "escape": "Esc",
                "return": "Return", "enter": "Return", "pgup": "PgUp", "pageup": "PgUp", "pgdown": "PgDown",
                "pagedown": "PgDown", "space": "Space", "tab": "Tab", "backspace": "Backspace",
                "home": "Home", "end": "End", "left": "Left", "right": "Right", "up": "Up", "down": "Down"}
_MAC_GLYPHS = {"Meta": "⌃", "Alt": "⌥", "Shift": "⇧", "Ctrl": "⌘"}   # thứ tự hiển thị chuẩn macOS: ⌃⌥⇧⌘
_MAC_ORDER = ("Meta", "Alt", "Shift", "Ctrl")


def parse_key_sequence(text: str) -> Optional[tuple[frozenset, str]]:
    """Trả (modifiers, key) cho đúng 1 tổ hợp; None nếu rỗng / nhiều tổ hợp / không có phím chính / lặp modifier."""
    text = (text or "").strip()
    if not text or ", " in text:   # "A, B" = chuỗi nhiều tổ hợp
        return None
    parts = text.split("+")
    key = parts.pop()
    if key == "" and parts and parts[-1] == "":   # "Ctrl++" → phím "+"
        parts.pop()
        key = "+"
    mods: list[str] = []
    for part in parts:
        mod = _MOD_ALIASES.get(part.strip().lower())
        if mod is None or mod in mods:
            return None
        mods.append(mod)
    key = key.strip()
    if not key or key.lower() in _MOD_ALIASES:
        return None
    lowered = key.lower()
    if lowered in _KEY_ALIASES:
        key = _KEY_ALIASES[lowered]
    elif len(key) == 1:
        key = key.upper()
    elif lowered.startswith("f") and lowered[1:].isdigit():
        key = lowered.upper()
    return frozenset(mods), key


def normalize_key_sequence(text: str) -> Optional[str]:
    """Dạng chuẩn "Ctrl+Alt+Shift+Meta+Key" để so sánh trùng; None nếu không hợp lệ."""
    parsed = parse_key_sequence(text)
    if parsed is None:
        return None
    mods, key = parsed
    return "+".join([m for m in MODIFIER_ORDER if m in mods] + [key])


def native_display_text(text: str, platform: str) -> str:
    """Văn bản hiển thị theo OS: mac → "⌃⌥⌘Space"; Windows → "Ctrl+Alt+P" (Meta → "Win")."""
    parsed = parse_key_sequence(text)
    if parsed is None:
        return text or ""
    mods, key = parsed
    if platform == "darwin":
        return "".join(_MAC_GLYPHS[m] for m in _MAC_ORDER if m in mods) + key
    return "+".join([("Win" if m == "Meta" else m) for m in MODIFIER_ORDER if m in mods] + [key])
