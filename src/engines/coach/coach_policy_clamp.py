"""Policy do Hermes đề xuất chỉ mang tính tư vấn: Ted kẹp số vào khoảng an toàn; sai cấu trúc → giữ policy cũ."""

import logging
from datetime import time
from typing import Optional, Union

from pydantic import ValidationError

from src.engines.coach.coach_sync_plan_schemas import CLOCK_RE, WINDOW_RE, Policy

logger = logging.getLogger("ted")

DEFAULT_POLICY = Policy(
    review_interval_mins=15, daily_cap=20, new_per_day=10,
    quiet_hours=[], study_windows=[], leitner_days=[0.007, 1, 3, 7, 14, 30],
)


def _clamp(value: float, low: float, high: float):
    return max(low, min(high, value))


def _valid_windows(windows: list[str]) -> list[str]:
    kept = []
    for entry in windows:
        start, _, end = entry.partition("-")
        if WINDOW_RE.match(entry) and CLOCK_RE.match(start) and CLOCK_RE.match(end):
            kept.append(entry)
    return kept


def clamp_policy(policy: Policy) -> Policy:
    return policy.model_copy(update={
        "review_interval_mins": int(_clamp(policy.review_interval_mins, 10, 120)),
        "daily_cap": int(_clamp(policy.daily_cap, 5, 40)),
        "new_per_day": int(_clamp(policy.new_per_day, 0, 20)),
        "leitner_days": [_clamp(d, 0.003, 365) for d in policy.leitner_days],
        "quiet_hours": _valid_windows(policy.quiet_hours),
        "study_windows": _valid_windows(policy.study_windows),
    })


def apply_policy(old: Policy, new_raw: Union[Policy, dict, None]) -> Policy:
    """Policy mới hợp lệ → đã kẹp; None / sai cấu trúc → trả policy cũ nguyên vẹn."""
    if new_raw is None:
        return old
    try:
        candidate = new_raw if isinstance(new_raw, Policy) else Policy.model_validate(new_raw)
        candidate = Policy.model_validate(candidate.model_dump())   # đảm bảo luôn qua validator leitner_days
    except ValidationError as exc:
        logger.warning("Policy không hợp lệ, giữ policy cũ: %s", str(exc)[:200])
        return old
    try:
        # Kẹp biên có thể làm 2 giá trị liền kề bằng nhau → validate lại sau khi kẹp
        return Policy.model_validate(clamp_policy(candidate).model_dump())
    except ValidationError:
        logger.warning("Policy sau khi kẹp mất tính tăng dần, giữ policy cũ")
        return old


def _parse_clock(text: str) -> time:
    hour, _, minute = text.partition(":")
    return time(int(hour), int(minute))


def in_any_window(windows: list[str], moment: time) -> bool:
    """moment (giờ địa phương) nằm trong 1 khung 'HH:MM-HH:MM'; hỗ trợ khung qua nửa đêm (21:45-06:30)."""
    for entry in _valid_windows(windows):
        start_text, _, end_text = entry.partition("-")
        start, end = _parse_clock(start_text), _parse_clock(end_text)
        if start <= end:
            if start <= moment < end:
                return True
        elif moment >= start or moment < end:
            return True
    return False


def effective_policy(stored: Optional[Policy]) -> Policy:
    return stored if stored is not None else DEFAULT_POLICY
