"""
HermesClientPool: tạo lại client khi cấu hình kết nối đổi, invalidate sau khi lưu Settings,
và thứ tự phân giải kết nối của module (override → manifest → kết nối đầu tiên).
Dùng AppConfig thật trỏ vào thư mục tạm; không gọi mạng.
"""

from src.bridge.hermes_client_pool import HermesClientPool
from src.config import AppConfig
from src.core.connection_registry_and_settings_migration import HermesConnection


def _pool(tmp_path) -> tuple[HermesClientPool, AppConfig]:
    config = AppConfig(data_dir=tmp_path)
    config.connections = [
        HermesConnection(id="local", name="Local", base_url="http://127.0.0.1:8080/v1", api_key="key-local"),
        HermesConnection(id="vps", name="VPS", base_url="http://100.1.2.3:8642/v1", api_key="key-vps"),
    ]
    config.module_overrides = {}
    return HermesClientPool(config), config


def test_same_client_reused_and_rebuilt_only_when_identity_fields_change(tmp_path):
    pool, config = _pool(tmp_path)
    first = pool.get("local")
    assert pool.get("local") is first

    # Đổi tên hiển thị không đổi identity → giữ nguyên client (và lịch sử chat)
    config.upsert_connection(HermesConnection(id="local", name="Renamed", base_url="http://127.0.0.1:8080/v1", api_key="key-local"))
    assert pool.get("local") is first

    # Đổi URL, API key hoặc model → tạo client mới
    config.upsert_connection(HermesConnection(id="local", name="Renamed", base_url="http://10.0.0.9/v1", api_key="key-local"))
    rebuilt = pool.get("local")
    assert rebuilt is not first and rebuilt.connection.base_url == "http://10.0.0.9/v1"

    config.upsert_connection(HermesConnection(id="local", name="Renamed", base_url="http://10.0.0.9/v1", api_key="other", model="m2"))
    again = pool.get("local")
    assert again is not rebuilt and again.connection.api_key == "other" and again.connection.model == "m2"


def test_get_unknown_connection_returns_none(tmp_path):
    pool, _ = _pool(tmp_path)
    assert pool.get("missing") is None


def test_invalidate_drops_clients_and_their_chat_history(tmp_path):
    pool, _ = _pool(tmp_path)
    old = pool.get("local")
    old.history.append({"role": "user", "content": "lịch sử cũ"})
    pool.invalidate()
    fresh = pool.get("local")
    assert fresh is not old
    assert all(m["content"] != "lịch sử cũ" for m in fresh.history)


def test_for_module_prefers_user_override_over_manifest_default(tmp_path):
    pool, config = _pool(tmp_path)
    pool.manifest_connection_resolver = lambda module_id: "local" if module_id == "work" else None
    config.set_module_override("work", connection="vps")
    assert pool.connection_id_for_module("work") == "vps"
    assert pool.for_module("work").connection.id == "vps"


def test_for_module_falls_back_to_manifest_then_first_connection(tmp_path):
    pool, config = _pool(tmp_path)
    pool.manifest_connection_resolver = lambda module_id: "vps" if module_id == "tutor" else None
    assert pool.connection_id_for_module("tutor") == "vps"
    assert pool.connection_id_for_module("unknown_module") == "local"


def test_stale_override_pointing_to_deleted_connection_is_ignored(tmp_path):
    pool, config = _pool(tmp_path)
    config.set_module_override("work", connection="deleted_conn")
    assert pool.connection_id_for_module("work") == "local"
    assert pool.for_module("work").connection.id == "local"


def test_strict_module_never_falls_back_to_first_connection(tmp_path):
    """Privacy: module coach thiếu/hỏng kết nối → None, KHÔNG rơi về kết nối đầu tiên (profile công việc)."""
    pool, config = _pool(tmp_path)
    pool.strict_module_predicate = lambda module_id: module_id != "work"
    pool.manifest_connection_resolver = lambda module_id: "gone" if module_id == "thcs" else None
    assert pool.connection_id_for_module("thcs") is None   # manifest trỏ kết nối không tồn tại
    assert pool.for_module("thcs") is None
    config.set_module_override("duhoc", connection="deleted_conn")
    assert pool.for_module("duhoc") is None                 # override cũ đã bị xoá
    assert pool.connection_id_for_module("work") == "local"  # work vẫn có fallback


def test_strict_module_still_resolves_valid_connection(tmp_path):
    pool, config = _pool(tmp_path)
    pool.strict_module_predicate = lambda module_id: True
    config.set_module_override("thcs", connection="vps")
    assert pool.for_module("thcs").connection.id == "vps"


def test_no_connections_at_all_returns_none(tmp_path):
    pool, config = _pool(tmp_path)
    config.connections = []
    assert pool.for_module("work") is None
