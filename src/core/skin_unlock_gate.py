"""Cổng mở khoá nhân vật: trạng thái dùng chung giữa Hub service (ghi) và FocusEngine/UI (đọc), không phụ thuộc Qt/config.

- Nhân vật gốc (6 con vật / pack `--pack`) không có '/' trong key → luôn mở.
- Nhân vật bundle (`pack/character`) chỉ dùng được khi nằm trong tập đã mở khoá (lưu vĩnh viễn ở bảng SkinUnlock).
- Chưa có Hub service (tập = None) → cho phép tất cả (hành vi cũ, test, chế độ không gamification).
"""

from typing import Iterable, Optional

_unlocked_keys: Optional[frozenset] = None


def is_bundled_skin_key(key: str) -> bool:
    return "/" in key


def set_unlocked_skin_keys(keys: Optional[Iterable[str]]) -> None:
    """Hub service gọi mỗi lần đánh giá lại; None = tắt cổng (cho phép tất cả)."""
    global _unlocked_keys
    _unlocked_keys = None if keys is None else frozenset(keys)


def is_skin_unlocked(key: str) -> bool:
    if _unlocked_keys is None or not is_bundled_skin_key(key):
        return True
    return key in _unlocked_keys
