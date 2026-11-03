"""
Quản lý phiên hội thoại (Chat Session) bền vững theo Module:
- Lưu lịch sử tin nhắn xuống SQLite (KeyValueStore) để khi tắt đi bật lại app/popup không bị mất luồng trò chuyện.
- Cung cấp tính năng Reset Session (Tạo mới phiên) khi người dùng muốn bắt đầu ngữ cảnh mới.
- Đồng bộ lịch sử LLM của HermesBrainClient tương ứng để ngữ cảnh được theo sát liền mạch.
"""

from datetime import datetime, timezone
import logging
from typing import Any, Callable, Optional
from uuid import uuid4

from PySide6.QtCore import QObject, Signal

from src.core.app_state_key_value_store import KeyValueStore
from src.core.models import db

logger = logging.getLogger("ted")


class ChatSessionManager(QObject):
    session_reset = Signal(str)  # module_id
    message_appended = Signal(str, dict)  # module_id, message_dict

    def __init__(self, kv: Optional[KeyValueStore] = None, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._kv = kv or KeyValueStore(db.engine)
        self._client_pool = None

    def set_client_pool(self, pool) -> None:
        self._client_pool = pool

    def _storage_key(self, module_id: str) -> str:
        return f"chat_session_v1:{module_id}"

    def get_session(self, module_id: str) -> dict[str, Any]:
        """Tải phiên hiện tại của module; nếu chưa có thì khởi tạo phiên mới."""
        key = self._storage_key(module_id)
        data = self._kv.get_json(key)
        if not data or not isinstance(data, dict) or "session_id" not in data:
            return self._create_new_session(module_id)
        return data

    def _create_new_session(self, module_id: str) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        session = {
            "session_id": str(uuid4()),
            "module_id": module_id,
            "created_at": now,
            "updated_at": now,
            "history": [],  # Danh sách [{"role": "user"|"assistant", "content": "..."}]
            "messages": [],  # Danh sách tin nhắn hiển thị UI [{"role": "...", "text": "...", "timestamp": "..."}]
        }
        self._kv.set_json(self._storage_key(module_id), session)
        return session

    def reset_session(self, module_id: str) -> dict[str, Any]:
        """Xoá ngữ cảnh cũ, tạo phiên mới cho module, đồng thời dọn dẹp history của HermesBrainClient."""
        new_session = self._create_new_session(module_id)

        # Xoá lịch sử hội thoại trên client LLM tương ứng nếu có client pool
        if self._client_pool:
            client = self._client_pool.for_module(module_id)
            if client and hasattr(client, "history"):
                # Giữ lại system prompt (phần tử đầu tiên) nếu có
                sys_prompt = [m for m in client.history if m.get("role") == "system"]
                client.history = sys_prompt or []

        self.session_reset.emit(module_id)
        return new_session

    def record_turn(self, module_id: str, user_text: str, reply_text: str) -> None:
        """Ghi 1 lượt trao đổi gồm tin nhắn người dùng và câu trả lời của Ted."""
        session = self.get_session(module_id)
        now = datetime.now(timezone.utc).isoformat()

        user_msg = {"role": "user", "text": user_text, "timestamp": now}
        reply_msg = {"role": "assistant", "text": reply_text, "timestamp": now}

        session.setdefault("messages", []).append(user_msg)
        session.setdefault("messages", []).append(reply_msg)

        session.setdefault("history", []).append({"role": "user", "content": user_text})
        session.setdefault("history", []).append({"role": "assistant", "content": reply_text})

        session["updated_at"] = now
        self._kv.set_json(self._storage_key(module_id), session)

        self.message_appended.emit(module_id, user_msg)
        self.message_appended.emit(module_id, reply_msg)

    def restore_client_history(self, module_id: str, client) -> None:
        """Khôi phục history cho HermesBrainClient từ phiên đã lưu trong DB."""
        if not client or not hasattr(client, "history"):
            return
        session = self.get_session(module_id)
        saved_history = session.get("history", [])
        if not saved_history:
            return

        # Giữ lại system prompt ở đầu
        sys_prompts = [m for m in client.history if m.get("role") == "system"]
        client.history = sys_prompts + list(saved_history)


# Singleton mặc định dùng cho app
chat_session_manager = ChatSessionManager()
