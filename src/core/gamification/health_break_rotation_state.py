"""Trạng thái xoay vòng gợi ý sức khỏe (lưu KV): loại đã gợi ý gần nhất + lần cuối uống nước / vận động."""

from datetime import datetime, timezone
from typing import List, Optional

from src.core.app_state_key_value_store import KeyValueStore

KV_KEY = "health_break.state_v1"
KEEP_RECENT = 4


def _minutes_since(iso: Optional[str], now: datetime) -> Optional[float]:
    if not iso:
        return None
    try:
        then = datetime.fromisoformat(iso)
    except ValueError:
        return None   # giá trị hỏng → coi như chưa biết
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    return max(0.0, (now - then).total_seconds() / 60)


class HealthBreakRotationState:
    def __init__(self, kv: KeyValueStore):
        self._kv = kv

    def _load(self) -> dict:
        data = self._kv.get_json(KV_KEY, {})
        return data if isinstance(data, dict) else {}

    def recent_kinds(self) -> List[str]:
        kinds = self._load().get("recent_kinds")
        return [k for k in kinds if isinstance(k, str)] if isinstance(kinds, list) else []

    def minutes_since_water(self, now: datetime) -> Optional[float]:
        return _minutes_since(self._load().get("last_water_at"), now)

    def minutes_since_move(self, now: datetime) -> Optional[float]:
        return _minutes_since(self._load().get("last_move_at"), now)

    def record_shown(self, kind: str) -> None:
        """Ghi loại vừa gợi ý (kể cả khi bị bỏ qua) để lần sau không lặp."""
        data = self._load()
        data["recent_kinds"] = (self.recent_kinds() + [kind])[-KEEP_RECENT:]
        self._kv.set_json(KV_KEY, data)

    def record_done(self, kind: str, now: datetime) -> None:
        data = self._load()
        if kind == "water":
            data["last_water_at"] = now.isoformat()
        elif kind in ("move", "posture"):
            data["last_move_at"] = now.isoformat()
        self._kv.set_json(KV_KEY, data)

    def recent_action_ids(self) -> List[str]:
        actions = self._load().get("recent_action_ids")
        return [a for a in actions if isinstance(a, str)] if isinstance(actions, list) else []

    def record_shown_action(self, action_id: str) -> None:
        data = self._load()
        data["recent_action_ids"] = (self.recent_action_ids() + [action_id])[-KEEP_RECENT:]
        self._kv.set_json(KV_KEY, data)

    def exercise_count_today(self, now: datetime) -> int:
        data = self._load()
        today_str = now.date().isoformat()
        if data.get("exercise_date") != today_str:
            return 0
        return int(data.get("exercise_count", 0))

    def record_exercise_done(self, now: datetime) -> int:
        data = self._load()
        today_str = now.date().isoformat()
        count = data.get("exercise_count", 0) if data.get("exercise_date") == today_str else 0
        new_count = count + 1
        data["exercise_date"] = today_str
        data["exercise_count"] = new_count
        data["last_move_at"] = now.isoformat()
        self._kv.set_json(KV_KEY, data)
        return new_count
