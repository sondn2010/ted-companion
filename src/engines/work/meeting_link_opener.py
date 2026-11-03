"""Mở link họp an toàn: chỉ http/https; domain lạ phải được người dùng xác nhận (link lấy từ lời mời của người khác)."""

import logging
from urllib.parse import urlparse

logger = logging.getLogger("ted")

TRUSTED_DOMAINS = ("meet.google.com", "zoom.us", "teams.microsoft.com", "teams.live.com", "webex.com")


def classify_meeting_url(url: str) -> str:
    """'blocked' (sai scheme/không có host) | 'trusted' (whitelist, kể cả subdomain) | 'confirm' (hỏi người dùng)."""
    try:
        parsed = urlparse(url.strip())
        host = (parsed.hostname or "").lower()
    except ValueError:
        return "blocked"
    if parsed.scheme not in ("http", "https") or not host:
        return "blocked"
    if any(host == d or host.endswith("." + d) for d in TRUSTED_DOMAINS):
        return "trusted"
    return "confirm"


def open_meeting_link(url: str, parent=None) -> bool:
    """True nếu đã mở trình duyệt. Chạy trên UI thread (có hộp thoại xác nhận cho domain lạ)."""
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices
    from PySide6.QtWidgets import QMessageBox

    verdict = classify_meeting_url(url)
    if verdict == "blocked":
        logger.warning("Từ chối mở link họp không hợp lệ")
        return False
    if verdict == "confirm":
        host = urlparse(url.strip()).hostname
        answer = QMessageBox.question(
            parent, "Mở link họp?", f"Link này trỏ tới \"{host}\" (không nằm trong danh sách quen thuộc).\nMở thật không?")
        if answer != QMessageBox.StandardButton.Yes:
            return False
    return QDesktopServices.openUrl(QUrl(url.strip()))
