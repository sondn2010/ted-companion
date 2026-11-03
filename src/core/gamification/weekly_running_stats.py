"""6 chỉ số tích lũy theo tuần (thuần): thứ Hai bắt đầu 50, mỗi ngày có hoạt động cộng thêm delta từ điểm ngày.

delta = (điểm ngày − 50) · STAT_DELTA_SCALE; giá trị chạy kẹp 0..100 và mang sang ngày sau trong cùng tuần.
Ngày không có dữ liệu thật → delta 0 (không bị trừ oan vì cuối tuần trống). Học tập None khi chưa từng có coach.
"""

from typing import Dict, List, Optional, Sequence

from src.core.gamification.wellbeing_stat_formulas import DayStats

STAT_START = 50.0
STAT_DELTA_SCALE = 0.4        # điểm ngày 100 → +20; điểm ngày 0 → −20
STAT_NAMES = ("data", "learning", "screen_load", "health", "engagement", "energy")


def stat_delta(day_score: Optional[int]) -> float:
    """Delta của 1 chỉ số từ điểm ngày (0..100); None (không có coach) → 0."""
    return 0.0 if day_score is None else (day_score - 50) * STAT_DELTA_SCALE


def _clamp(x: float) -> float:
    return max(0.0, min(100.0, x))


def _to_stats(values: Dict[str, Optional[float]]) -> DayStats:
    return DayStats(**{n: (None if v is None else int(round(_clamp(v)))) for n, v in values.items()})


def running_week_stats(day_stats: Sequence[DayStats], active: Sequence[bool]) -> List[DayStats]:
    """Giá trị chạy cuối mỗi ngày (Thứ Hai → hết danh sách). `active[i]` = ngày i có dữ liệu thật."""
    run: Dict[str, Optional[float]] = {n: STAT_START for n in STAT_NAMES}
    run["learning"] = None
    out: List[DayStats] = []
    for st, is_active in zip(day_stats, active):
        if run["learning"] is None and st.learning is not None:
            run["learning"] = STAT_START   # coach xuất hiện lần đầu trong tuần → bắt đầu từ 50
        for name in STAT_NAMES:
            score = getattr(st, name)
            if run[name] is not None and is_active:
                run[name] = _clamp(run[name] + stat_delta(score))
        out.append(_to_stats(run))
    return out


def stats_delta(prev: Optional[DayStats], cur: DayStats) -> Dict[str, Optional[int]]:
    """Chênh lệch ngày cuối so với ngày trước (prev None = từ mốc 50)."""
    out: Dict[str, Optional[int]] = {}
    for name in STAT_NAMES:
        now = getattr(cur, name)
        before = int(STAT_START) if prev is None else getattr(prev, name)
        out[name] = None if now is None else now - (int(STAT_START) if before is None else before)
    return out
