"""Tên múi giờ IANA của máy (prompt lịch cần IANA, vd Asia/Ho_Chi_Minh). Windows chỉ cho tên Windows → map + fallback Etc/GMT±N."""

import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_WINDOWS_TO_IANA = {
    "SE Asia Standard Time": "Asia/Ho_Chi_Minh",
    "China Standard Time": "Asia/Shanghai",
    "Singapore Standard Time": "Asia/Singapore",
    "Tokyo Standard Time": "Asia/Tokyo",
    "India Standard Time": "Asia/Kolkata",
    "GMT Standard Time": "Europe/London",
    "W. Europe Standard Time": "Europe/Berlin",
    "Eastern Standard Time": "America/New_York",
    "Pacific Standard Time": "America/Los_Angeles",
    "UTC": "UTC",
}


def _valid(name: str | None) -> str | None:
    if not name:
        return None
    try:
        ZoneInfo(name)  # cần gói tzdata trên Windows
    except (ZoneInfoNotFoundError, ValueError, OSError):
        return None
    return name


def _etc_gmt(offset_secs: int) -> str:
    hours, rest = divmod(abs(offset_secs), 3600)
    if rest or hours > 14:
        return "UTC"  # offset lẻ giờ không có Etc/GMT tương ứng
    # Dấu của Etc/GMT ngược với UTC offset (Etc/GMT-7 = UTC+7)
    return "UTC" if hours == 0 else f"Etc/GMT{'-' if offset_secs > 0 else '+'}{hours}"


def local_timezone_name(override: str | None = None) -> str:
    """Thứ tự: override (settings) → biến TZ → tên Windows đã map → Etc/GMT±N theo offset hiện tại."""
    for candidate in (override, os.environ.get("TZ"), _WINDOWS_TO_IANA.get(time.tzname[0]), time.tzname[0]):
        if (name := _valid(candidate)):
            return name
    return _etc_gmt(int(datetime.now().astimezone().utcoffset().total_seconds()))
