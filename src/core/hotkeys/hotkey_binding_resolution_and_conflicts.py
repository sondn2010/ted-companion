"""Gộp mặc định ⊕ override, kiểm tra hợp lệ / phím dành riêng của OS, phát hiện trùng trong app (thuần, không Qt)."""

from dataclasses import dataclass
from typing import Optional

from src.core.hotkeys.hotkey_action_catalog import ACTIONS_BY_ID, HOTKEY_ACTIONS
from src.core.hotkeys.hotkey_key_sequence_text_parser import normalize_key_sequence, parse_key_sequence

# Tổ hợp OS giữ riêng (dạng chuẩn hoá; trên mac Ctrl = ⌘)
_RESERVED = {
    "win32": {"Ctrl+Alt+Del", "Alt+Tab", "Alt+F4", "Meta+L"},
    "darwin": {"Ctrl+Space", "Ctrl+Tab", "Ctrl+Q"},
}


@dataclass(frozen=True)
class Binding:
    seq: str
    enabled: bool = True


def validate_sequence(seq: str, platform: str) -> tuple[bool, str]:
    """(ok, reason). reason ∈ "" | "invalid" | "reserved". Cần đúng 1 tổ hợp có ít nhất 1 trong Ctrl/Alt/Meta."""
    parsed = parse_key_sequence(seq)
    if parsed is None or not (parsed[0] & {"Ctrl", "Alt", "Meta"}):
        return False, "invalid"
    if normalize_key_sequence(seq) in _RESERVED.get(platform, set()):
        return False, "reserved"
    return True, ""


def resolve_bindings(overrides: Optional[dict], platform: str) -> dict[str, Binding]:
    """Mặc định ⊕ override ({id: {"seq","enabled"}}); mục lạ / sai kiểu / seq không hợp lệ bị bỏ qua (dùng mặc định)."""
    overrides = overrides if isinstance(overrides, dict) else {}
    result: dict[str, Binding] = {}
    for action in HOTKEY_ACTIONS:
        default = action.default_for(platform)
        item = overrides.get(action.id)
        seq, enabled = default, True
        if isinstance(item, dict):
            cand = item.get("seq")
            if isinstance(cand, str) and validate_sequence(cand, platform)[0]:
                seq = normalize_key_sequence(cand) or default
            if isinstance(item.get("enabled"), bool):
                enabled = item["enabled"]
        result[action.id] = Binding(seq, enabled)
    return result


def find_duplicates(bindings: dict[str, Binding]) -> dict[str, list[str]]:
    """{tổ hợp chuẩn hoá: [action id...]} chỉ gồm tổ hợp bị ≥2 hành động đang bật dùng chung."""
    groups: dict[str, list[str]] = {}
    for action_id, b in bindings.items():
        norm = normalize_key_sequence(b.seq)
        if b.enabled and norm:
            groups.setdefault(norm, []).append(action_id)
    return {seq: ids for seq, ids in groups.items() if len(ids) > 1}


def conflicting_action(bindings: dict[str, Binding], action_id: str, seq: str) -> Optional[str]:
    """Hành động KHÁC đang bật đã dùng `seq`; None nếu không trùng."""
    norm = normalize_key_sequence(seq)
    for other_id, b in bindings.items():
        if other_id != action_id and b.enabled and norm and normalize_key_sequence(b.seq) == norm:
            return other_id
    return None


def overrides_from_bindings(bindings: dict[str, Binding], platform: str) -> dict:
    """Chỉ giữ phần khác mặc định để lưu vào settings.hotkeys; trả {} khi mọi thứ là mặc định."""
    out: dict = {}
    for action_id, b in bindings.items():
        default = normalize_key_sequence(ACTIONS_BY_ID[action_id].default_for(platform))
        if normalize_key_sequence(b.seq) != default or not b.enabled:
            out[action_id] = {"seq": b.seq, "enabled": b.enabled}
    return out
