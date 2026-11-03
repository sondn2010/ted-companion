"""
Cấu hình phiên bản & địa chỉ kiểm tra cập nhật cho ứng dụng Ted Companion.
"""

import os
import re

# Phiên bản hiện tại của ứng dụng Ted
APP_VERSION = "1.5.1"

# URL mặc định kiểm tra bản cập nhật (nướng sẵn vào ứng dụng khi build)
DEFAULT_UPDATE_URL = "https://file5.bkglobal.vn/techbkglobal/release/version.json"


def get_default_update_url() -> str:
    """Trả về URL kiểm tra cập nhật mặc định (cho phép biến môi trường TED_UPDATE_URL ghi đè lúc dev)."""
    return os.getenv("TED_UPDATE_URL", DEFAULT_UPDATE_URL).strip()


def parse_version(v_str: str) -> tuple[int, ...]:
    """
    Phân tích chuỗi phiên bản dạng 'v1.2.3' hoặc '1.2.3-beta' thành tuple các số nguyên.
    Nếu chuỗi không hợp lệ, trả về (0, 0, 0).
    """
    if not v_str:
        return (0, 0, 0)
    # Loại bỏ tiền tố v/V
    clean = re.sub(r"^[vV]", "", v_str.strip())
    # Lấy phần số phiên bản chính (trước dấu gạch ngang hoặc chữ)
    match = re.match(r"^(\d+(?:\.\d+)*)", clean)
    if not match:
        return (0, 0, 0)
    parts = [int(p) for p in match.group(1).split(".")]
    # Chuẩn hoá tối thiểu 3 phần tử (Major, Minor, Patch)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def is_newer_version(remote_version: str, local_version: str = APP_VERSION) -> bool:
    """So sánh xem remote_version có lớn hơn local_version hay không."""
    return parse_version(remote_version) > parse_version(local_version)
