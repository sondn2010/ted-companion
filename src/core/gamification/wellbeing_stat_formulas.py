"""6 chỉ số hiển thị trong Hub, tính thuần từ DaySignals (0..100, int). Hằng số chỉnh ở đầu file."""

from dataclasses import asdict, dataclass
from typing import Optional

from src.core.gamification.day_signals_collector import DaySignals

DATA_POINTS_FULL = 40
LEARNING_STUDY_DAYS_FULL = 5
SCREEN_ON_MINUTES_FULL = 600
SCREEN_CHAIN_MINUTES_FULL = 120
# Health: baseline 50; nghỉ ít hơn mục tiêu → rơi dưới 50, nhiều hơn → tăng
HEALTH_BASELINE = 50
REST_TARGET_SHARE = 0.15       # mục tiêu: nghỉ (vắng + giải lao) >= 15% tổng (nghỉ + Ted bật)
REST_SHARE_GAIN = 150          # điểm / 1.0 chênh lệch share
REST_TERM_LIMIT = 40           # kẹp ±40
BREAK_BONUS_EACH, BREAK_BONUS_MAX_COUNT = 4, 5
MICRO_BREAK_BONUS_EACH, MICRO_BREAK_BONUS_CAP = 3, 15   # hành động sức khỏe nhỏ sau Deep Work: +3/lần, tối đa +15/ngày
CHAIN_FREE_MINUTES, CHAIN_PENALTY_MAX = 90, 30
LATE_NIGHT_MINUTES_PER_POINT, LATE_NIGHT_PENALTY_MAX = 6, 20
ENGAGE_EVENT_MINUTES_FULL = 180
MEETING_ENGAGE_FULL_MINUTES = 45   # họp/học nhóm ≥ 45 phút → +MEETING_ENGAGE_POINTS điểm Gắn kết/Quan hệ trong ngày
MEETING_ENGAGE_POINTS = 80         # điểm ngày ≥ 80 → delta ≈ +12 (mạnh hơn mọi nguồn Gắn kết khác)


@dataclass(frozen=True)
class DayStats:
    data: int
    learning: Optional[int]   # None = không có coach → ẩn
    screen_load: int          # càng thấp càng tốt
    health: int
    engagement: int
    energy: int               # "Năng lượng lõi"

    def as_dict(self) -> dict:
        return asdict(self)


def _clamp(x: float) -> int:
    return int(round(max(0.0, min(100.0, x))))


def data_stat(s: DaySignals) -> int:
    pts = (2 * s.quiz_correct + s.quiz_wrong + 5 * s.agenda_done + 8 * s.writing_graded
           + 2 * s.tasks_done + s.focus_minutes / 10)
    return _clamp(pts * 100 / DATA_POINTS_FULL)


def learning_stat(s: DaySignals) -> Optional[int]:
    if not s.has_coach:
        return None
    return _clamp(60 * min(1, s.study_days_7d / LEARNING_STUDY_DAYS_FULL) + 40 * s.accuracy_7d)


def screen_load_stat(s: DaySignals) -> float:
    return (0.6 * min(100, s.app_on_minutes * 100 / SCREEN_ON_MINUTES_FULL)
            + 0.4 * min(100, s.focus_chain_max * 100 / SCREEN_CHAIN_MINUTES_FULL))


def health_stat(s: DaySignals) -> float:
    """Nghỉ đủ mục tiêu → >50; làm quá tay (ít nghỉ, chuỗi focus dài, thức khuya) → <50. Ngày không có dữ liệu = 50."""
    rest = s.away_minutes + s.break_minutes
    total = rest + s.app_on_minutes
    share = rest / total if total > 0 else REST_TARGET_SHARE  # không dữ liệu → trung tính
    rest_term = max(-REST_TERM_LIMIT, min(REST_TERM_LIMIT, REST_SHARE_GAIN * (share - REST_TARGET_SHARE)))
    break_bonus = BREAK_BONUS_EACH * min(s.breaks, BREAK_BONUS_MAX_COUNT)
    micro_bonus = min(MICRO_BREAK_BONUS_CAP, MICRO_BREAK_BONUS_EACH * s.micro_breaks)
    chain_penalty = min(CHAIN_PENALTY_MAX, max(0, s.focus_chain_max - CHAIN_FREE_MINUTES) / 2)
    late_penalty = min(LATE_NIGHT_PENALTY_MAX, s.late_night_minutes / LATE_NIGHT_MINUTES_PER_POINT)
    return HEALTH_BASELINE + rest_term + break_bonus + micro_bonus - chain_penalty - late_penalty


def engagement_stat(s: DaySignals) -> float:
    return (0.5 * min(100, s.personal_event_minutes * 100 / ENGAGE_EVENT_MINUTES_FULL)
            + 30 * min(s.outings, 2) + min(20, s.away_minutes / 12) + min(10, s.work_meeting_minutes / 12)
            + min(MEETING_ENGAGE_POINTS, s.meeting_session_minutes * MEETING_ENGAGE_POINTS / MEETING_ENGAGE_FULL_MINUTES))


def energy_stat(s: DaySignals, health: float, screen_load: float) -> float:
    momentum = min(100, (0.5 * s.xp_day + 0.5 * s.xp_7d_avg) * 100 / 150)
    return 0.5 * momentum + 0.3 * max(0, min(100, health)) + 0.2 * (100 - screen_load)


def compute_day_stats(s: DaySignals) -> DayStats:
    screen, health = screen_load_stat(s), health_stat(s)
    return DayStats(data=data_stat(s), learning=learning_stat(s), screen_load=_clamp(screen), health=_clamp(health),
                    engagement=_clamp(engagement_stat(s)), energy=_clamp(energy_stat(s, health, screen)))


def has_stat_activity(s: DaySignals) -> bool:
    """Ngày có dữ liệu thật (để lấy trung bình tuần, bỏ ngày trống)."""
    return bool(s.xp_day or s.app_on_minutes or s.away_minutes or s.outings or s.focus_minutes
                or s.meeting_session_minutes)
