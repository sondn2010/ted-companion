import asyncio
from typing import Callable, Optional

from src.bridge.openai_client import OpenAIBrainClient
from src.config import AppConfig, settings
from src.core.background_task_spawner import spawn_background_task

# Trả về connection id mặc định khai báo trong manifest của module
ManifestConnectionResolver = Callable[[str], Optional[str]]


def _close_client_later(client: OpenAIBrainClient) -> None:
    """Đóng AsyncOpenAI của client bị thay/bỏ (giải phóng httpx pool). Không có event loop đang chạy → bỏ qua."""
    inner = getattr(client, "_client", None)  # chỉ có khi client đã từng gọi mạng
    if inner is None:
        return
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return
    spawn_background_task(inner.close(), "openai-client-close")


class OpenAIClientPool:
    """Một OpenAIBrainClient cho mỗi kết nối; tự tạo lại khi URL/API key/model thay đổi."""

    def __init__(self, config: AppConfig):
        self._config = config
        self._clients: dict[str, tuple[tuple, OpenAIBrainClient]] = {}
        self.manifest_connection_resolver: Optional[ManifestConnectionResolver] = None
        # module_id -> True nếu module không được phép rơi về kết nối mặc định (gắn ở main.py)
        self.strict_module_predicate: Optional[Callable[[str], bool]] = None

    def get(self, conn_id: str) -> Optional[OpenAIBrainClient]:
        conn = self._config.get_connection(conn_id)
        if conn is None:
            return None
        cached = self._clients.get(conn_id)
        if cached and cached[0] == conn.identity_key():
            return cached[1]
        if cached:  # cấu hình đổi → client cũ bị thay, đóng kết nối HTTP của nó
            _close_client_later(cached[1])
        client = OpenAIBrainClient(conn)
        self._clients[conn_id] = (conn.identity_key(), client)
        return client

    def connection_id_for_module(self, module_id: str) -> Optional[str]:
        """Thứ tự ưu tiên: override trong Settings → manifest → kết nối đầu tiên.
        Module "nghiêm ngặt" (coach: dữ liệu trẻ em) KHÔNG có bước cuối — thiếu kết nối thì trả None để không
        bao giờ gửi nhầm sang kết nối khác (vd. profile công việc)."""
        candidates = [self._config.module_override(module_id).connection]
        if self.manifest_connection_resolver:
            candidates.append(self.manifest_connection_resolver(module_id))
        for conn_id in candidates:
            if conn_id and self._config.get_connection(conn_id):
                return conn_id
        if self.strict_module_predicate and self.strict_module_predicate(module_id):
            return None
        return self._config.connections[0].id if self._config.connections else None

    def for_module(self, module_id: str) -> Optional[OpenAIBrainClient]:
        """None = module chưa có kết nối hợp lệ (bên gọi coi như offline/chưa cấu hình)."""
        conn_id = self.connection_id_for_module(module_id)
        if not conn_id:
            return None
        client = self.get(conn_id)
        if client and not getattr(client, f"_restored_for_{module_id}", False):
            try:
                from src.core.chat_session_manager import chat_session_manager
                chat_session_manager.restore_client_history(module_id, client)
                setattr(client, f"_restored_for_{module_id}", True)
            except Exception:
                pass
        return client

    def drop(self, conn_id: str) -> None:
        """Bỏ client của 1 kết nối đã bị xoá (các kết nối khác giữ nguyên lịch sử chat)."""
        cached = self._clients.pop(conn_id, None)
        if cached:
            _close_client_later(cached[1])

    def invalidate(self):
        """Bỏ toàn bộ client (kèm lịch sử chat) để tạo lại."""
        for conn_id in list(self._clients):
            self.drop(conn_id)


openai_client_pool = OpenAIClientPool(settings)

# Backward compatibility aliases
HermesClientPool = OpenAIClientPool
hermes_client_pool = openai_client_pool
AIClientPool = OpenAIClientPool
AI_client_pool = openai_client_pool
