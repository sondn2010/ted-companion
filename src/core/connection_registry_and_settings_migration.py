"""
Mô hình kết nối OpenAI-compatible (không giới hạn số lượng) + hàm thuần di trú settings.json v1 → v2.

v1: một cặp cố định local_* / vps_* + "mode".
v2: "connections" (danh sách), "modules" {id: {enabled, connection}}, "active_module".
"""

import logging
from typing import Mapping, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, Field, ValidationError, field_validator

logger = logging.getLogger("ted")

SETTINGS_SCHEMA_VERSION = 2

DEFAULT_LOCAL_BASE_URL = "http://127.0.0.1:8000/v1"
DEFAULT_MODEL_NAME = "gpt-4o-mini"

# Các khoá v1 bị thay thế bởi "connections" / "modules" trong v2
_V1_CONNECTION_KEYS = (
    "mode", "model_name",
    "local_base_url", "local_api_key",
    "vps_base_url", "vps_api_key",
)


class OpenAIConnection(BaseModel):
    """Một endpoint OpenAI-compatible mà module có thể dùng."""

    id: str = Field(pattern=r"^[a-z0-9_-]{1,32}$")
    name: str = Field(min_length=1)
    base_url: str
    api_key: str = ""
    model: str = DEFAULT_MODEL_NAME

    @field_validator("base_url")
    @classmethod
    def _validate_base_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        parsed = urlparse(value)
        if parsed.scheme not in ("http", "https") or not parsed.netloc or " " in value:
            raise ValueError("base_url phải là URL http:// hoặc https:// có host hợp lệ")
        return value

    def identity_key(self) -> tuple:
        """Bộ giá trị quyết định khi nào client cần được tạo lại."""
        return (self.base_url, self.api_key, self.model)


# Backward compatibility aliases
HermesConnection = OpenAIConnection
AIConnection = OpenAIConnection


class ModuleOverride(BaseModel):
    """Ghi đè cấu hình manifest của module do người dùng chọn trong Settings."""

    enabled: Optional[bool] = None
    connection: Optional[str] = None


def coerce_setting_value(cast, value, default):
    """Ép kiểu an toàn: giá trị sai kiểu trong file (null, "abc") → giữ mặc định thay vì crash lúc import."""
    try:
        return default if value is None else cast(value)
    except (TypeError, ValueError):
        logger.warning("Giá trị settings không hợp lệ %r → dùng mặc định %r", value, default)
        return default


def validation_error_summary(exc: ValidationError) -> str:
    """Tóm tắt lỗi pydantic KHÔNG kèm giá trị đầu vào (tránh lộ api_key vào log)."""
    return "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors(include_input=False))


def _with_scheme(url: str) -> str:
    """URL v1 thiếu scheme (vd "127.0.0.1:8000/v1") → thêm http:// thay vì bị loại bỏ."""
    return url if "://" in url else f"http://{url}"


def _connection_dict(conn_id: str, name: str, base_url: str, api_key: str, model: str) -> dict:
    return {"id": conn_id, "name": name, "base_url": _with_scheme(base_url), "api_key": api_key, "model": model}


def migrate_settings_payload(raw: dict, env: Mapping[str, str]) -> tuple[dict, bool]:
    """
    Hàm thuần. Trả về (payload_v2, changed). Idempotent với payload đã là v2.
    Biến môi trường (OPENAI_* / HERMES_*) chỉ dùng làm giá trị mặc định khi file thiếu khoá.
    """
    version = raw.get("schema_version")
    if isinstance(version, int) and version >= SETTINGS_SCHEMA_VERSION:
        return raw, False  # v2 hoặc mới hơn: không đụng vào

    model = raw.get("model_name") or env.get("OPENAI_MODEL") or env.get("OPENAI_MODEL_NAME") or env.get("HERMES_MODEL_NAME") or DEFAULT_MODEL_NAME
    local_url = raw.get("local_base_url") or env.get("OPENAI_BASE_URL") or env.get("OPENAI_LOCAL_BASE_URL") or env.get("HERMES_LOCAL_BASE_URL") or DEFAULT_LOCAL_BASE_URL
    local_key = raw.get("local_api_key") if raw.get("local_api_key") is not None else env.get("OPENAI_API_KEY", env.get("HERMES_LOCAL_API_KEY", ""))
    vps_url = raw.get("vps_base_url") or env.get("OPENAI_VPS_BASE_URL") or env.get("HERMES_VPS_BASE_URL") or DEFAULT_LOCAL_BASE_URL
    vps_key = raw.get("vps_api_key") if raw.get("vps_api_key") is not None else env.get("OPENAI_VPS_API_KEY", env.get("HERMES_VPS_API_KEY", ""))

    # Giữ cả 2 kết nối kể cả khi URL trùng nhau
    connections = [
        _connection_dict("local", "Não AI Local", local_url, local_key, model),
        _connection_dict("vps", "Não AI VPS", vps_url, vps_key, model),
    ]

    mode = raw.get("mode") or env.get("TED_CONNECTION_MODE") or "local"
    if mode not in ("local", "vps"):
        mode = "local"

    payload = {k: v for k, v in raw.items() if k not in _V1_CONNECTION_KEYS}
    payload["schema_version"] = SETTINGS_SCHEMA_VERSION
    payload["connections"] = connections
    payload["modules"] = {"work": {"connection": mode}}
    payload.setdefault("active_module", "work")
    return payload, True
