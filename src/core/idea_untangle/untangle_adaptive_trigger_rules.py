"""Luật thuần (không Qt/DB) quyết định khi nào Ted gợi ý Gỡ Rối: ngưỡng thích nghi theo lịch sử + cooldown cứng."""

import math
import statistics
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Sequence

MIN_SAMPLES = 5
MIN_ELAPSED_SECS = 10 * 60          # chỉ xét khi đã làm ≥ 10 phút
DEFAULT_OVERRUN = 1.5
OVERRUN_MIN, OVERRUN_MAX = 1.5, 4.0
DEFAULT_STREAK = 3
MAX_NUDGES_PER_DAY = 2
MAX_NUDGES_PER_TASK_PER_DAY = 1
BASE_GAP_MINS = 90
MAX_BACKOFF = 8

REASON_OVERRUN, REASON_STREAK, REASON_DISTRACTED, REASON_WRONG_STREAK = "overrun", "streak", "distracted", "wrong_streak"
REASONS = (REASON_WRONG_STREAK, REASON_OVERRUN, REASON_STREAK, REASON_DISTRACTED)  # thứ tự ưu tiên


@dataclass(frozen=True)
class Thresholds:
    overrun_ratio: float = DEFAULT_OVERRUN
    streak_sessions: int = DEFAULT_STREAK
    distraction_rate: float = 0.0       # xao nhãng / 25 phút của chính user (0 = chưa có dữ liệu → sàn 3)


@dataclass(frozen=True)
class Snapshot:
    """Ảnh chụp phiên đang chạy, do watcher dựng một lần mỗi tick kiểm tra."""
    running_deep_work: bool
    elapsed_secs: int
    planned_secs: int = 0
    task_focus_mins_before: float = 0.0     # phút đã focus cho task TRƯỚC phiên này
    estimated_mins: float = 0.0             # ước lượng task (pomodoro × phút pomodoro); 0 = không rõ
    consecutive_sessions: int = 0
    distraction_count: int = 0
    coach_wrong_streak: bool = False        # đã có ≥3 lần sai cùng câu/chủ đề (do truy vấn coach tính)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def compute_thresholds(overrun_ratios: Sequence[float], daily_counts: Sequence[int],
                       distraction_rates: Sequence[float]) -> Thresholds:
    """Ngưỡng theo lịch sử của chính user; < 5 mẫu → mặc định (tránh nhiễu ở user mới)."""
    overrun = (_clamp(1.25 * statistics.median(overrun_ratios), OVERRUN_MIN, OVERRUN_MAX)
               if len(overrun_ratios) >= MIN_SAMPLES else DEFAULT_OVERRUN)
    streak = (max(3, math.ceil(1.5 * statistics.median(daily_counts)))
              if len(daily_counts) >= MIN_SAMPLES else DEFAULT_STREAK)
    rate = statistics.median(distraction_rates) if len(distraction_rates) >= MIN_SAMPLES else 0.0
    return Thresholds(round(overrun, 3), streak, rate)


def distraction_limit(thresholds: Thresholds, elapsed_secs: int) -> int:
    """Số xao nhãng tối thiểu để kích hoạt: max(3, ceil(2 × tỉ lệ nền × phút / 25))."""
    return max(3, math.ceil(2 * thresholds.distraction_rate * (elapsed_secs / 60) / 25))


def evaluate_untangle_trigger(snap: Snapshot, th: Thresholds) -> Optional[str]:
    """Trả lý do bị kẹt (ưu tiên wrong_streak > overrun > streak > distracted) hoặc None."""
    if not snap.running_deep_work or snap.elapsed_secs < MIN_ELAPSED_SECS:
        return None
    if snap.coach_wrong_streak:
        return REASON_WRONG_STREAK
    if snap.estimated_mins > 0:
        spent = snap.task_focus_mins_before + snap.elapsed_secs / 60
        if spent >= th.overrun_ratio * snap.estimated_mins:
            return REASON_OVERRUN
    if snap.consecutive_sessions >= th.streak_sessions:
        return REASON_STREAK
    if snap.distraction_count >= distraction_limit(th, snap.elapsed_secs):
        return REASON_DISTRACTED
    return None


@dataclass
class NudgeState:
    """Trạng thái cooldown lưu KV `idea_untangle_nudge_v2` (JSON)."""
    day: str = ""
    count_today: int = 0
    tasks_today: list = field(default_factory=list)
    last_shown: str = ""                # ISO-8601 có múi giờ
    ignored: int = 0                    # số nudge liên tiếp chưa được nhận

    def to_json(self) -> dict:
        return asdict(self)

    @classmethod
    def from_json(cls, raw) -> "NudgeState":
        """Dữ liệu hỏng/thiếu → trạng thái rỗng (an toàn: chỉ làm nudge dễ hiện hơn 1 lần)."""
        if not isinstance(raw, dict):
            return cls()
        try:
            return cls(day=str(raw.get("day", "")), count_today=int(raw.get("count_today", 0)),
                       tasks_today=[str(t) for t in raw.get("tasks_today", [])],
                       last_shown=str(raw.get("last_shown", "")), ignored=max(0, int(raw.get("ignored", 0))))
        except (TypeError, ValueError):
            return cls()


def _today(now: datetime) -> str:
    return now.astimezone().date().isoformat()


def required_gap(ignored: int) -> timedelta:
    return timedelta(minutes=BASE_GAP_MINS * min(MAX_BACKOFF, 2 ** max(0, ignored)))


def cooldown_allows(state: NudgeState, task_key: str, now: datetime) -> bool:
    """Giới hạn cứng: ≤1/task/ngày, ≤2/ngày, giãn cách ≥ 90 phút × backoff."""
    if state.last_shown:
        try:
            if now - datetime.fromisoformat(state.last_shown) < required_gap(state.ignored):
                return False
        except (ValueError, TypeError):   # chuỗi hỏng / mốc naive (không múi giờ) → bỏ qua giãn cách
            pass
    if state.day == _today(now):
        if state.count_today >= MAX_NUDGES_PER_DAY or task_key in state.tasks_today:
            return False
    return True


def record_shown(state: NudgeState, task_key: str, now: datetime) -> NudgeState:
    """Ghi nhận đã hiện nudge; mặc định coi là bị bỏ qua cho tới khi user nhận (record_accepted)."""
    same_day = state.day == _today(now)
    return NudgeState(day=_today(now), count_today=(state.count_today if same_day else 0) + 1,
                      tasks_today=(state.tasks_today if same_day else []) + [task_key],
                      last_shown=now.isoformat(), ignored=state.ignored + 1)


def record_accepted(state: NudgeState) -> NudgeState:
    """User mở Gỡ Rối từ nudge → xoá backoff."""
    return NudgeState(state.day, state.count_today, list(state.tasks_today), state.last_shown, 0)
