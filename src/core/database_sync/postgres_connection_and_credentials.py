"""Tài khoản/mật khẩu PostgreSQL lưu trong keyring của hệ điều hành + mở kết nối theo cấu hình đồng bộ."""

import json

import keyring
import psycopg

from src.core.database_sync.database_sync_config import DatabaseSyncConfig

_KEYRING_SERVICE = "TedCompanion.DatabaseSync"
_KEYRING_ENTRY = "postgres"


def load_credentials() -> tuple[str, str]:
    raw = keyring.get_password(_KEYRING_SERVICE, _KEYRING_ENTRY)
    if not raw:
        return "", ""
    data = json.loads(raw)
    return str(data.get("user") or ""), str(data.get("password") or "")


def save_credentials(user: str, password: str) -> None:
    keyring.set_password(_KEYRING_SERVICE, _KEYRING_ENTRY, json.dumps({"user": user, "password": password}))


def connect_postgres(config: DatabaseSyncConfig, user: str | None = None, password: str | None = None) -> psycopg.Connection:
    """user/password None → đọc từ keyring (luồng nền gọi mỗi lần đồng bộ)."""
    if user is None or password is None:
        user, password = load_credentials()
    return psycopg.connect(
        host=config.host.strip(), port=config.port, dbname=config.database, user=user, password=password,
        sslmode=config.sslmode, connect_timeout=10, autocommit=True, application_name="ted-companion",
    )
