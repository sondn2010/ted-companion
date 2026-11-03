"""Hàm nhỏ cho các điểm vào UI (menu pet, tray, tab Công việc, hotkey) của chế độ Họp.

Truy cập theo getattr để điểm vào vẫn dựng được khi focus engine là bản giả/rút gọn (test, host nhúng);
FocusEngine thật luôn có `in_meeting` và `request_meeting_toggle`.
"""


def meeting_active(focus) -> bool:
    return bool(getattr(focus, "in_meeting", False))


def request_meeting_toggle(focus) -> None:
    """Bật (hỏi chủ đề) / tắt chế độ Họp qua coordinator nghe `meeting_toggle_requested`."""
    request = getattr(focus, "request_meeting_toggle", None)
    if request is not None:
        request()
