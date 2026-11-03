"""Danh sách giọng VieNeu đọc từ file cache tĩnh do `sidecar --warmup` ghi lúc cài (voices_<mode>.json trong env dir).

UI chọn giọng dùng cache này nên không cần bật (hay đổi model của) sidecar chỉ để liệt kê giọng.
"""

from dataclasses import dataclass
import json
import logging
from typing import Optional

from src.core.vieneu_runtime_paths import SIDECAR_MODE_BY_MODEL_ID, voices_cache_file

logger = logging.getLogger("ted")


@dataclass(frozen=True)
class VieneuVoice:
    id: str
    name: str
    is_default: bool = False


def parse_voices_payload(data: dict) -> list[VieneuVoice]:
    """Định dạng chung của /v1/voices và file cache: {"default": id|null, "voices": [{"id","name"}]}."""
    default = data.get("default")
    return [VieneuVoice(v["id"], v.get("name") or v["id"], v["id"] == default) for v in data.get("voices", [])]


def read_cached_voices(model_id: str) -> Optional[list[VieneuVoice]]:
    """None nếu chưa có cache (cài bản cũ) hoặc file hỏng."""
    mode = SIDECAR_MODE_BY_MODEL_ID.get(model_id)
    if mode is None:
        return None
    path = voices_cache_file(mode)
    try:
        return parse_voices_payload(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        if path.exists():
            logger.warning("Cache giọng VieNeu hỏng (%s): %s", path, exc)
        return None
