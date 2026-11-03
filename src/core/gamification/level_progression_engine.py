"""Engine tiến độ tuần thuần (không Qt, không DB): phát lại XP từng ngày thành thanh % 0–100.

Mỗi thứ Hai thanh bắt đầu ở START_PCT (50%). Điểm XP trong sổ cái giữ nguyên; việc đổi điểm → % chỉ xảy ra ở đây:
  - ngày có XP ròng > 0: +min(xp·PCT_PER_XP, DAY_GAIN_CAP)  (trần để tuần không đầy ngay ngày đầu)
  - ngày thu hồi (XP ròng < 0): trừ đối xứng xp·PCT_PER_XP, không có trần
  - ngày đã kết thúc mà XP < MIN_DAILY_XP: −DECAY_PCT (kể cả cuối tuần)
Level suy ra từ %: ceil(% / 10) kẹp 1..10. Decay không lưu mà tính lại mỗi lần.
"""

import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List

MAX_LEVEL = 10
START_PCT = 50.0          # thanh tuần mới bắt đầu ở 50% (= Lv5)
PCT_PER_XP = 0.1          # 1 XP = 0.1% → ngày làm việc tốt (~80–100 XP) ≈ +8–10%
DAY_GAIN_CAP = 15.0       # tối đa +15%/ngày
DECAY_PCT = 5.0           # ngày kết thúc thiếu XP tối thiểu → −5%
MIN_DAILY_XP = 20         # điểm XP tối thiểu mỗi ngày để không bị trừ


def clamp_pct(pct: float) -> float:
    """Kẹp 0..100, làm tròn 2 chữ số để tránh sai số float làm lệch level ở mốc chia hết 10."""
    return round(max(0.0, min(100.0, pct)), 2)


def level_for_pct(pct: float) -> int:
    """Lv = ceil(% / 10) kẹp 1..MAX_LEVEL (0–10% → Lv1, 50% → Lv5, 100% → Lv10)."""
    return max(1, min(MAX_LEVEL, math.ceil(clamp_pct(pct) / 10)))


def week_start_of(d: date) -> date:
    """Thứ Hai của tuần chứa d."""
    return d - timedelta(days=d.weekday())


def day_pct_gain(xp: int) -> float:
    """% thay đổi do XP ròng của 1 ngày: dương bị trần, âm (thu hồi) đối xứng."""
    gain = xp * PCT_PER_XP
    return min(gain, DAY_GAIN_CAP) if gain > 0 else gain


@dataclass
class WeekProgress:
    pct: float = START_PCT
    level: int = level_for_pct(START_PCT)
    peak_level: int = level_for_pct(START_PCT)
    pct_today_delta: float = 0.0          # thay đổi % của ngày xử lý cuối cùng (hôm nay)
    decay_days: int = 0
    active_days: int = 0
    demoted_then_recovered: bool = False
    day_end_levels: List[int] = field(default_factory=list)


def replay_week(daily_xp: Dict[date, int], week_start: date, today: date) -> WeekProgress:
    """Phát lại Thứ Hai → min(today, Chủ nhật). Hôm nay chưa bị decay; ngày trước đó thiếu XP bị decay."""
    p = WeekProgress()
    pct, pending_drop = START_PCT, 0
    last_day = min(today, week_start + timedelta(days=6))
    d = week_start
    while d <= last_day:
        xp = daily_xp.get(d, 0)
        before = pct
        pct = clamp_pct(pct + day_pct_gain(xp))
        level = level_for_pct(pct)
        p.peak_level = max(p.peak_level, level)
        if xp >= MIN_DAILY_XP:
            p.active_days += 1
        if pending_drop and level >= pending_drop:  # quay lại đúng mức đã rớt
            p.demoted_then_recovered = True
        p.pct_today_delta = round(pct - before, 2)
        if d < today and xp < MIN_DAILY_XP:  # ngày đã kết thúc, thiếu hoạt động → decay
            pct = clamp_pct(pct - DECAY_PCT)
            p.decay_days += 1
            p.pct_today_delta = round(pct - before, 2)
            if level_for_pct(pct) < level:
                pending_drop = max(pending_drop, level)  # ghi nhớ level trước khi rớt để nhận "comeback"
        p.day_end_levels.append(level_for_pct(pct))
        d += timedelta(days=1)
    p.pct, p.level = pct, level_for_pct(pct)
    return p
