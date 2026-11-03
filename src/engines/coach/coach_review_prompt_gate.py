"""Cổng quyết định có được hiện bong bóng nhắc coach hay không (thuần hàm, không phụ thuộc Qt/DB)."""

from datetime import date, datetime
from typing import Optional

from src.core.focus_engine import FocusState
from src.engines.coach.coach_policy_clamp import in_any_window
from src.engines.coach.coach_sync_plan_schemas import Policy

# Đang giữa phiên tập trung → tuyệt đối không làm phiền (PAUSED cũng vậy: người dùng sắp quay lại làm tiếp)
SUPPRESSED_STATES = (FocusState.DEEP_WORK_RUNNING, FocusState.PAUSED, FocusState.MEETING_RUNNING)


def should_prompt(
    now: datetime, state: str, policy: Policy, *,
    attempts_today: int, due_count: int, new_available: int,
    snooze_until: Optional[datetime] = None, skip_date: Optional[date] = None, in_meeting: bool = False,
) -> tuple[bool, str]:
    """`now` là giờ địa phương (aware). Trả (được_nhắc, lý_do). Lý do dùng cho log/test."""
    if state in SUPPRESSED_STATES:
        return False, "focus_session"
    local_time = now.timetz().replace(tzinfo=None)
    if in_any_window(policy.quiet_hours, local_time):
        return False, "quiet_hours"
    if attempts_today >= policy.daily_cap:
        return False, "daily_cap"
    if snooze_until is not None and now < snooze_until:
        return False, "snoozed"
    if skip_date == now.date():
        return False, "skipped_today"
    if in_meeting:
        return False, "in_meeting"
    if due_count <= 0 and new_available <= 0:
        return False, "nothing_to_review"
    # study_windows là ưu tiên chứ không phải rào cứng: nghỉ giải lao → kiểm tra ngay;
    # IDLE ngoài khung → chỉ nhắc khi có câu đến hạn (không đẩy câu mới)
    if state == FocusState.IDLE and policy.study_windows and due_count <= 0 \
            and not in_any_window(policy.study_windows, local_time):
        return False, "outside_study_window"
    return True, "ok"
