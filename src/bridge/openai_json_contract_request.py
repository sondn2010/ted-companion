"""
Gọi OpenAI-compatible API theo hợp đồng JSON: trích khối <json>…</json>, validate bằng pydantic, retry đúng 1 lần.
Mọi thất bại → None để bên gọi giữ nguyên dữ liệu cache.
"""

import json
import logging
import re
from typing import Optional, TypeVar

from pydantic import BaseModel, ValidationError

from src.bridge.openai_client import (
    OpenAIBrainClient,
    OpenAIRequestRejectedError,
    OpenAIUnavailableError,
)

logger = logging.getLogger("ted")

T = TypeVar("T", bound=BaseModel)

JSON_BLOCK_RE = re.compile(r"<json>\s*(.*?)\s*</json>", re.S)
JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.S)


class OpenAIContractError(Exception):
    """Máy chủ AI trả về {"error": "..."} — lỗi nghiệp vụ, không retry."""


# Backward compatibility alias
HermesContractError = OpenAIContractError


def extract_json_block(text: str) -> str:
    """Ưu tiên <json> → ```json fence → đoạn từ "{" đầu tiên tới "}" cuối cùng; không có → ValueError."""
    for pattern in (JSON_BLOCK_RE, JSON_FENCE_RE):
        match = pattern.search(text)
        if match:
            return match.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        return text[start:end + 1]
    raise ValueError("Không tìm thấy JSON trong phản hồi")


async def request_openai_json_contract(
    client: OpenAIBrainClient,
    prompt: str,
    schema: type[T],
    *,
    system: Optional[str] = None,
    timeout: float = 60.0,
) -> Optional[T]:
    head = [{"role": "system", "content": system}] if system else []
    message = prompt
    for _attempt in range(2):
        try:
            raw = await client.complete_text(head + [{"role": "user", "content": message}], timeout=timeout)
        except OpenAIUnavailableError as exc:
            logger.info("request_json offline [%s]: %s", schema.__name__, exc)
            return None  # offline: không retry, bên gọi giữ cache
        except OpenAIRequestRejectedError as exc:
            logger.warning("request_json bị từ chối [%s]: %s", schema.__name__, exc)
            return None  # 4xx: lỗi hợp đồng, gửi lại y hệt cũng vô ích
        try:
            data = json.loads(extract_json_block(raw))
            if isinstance(data, dict) and "error" in data and "error" not in schema.model_fields:
                # mọi dict có khoá "error" đều là báo lỗi (kể cả kèm events rỗng), trừ schema tự khai báo trường error
                raise OpenAIContractError(str(data["error"]))
            return schema.model_validate(data)
        except OpenAIContractError as exc:
            logger.warning("request_json [%s] AI báo lỗi: %s", schema.__name__, exc)
            return None
        except (ValueError, ValidationError) as exc:
            logger.warning("request_json [%s] JSON không hợp lệ: %s", schema.__name__, str(exc)[:300])
            message = prompt + f"\n\n[TED_JSON_ERROR] {str(exc)[:300]}\nChỉ trả về JSON hợp lệ trong <json></json>."
    return None


# Backward compatibility alias
request_json = request_openai_json_contract
