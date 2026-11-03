"""Chặn chạy 2 bản Ted cùng lúc (2 bản = app_on_minutes nhân đôi, heartbeat đan xen, IntegrityError wellbeing).

Cơ chế: QLocalServer đặt tên theo thư mục dữ liệu (TED_HOME khác nhau thì chạy song song được).
Bản chạy sau nối thử vào server của bản đầu: nối được -> gửi "show" (bản đầu hiện lại nhân vật) rồi thoát im lặng.
Fail-open: không listen được (quyền, tên bị chiếm bất thường) -> vẫn cho chạy, chỉ ghi log.
Biến môi trường TED_ALLOW_MULTIPLE_INSTANCES=1 tắt guard (dev / test).
"""

import hashlib
import logging
import os
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import QObject
from PySide6.QtNetwork import QLocalServer, QLocalSocket

logger = logging.getLogger("ted")

ALLOW_MULTIPLE_ENV = "TED_ALLOW_MULTIPLE_INSTANCES"
CONNECT_TIMEOUT_MS = 500
SHOW_MESSAGE = b"show"


def instance_name_for(data_dir: Path) -> str:
    """Tên server ổn định theo thư mục dữ liệu (băm để không dính ký tự đường dẫn)."""
    digest = hashlib.sha1(str(Path(data_dir).resolve()).lower().encode("utf-8")).hexdigest()[:12]
    return f"TedCompanion-{digest}"


class SingleInstanceGuard(QObject):
    """Giữ QLocalServer của bản đang chạy; `on_activate` được gọi khi bản khác cố mở (để hiện lại nhân vật)."""

    def __init__(self, server: Optional[QLocalServer] = None):
        super().__init__()
        self._server = server
        self.on_activate: Optional[Callable[[], None]] = None
        if server is not None:
            server.newConnection.connect(self._on_connection)

    def _on_connection(self) -> None:
        while self._server is not None and self._server.hasPendingConnections():
            sock = self._server.nextPendingConnection()
            sock.waitForReadyRead(100)
            sock.readAll()
            sock.disconnectFromServer()
            if self.on_activate is not None:
                try:
                    self.on_activate()
                except Exception:  # noqa: BLE001 - hiện lại nhân vật lỗi không được làm sập app
                    logger.exception("Không hiện lại được nhân vật khi mở bản thứ hai")

    def release(self) -> None:
        """Nhả khóa (khi thoát / trước khi relaunch sau cập nhật để bản mới không tưởng bản cũ còn sống)."""
        if self._server is not None:
            self._server.close()
            self._server = None


def acquire_single_instance(data_dir: Path) -> Optional[SingleInstanceGuard]:
    """Trả guard nếu đây là bản đầu tiên; None nếu đã có bản khác chạy (đã báo bản đó hiện lại)."""
    if os.environ.get(ALLOW_MULTIPLE_ENV) == "1":
        return SingleInstanceGuard()
    name = instance_name_for(data_dir)
    probe = QLocalSocket()
    probe.connectToServer(name)
    if probe.waitForConnected(CONNECT_TIMEOUT_MS):
        probe.write(SHOW_MESSAGE)
        probe.flush()
        probe.waitForBytesWritten(CONNECT_TIMEOUT_MS)
        probe.disconnectFromServer()
        return None
    QLocalServer.removeServer(name)   # dọn socket mồ côi của bản đã chết (Unix); Windows là no-op
    server = QLocalServer()
    if not server.listen(name):
        logger.warning("Không tạo được khóa single-instance (%s), vẫn chạy", server.errorString())
        return SingleInstanceGuard()
    return SingleInstanceGuard(server)
