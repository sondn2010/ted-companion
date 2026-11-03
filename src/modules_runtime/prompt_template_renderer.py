"""Render prompt md của module work. Dùng {{var}} (không dùng str.format vì md chứa dấu { } của JSON)."""

import logging
import re
from typing import Mapping, Optional

from src.modules_runtime.module_manifest_schema import ModuleManifest

logger = logging.getLogger("ted")
_VAR = re.compile(r"\{\{\s*(\w+)\s*\}\}")
_BULLET = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+(.*\S)\s*$")


def render_prompt(template: str, values: Mapping[str, object]) -> str:
    """Thay {{var}} theo values; biến không có trong values giữ nguyên."""
    return _VAR.sub(lambda m: str(values[m.group(1)]) if m.group(1) in values else m.group(0), template)


def load_prompt(manifest: ModuleManifest, key: str, values: Mapping[str, object]) -> Optional[str]:
    path = manifest.prompt_path(key)
    if path is None:
        logger.warning("Prompt '%s' của module %s không khả dụng", key, manifest.id)
        return None
    try:
        return render_prompt(path.read_text(encoding="utf-8"), values)
    except OSError as exc:
        logger.warning("Không đọc được prompt %s: %s", path, exc)
        return None


def parse_bullet_lines(md: str) -> list[str]:
    """Lấy các dòng gạch đầu dòng (pool câu động viên)."""
    return [m.group(1) for line in md.splitlines() if (m := _BULLET.match(line))]
