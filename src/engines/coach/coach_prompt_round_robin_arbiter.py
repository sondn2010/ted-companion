"""Phân xử luân phiên giữa nhiều module coach để module ưu tiên cao không bỏ đói module sau (Red Team #11).

Chỉ 1 bong bóng tại 1 thời điểm. Module bị chặn vì bong bóng bận được ghi vào `waiting`; trong số đang
chờ, module có `last_prompted_at` cũ nhất (chưa từng nhắc = cũ nhất) được nhắc trước.
`waiting` KHÔNG hết hạn theo thời gian (interval > TTL từng làm module đầu bị bỏ đói); chỉ xoá khi module
được nhắc (record_prompt) hoặc không còn đủ điều kiện / bị tắt (forget)."""

from datetime import datetime, timezone

EPOCH = datetime.min.replace(tzinfo=timezone.utc)


class RoundRobinArbiter:
    def __init__(self):
        self.last_prompted: dict[str, datetime] = {}
        self.waiting: dict[str, datetime] = {}

    def _rank(self, module_id: str) -> datetime:
        return self.last_prompted.get(module_id, EPOCH)

    def mark_waiting(self, module_id: str, now: datetime) -> None:
        self.waiting.setdefault(module_id, now)

    def may_prompt(self, module_id: str, now: datetime) -> bool:
        mine = self._rank(module_id)
        return all(mine <= self._rank(other) for other in self.waiting if other != module_id)

    def record_prompt(self, module_id: str, now: datetime) -> None:
        self.waiting.pop(module_id, None)
        self.last_prompted[module_id] = now

    def forget(self, module_id: str) -> None:
        self.waiting.pop(module_id, None)


# Dùng chung cho mọi CoachModuleEngine trong tiến trình
SHARED_ARBITER = RoundRobinArbiter()
