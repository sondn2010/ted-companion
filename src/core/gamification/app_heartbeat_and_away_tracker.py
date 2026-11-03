"""Heartbeat Ted đang chạy + suy ra "vắng mặt" từ khoảng trống giữa 2 lần chạy (app đóng / máy tắt).

Không theo dõi bàn phím/chuột/màn hình. Hub service gọi: on_app_start(now) 1 lần, tick(now) mỗi 60s,
record_break(now) khi focus_engine chuyển sang BREAK_RUNNING.
"""

import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Dict, Optional

from src.core.app_state_key_value_store import KeyValueStore
from src.core.gamification.wellbeing_daily_repository import WellbeingDailyRepository
from src.core.gamification.xp_ledger_repository import XpLedgerRepository

logger = logging.getLogger("ted")

KV_LAST_HEARTBEAT = "gamify.last_heartbeat"
WAKING_START_HOUR = 7
WAKING_END_HOUR = 22
LATE_NIGHT_FROM_HOUR = 22  # Ted vẫn chạy từ 22:00 đến trước 05:00 = thức khuya
LATE_NIGHT_UNTIL_HOUR = 5
MIN_GAP_MINUTES = 10   # ngắn hơn = restart bình thường, không tính vắng mặt
MAX_GAP_DAYS = 30      # dài hơn / âm (đổi đồng hồ) → bỏ qua


def _to_local_naive(dt: datetime) -> datetime:
    """aware → giờ máy (bỏ tzinfo); naive được hiểu là giờ máy sẵn."""
    return dt.astimezone().replace(tzinfo=None) if dt.tzinfo else dt


def split_gap_waking_minutes(start: datetime, end: datetime) -> Dict[date, int]:
    """Chia khoảng [start, end] theo ngày local, chỉ đếm phần giao với 07:00–22:00. Hàm thuần."""
    start, end = _to_local_naive(start), _to_local_naive(end)
    out: Dict[date, int] = {}
    if end <= start:
        return out
    day = start.date()
    while day <= end.date():
        lo = max(start, datetime.combine(day, time(WAKING_START_HOUR)))
        hi = min(end, datetime.combine(day, time(WAKING_END_HOUR)))
        minutes = int((hi - lo).total_seconds() // 60)
        if minutes > 0:
            out[day] = minutes
        day += timedelta(days=1)
    return out


class AppHeartbeatTracker:
    def __init__(self, kv: KeyValueStore, wellbeing: WellbeingDailyRepository, ledger: XpLedgerRepository):
        self._kv, self._wellbeing, self._ledger = kv, wellbeing, ledger

    def _last_heartbeat(self) -> Optional[datetime]:
        raw = self._kv.get(KV_LAST_HEARTBEAT)
        try:
            return datetime.fromisoformat(raw) if raw else None
        except ValueError:
            logger.warning("gamify.last_heartbeat hỏng, bỏ qua: %r", raw)
            return None

    def on_app_start(self, now: datetime) -> Dict[date, int]:
        """Cộng away_minutes cho khoảng trống từ heartbeat cuối đến `now`; trả phần đã cộng (rỗng nếu lần đầu)."""
        added = self._credit_gap(now) or {}
        self._write_heartbeat(now)
        return added

    def _credit_gap(self, now: datetime) -> Optional[Dict[date, int]]:
        """Cộng away_minutes cho khoảng trống [heartbeat cuối, now] nếu đủ dài (>= 10 phút, <= 30 ngày).
        None = không có khoảng trống đáng kể; dict (có thể rỗng nếu gap nằm ngoài 07:00–22:00) = đã xử lý."""
        last = self._last_heartbeat()
        if last is None:
            return None
        gap = _to_local_naive(now) - _to_local_naive(last)
        if not timedelta(minutes=MIN_GAP_MINUTES) <= gap <= timedelta(days=MAX_GAP_DAYS):
            return None
        added = split_gap_waking_minutes(last, now)
        for day, minutes in added.items():
            self._wellbeing.add_away(day, minutes)
        return added

    def tick(self, now: datetime) -> bool:
        """Mỗi 60s: +1 phút app_on (và late_night nếu khuya), ghi heartbeat. Trả True nếu phút này được tính.

        Máy ngủ/ngủ đông khi Ted còn mở = nghỉ ngơi: tick đầu tiên sau khi thức dậy thấy heartbeat cũ >= 10 phút
        → cộng khoảng trống vào away (cùng luật 07:00–22:00 như lúc khởi động) và KHÔNG tính phút đó là Ted bật."""
        if self._credit_gap(now) is not None:
            self._write_heartbeat(now)
            return False
        local = _to_local_naive(now)
        self._wellbeing.add_minutes(local.date(), 1)
        if local.hour >= LATE_NIGHT_FROM_HOUR or local.hour < LATE_NIGHT_UNTIL_HOUR:
            self._wellbeing.add_late_night(local.date(), 1)
        self._write_heartbeat(now)
        return True

    def record_break(self, now: datetime) -> bool:
        """Ghi 1 lần nghỉ (ledger core/break_taken, key theo phút) + breaks_taken. False nếu đã ghi trong phút này."""
        local = _to_local_naive(now)
        ts = now if now.tzinfo else now.astimezone()
        event = self._ledger.add(f"break:{local:%Y%m%d%H%M}", ts.astimezone(timezone.utc), "core", "core", "break_taken")
        if event is None:
            return False
        self._wellbeing.increment_break(local.date())
        return True

    def _write_heartbeat(self, now: datetime) -> None:
        aware = now if now.tzinfo else now.astimezone()
        self._kv.set(KV_LAST_HEARTBEAT, aware.isoformat())
