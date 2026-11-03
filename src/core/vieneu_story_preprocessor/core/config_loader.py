"""Đọc file cấu hình JSON của bộ tiền xử lý; cache theo mtime → sửa file là có hiệu lực ngay (tinh chỉnh nóng)."""

import json
from pathlib import Path

from src.config import get_resource_path

CONFIG_DIR_RELATIVE = "src/core/vieneu_story_preprocessor/config"

_cache: dict[Path, tuple[float, object]] = {}


def config_dir() -> Path:
    return get_resource_path(CONFIG_DIR_RELATIVE)


def load_json(path: Path, default=None):
    """Nội dung JSON của `path` (cùng một đối tượng khi file chưa đổi); file không tồn tại → `default`."""
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return default
    hit = _cache.get(path)
    if hit is not None and hit[0] == mtime:
        return hit[1]
    data = json.loads(path.read_text(encoding="utf-8"))
    _cache[path] = (mtime, data)
    return data


def load_config(name: str):
    return load_json(config_dir() / name)
