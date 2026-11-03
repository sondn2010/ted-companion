"""Mô hình + đọc/ghi `skin_unlock_registry.json`: điều kiện mở khoá TỪNG nhân vật bundle sẵn (không phụ thuộc Qt/config).

Định dạng file (dev sửa tay được, script KHÔNG ghi đè điều kiện đã có):
    {"version": 1, "skins": [{"key": "pack/char", "pack": "pack", "name_vi": "...", "name_en": "...",
                              "unlock": {"type": "badges", "count": 5}}]}
Điều kiện (`unlock`):
    {"type": "free"}                                   mở ngay
    {"type": "badges", "count": N}                     số huy hiệu khác nhau đã mở >= N
    {"type": "badge", "id": "focus_day_gold"}          đã có huy hiệu cụ thể
    {"type": "metric", "metric": "<tên>", "value": N}  chỉ số trọn đời >= N (xem METRIC_LABELS)
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger("ted")

REGISTRY_FILE_NAME = "skin_unlock_registry.json"
CONDITION_TYPES = ("free", "badges", "badge", "metric")

# Chỉ số trọn đời dùng được trong điều kiện: (nhãn vi, nhãn en) — "Làm {n} <nhãn>"
METRIC_LABELS = {
    "focus_sessions": ("phiên Deep Work", "deep-work sessions"),
    "focus_minutes": ("phút tập trung", "focus minutes"),
    "tasks_done": ("việc hoàn thành", "tasks done"),
    "quiz_answered": ("bài tập đã làm", "exercises done"),
    "quiz_correct": ("câu trả lời đúng", "correct answers"),
    "writing_graded": ("bài viết đã chấm", "writing submissions"),
    "agenda_done": ("mục lịch học hoàn thành", "study agenda items done"),
    "untangle_sessions": ("phiên Gỡ Rối ý tưởng", "idea-untangling sessions"),
    "peak_level": ("level cao nhất", "peak level"),
    "best_streak_days": ("ngày liên tiếp (streak)", "streak days"),
    "active_days": ("ngày hoạt động", "active days"),
    "outings": ("lần đi chơi/ra ngoài", "outings"),
    "xp_total": ("XP tích luỹ", "total XP"),
}


@dataclass(frozen=True)
class SkinCondition:
    type: str = "free"
    count: int = 0          # type=badges
    metric: str = ""        # type=metric
    value: float = 0        # type=metric
    badge_id: str = ""      # type=badge

    def to_json(self) -> dict:
        if self.type == "badges":
            return {"type": "badges", "count": self.count}
        if self.type == "badge":
            return {"type": "badge", "id": self.badge_id}
        if self.type == "metric":
            return {"type": "metric", "metric": self.metric, "value": int(self.value)}
        return {"type": "free"}


def parse_condition(raw) -> Optional[SkinCondition]:
    """None nếu sai định dạng (caller bỏ qua + log) — không bao giờ mở nhầm miễn phí."""
    if not isinstance(raw, dict):
        return None
    kind = raw.get("type")
    try:
        if kind == "free":
            return SkinCondition("free")
        if kind == "badges" and int(raw["count"]) >= 0:
            return SkinCondition("badges", count=int(raw["count"]))
        if kind == "badge" and str(raw["id"]).strip():
            return SkinCondition("badge", badge_id=str(raw["id"]).strip())
        if kind == "metric" and raw["metric"] in METRIC_LABELS and float(raw["value"]) >= 0:
            return SkinCondition("metric", metric=raw["metric"], value=float(raw["value"]))
    except (KeyError, TypeError, ValueError):
        pass
    return None


@dataclass(frozen=True)
class UnlockableSkin:
    key: str                # "pack/character"
    pack: str
    name_vi: str
    name_en: str
    condition: SkinCondition

    def to_json(self) -> dict:
        return {"key": self.key, "pack": self.pack, "name_vi": self.name_vi, "name_en": self.name_en,
                "unlock": self.condition.to_json()}


def skin_key(pack_id: str, char_id: str) -> str:
    # '/' không bao giờ xuất hiện trong key 6 con vật gốc. Luôn viết thường: set_character / MCP hạ chữ thường
    # khoá nhận vào, nên key chứa chữ hoa sẽ không bao giờ chọn được.
    return f"{pack_id}/{char_id}".lower()


def read_registry(path: Path) -> list[UnlockableSkin]:
    """Registry thiếu/hỏng → []. Entry hỏng bị bỏ qua + log (nhân vật đó sẽ được gán điều kiện tự động)."""
    path = Path(path)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.error("Không đọc được %s: %s", path, exc)
        return []
    skins, seen = [], set()
    for raw in (data.get("skins") if isinstance(data, dict) else None) or []:
        condition = parse_condition(raw.get("unlock")) if isinstance(raw, dict) else None
        key = str(raw.get("key") or "").strip().lower() if isinstance(raw, dict) else ""   # cùng quy tắc với skin_key()
        if condition is None or "/" not in key or key in seen:
            logger.warning("Bỏ qua entry registry skin không hợp lệ: %r", raw)
            continue
        seen.add(key)
        pack = str(raw.get("pack") or key.split("/", 1)[0])
        skins.append(UnlockableSkin(key, pack, str(raw.get("name_vi") or key), str(raw.get("name_en") or key),
                                    condition))
    return skins


def write_registry(path: Path, skins: list[UnlockableSkin]) -> None:
    payload = {"version": 1, "skins": [s.to_json() for s in skins]}
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
