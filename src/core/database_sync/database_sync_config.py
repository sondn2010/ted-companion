"""Cấu hình đồng bộ dữ liệu (lưu trong settings.json, khoá "database_sync") + xuất/nhập file JSON.

KHÔNG chứa tài khoản/mật khẩu: hai thứ đó nằm trong keyring của hệ điều hành và không bao giờ được xuất ra file.
Module thuần pydantic (không import Qt/psycopg) vì src.config import nó lúc khởi động.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

EXPORT_APP = "Ted Companion"
EXPORT_KIND = "database_sync"
EXPORT_VERSION = 1


class DatabaseSyncConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    mode: Literal["local_only", "postgres_sync", "api_sync"] = "local_only"
    host: str = ""
    port: int = Field(default=5432, ge=1, le=65535)
    database: str = "ted"
    schema_name: str = Field(default="ted_sync", alias="schema", pattern=r"^[a-z_][a-z0-9_]*$")
    sslmode: Literal["disable", "allow", "prefer", "require", "verify-ca", "verify-full"] = "require"
    sync_interval_minutes: int = Field(default=30, ge=1, le=240)   # kéo định kỳ; thay đổi cục bộ đẩy ngay
    api_url: str = ""   # chế độ api_sync: địa chỉ ted-sync-api (khoá API nằm trong keyring)

    @field_validator("api_url")
    @classmethod
    def _normalize_api_url(cls, value: str) -> str:
        return value.strip().rstrip("/")

    @property
    def enabled(self) -> bool:
        if self.mode == "api_sync":
            return bool(self.api_url)
        return self.mode == "postgres_sync" and bool(self.host.strip())

    def to_payload(self) -> dict:
        return self.model_dump(by_alias=True)


class DatabaseSyncImportError(ValueError):
    """code: wrong_file | unsupported_version | invalid (UI đổi sang câu thông báo theo ngôn ngữ)."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(detail or code)
        self.code = code
        self.detail = detail


def build_export(config: DatabaseSyncConfig) -> dict:
    return {
        "app": EXPORT_APP,
        "kind": EXPORT_KIND,
        "version": EXPORT_VERSION,
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "database": config.to_payload(),
    }


def parse_import(raw: object, current: DatabaseSyncConfig) -> DatabaseSyncConfig:
    """Đọc file đã xuất. Khoá thiếu giữ giá trị hiện tại, khoá lạ (kể cả user/password nếu ai đó tự thêm) bị bỏ qua."""
    if not isinstance(raw, dict) or raw.get("app") != EXPORT_APP or raw.get("kind") != EXPORT_KIND:
        raise DatabaseSyncImportError("wrong_file")
    if raw.get("version") != EXPORT_VERSION:
        raise DatabaseSyncImportError("unsupported_version", str(raw.get("version")))
    database = raw.get("database")
    if not isinstance(database, dict):
        raise DatabaseSyncImportError("wrong_file")
    known = {f.alias or name for name, f in DatabaseSyncConfig.model_fields.items()}
    merged = current.to_payload()
    merged.update({k: v for k, v in database.items() if k in known})
    try:
        return DatabaseSyncConfig.model_validate(merged)
    except ValidationError as exc:
        raise DatabaseSyncImportError("invalid", "; ".join(e["msg"] for e in exc.errors())) from exc
