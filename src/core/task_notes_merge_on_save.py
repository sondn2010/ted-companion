"""Gộp ghi chú khi lưu từ form Chi tiết công việc, tránh mất mục Gỡ Rối Ý Tưởng nối thêm lúc form đang mở."""

from typing import Optional


def notes_to_save(loaded_raw: str, loaded_shown: str, edited: str, current_raw: str) -> Optional[str]:
    """Trả giá trị `notes` truyền cho update_task (None = giữ nguyên ghi chú trong DB).

    loaded_raw: notes đọc từ DB lúc mở form; loaded_shown: text ô soạn thảo ngay sau khi nạp (đã chuẩn hoá xuống dòng);
    edited: text hiện tại trong ô; current_raw: notes trong DB ngay lúc lưu.
    - Người dùng không sửa ô ghi chú → None (không đè phần ai đó đã nối thêm).
    - Có sửa, DB đã được nối thêm phía sau bản đã nạp → giữ bản sửa + phần nối thêm.
    - Còn lại → bản sửa của người dùng.
    """
    if edited == loaded_shown:
        return None
    if current_raw != loaded_raw and current_raw.startswith(loaded_raw):
        return edited + current_raw[len(loaded_raw):]
    return edited
