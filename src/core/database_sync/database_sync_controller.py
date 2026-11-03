"""Chạy đồng bộ theo cấu hình: lúc mở app, ~10 giây sau mỗi thay đổi cục bộ, định kỳ N phút (kéo dữ liệu máy khác),
nút "Đồng bộ ngay" và lần đẩy cuối khi thoát.

sync_once chạy trên luồng nền (asyncio.to_thread) → pet không bao giờ bị treo vì mạng/VPS chậm.
Kéo về có dòng mới → phát data_changed để dashboard/Hub nạp lại.
"""

import asyncio
import logging
import threading
from datetime import datetime

from PySide6.QtCore import QObject, QTimer, Signal

from src.config import settings
from src.core.background_task_spawner import spawn_background_task
from src.core.i18n import tr

logger = logging.getLogger("ted")

CHANGE_CHECK_MS = 5_000    # chu kỳ xem sync_outbox có thay đổi mới không
PUSH_DEBOUNCE_MS = 10_000  # chờ thêm sau thay đổi cuối rồi mới đồng bộ


def _make_transport(config):
    if config.mode == "api_sync":
        from src.core.database_sync.api_sync_transport import ApiSyncTransport

        return ApiSyncTransport(config.api_url)
    from src.core.database_sync.postgres_connection_and_credentials import connect_postgres
    from src.core.database_sync.postgres_sync_transport import PostgresSyncTransport

    return PostgresSyncTransport(lambda: connect_postgres(config), config.schema_name,
                                 f"{config.host.strip()}|{config.port}|{config.database}")


def fill_user_name_from_server(name: str | None) -> None:
    """Chưa đặt tên trên máy này → lấy tên tài khoản phía server; đã có tên thì giữ nguyên."""
    if name and not settings.user_name:
        settings.set_user_name(name)
        settings.save()


class DatabaseSyncController(QObject):
    status_changed = Signal(str)
    data_changed = Signal()

    def __init__(self):
        super().__init__()
        self._engine = None
        self._service = None
        self._busy = False
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.sync_now)
        # App có thể chạy cả ngày không tắt → có thay đổi cục bộ là đẩy luôn (gom các thao tác liên tiếp)
        self._change_timer = QTimer(self)
        self._change_timer.setInterval(CHANGE_CHECK_MS)
        self._change_timer.timeout.connect(self._check_local_changes)
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(PUSH_DEBOUNCE_MS)
        self._debounce.timeout.connect(self.sync_now)
        self._last_seen_change = None
        self.status_text = tr("db_sync_status_off")

    def start(self, engine) -> None:
        self._engine = engine
        self.reconfigure()

    def reconfigure(self) -> None:
        """Gọi lại sau khi lưu cấu hình: tắt hẳn hoặc dựng service mới rồi đồng bộ ngay."""
        self._stop_timers()
        self._service = None
        config = settings.database_sync
        if self._engine is None or not config.enabled:
            self._set_status(tr("db_sync_status_off"))
            return
        from src.core.database_sync.sqlite_postgres_sync_service import DatabaseSyncService

        try:
            self._service = DatabaseSyncService(self._engine, _make_transport(config))
        except Exception as exc:  # vd DB đang bị khoá lúc cài trigger: app vẫn chạy, chỉ báo lỗi
            logger.exception("Không khởi tạo được đồng bộ dữ liệu")
            self._set_status(tr("db_sync_status_error", error=str(exc)))
            return
        self._timer.start(config.sync_interval_minutes * 60_000)
        self._change_timer.start()
        self.sync_now()

    def _check_local_changes(self) -> None:
        """Đọc mốc thay đổi mới nhất trong sync_outbox (SQLite cục bộ, vài ms); mốc mới → hẹn đồng bộ sau 10 giây."""
        try:
            with self._engine.connect() as conn:
                latest = conn.exec_driver_sql("SELECT MAX(changed_at) FROM sync_outbox").scalar()
        except Exception:  # DB bận / bị khoá → lần kiểm tra sau
            logger.debug("Không đọc được sync_outbox", exc_info=True)
            return
        if latest and latest != self._last_seen_change:
            self._last_seen_change = latest
            self._debounce.start()   # start lại = dời mốc, thao tác liên tiếp chỉ đồng bộ 1 lần

    def _stop_timers(self) -> None:
        self._timer.stop()
        self._change_timer.stop()
        self._debounce.stop()

    def sync_now(self) -> None:
        if self._service is None or self._busy:
            return
        self._busy = True
        self._set_status(tr("db_sync_status_running"))
        spawn_background_task(self._run(self._service), name="database_sync")

    async def _run(self, service) -> None:
        from src.core.database_sync.api_sync_transport import ApiKeyRejected

        try:
            result = await asyncio.to_thread(service.sync_once)
        except ApiKeyRejected:
            logger.warning("Đồng bộ dữ liệu thất bại: server từ chối khoá API")
            self._set_status(tr("db_sync_api_key_rejected"))
        except Exception as exc:
            logger.warning("Đồng bộ dữ liệu thất bại: %s", exc)
            self._set_status(tr("db_sync_status_error", error=str(exc)))
        else:
            self._set_status(tr("db_sync_status_ok", time=datetime.now().strftime("%H:%M"),
                                pushed=result.pushed, pulled=result.pulled))
            fill_user_name_from_server(result.server_user_name)
            if result.pulled:
                self.data_changed.emit()
        finally:
            self._busy = False

    def flush_on_exit(self, timeout: float = 10.0) -> None:
        """Lần đẩy cuối khi thoát; VPS không phản hồi thì chỉ chờ tối đa `timeout` giây."""
        service = self._service
        if service is None:
            return
        self._stop_timers()

        def run():
            try:
                service.sync_once()
            except Exception as exc:
                logger.warning("Đồng bộ lúc thoát thất bại: %s", exc)

        worker = threading.Thread(target=run, name="database_sync_exit", daemon=True)
        worker.start()
        worker.join(timeout)

    def _set_status(self, text: str) -> None:
        self.status_text = text
        self.status_changed.emit(text)


database_sync_controller = DatabaseSyncController()
