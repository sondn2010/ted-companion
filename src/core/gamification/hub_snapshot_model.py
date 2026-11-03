"""Ảnh chụp trạng thái Hub (dữ liệu thuần, bất biến) — UI phase 06/07 chỉ đọc, không tự truy vấn DB."""

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, FrozenSet, List, Optional


@dataclass(frozen=True)
class WeeklyLogRow:
    week_start: str
    final_level: int
    peak_level: int
    final_pct: float
    xp_earned: int
    active_days: int
    decay_days: int
    stats: Dict[str, Optional[int]]
    badge_ids: List[str]


@dataclass(frozen=True)
class HubSnapshot:
    today: date
    week_start: date
    level: int
    peak_level: int
    pct: float                           # tiến độ tuần 0–100 (thứ Hai = 50)
    pct_today_delta: float               # % thay đổi trong hôm nay
    xp_today: int
    week_xp: int                         # XP dương trong tuần hiện tại (live)
    active_days: int
    decay_days: int
    stats: Dict[str, Optional[int]]         # 6 chỉ số tích lũy trong tuần (learning None = không có coach)
    stats_delta_today: Dict[str, Optional[int]]   # thay đổi của từng chỉ số trong hôm nay
    badges_unlocked: FrozenSet[str] = field(default_factory=frozenset)   # mọi badge id từng mở
    badges_this_week: FrozenSet[str] = field(default_factory=frozenset)
    distinct_badge_count: int = 0
    weekly_log: List[WeeklyLogRow] = field(default_factory=list)         # mới nhất trước
