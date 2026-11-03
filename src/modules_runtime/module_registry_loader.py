"""Nạp manifest từ thư mục built-in + ~/.ted/modules và áp override từ settings."""

import logging
from pathlib import Path
from typing import Optional

import yaml
from pydantic import ValidationError
from PySide6.QtCore import QObject, Signal

from src.config import AppConfig, get_resource_path, settings as app_settings
from src.core.connection_registry_and_settings_migration import validation_error_summary
from src.modules_runtime.module_manifest_schema import ModuleManifest

logger = logging.getLogger("ted")


def default_module_dirs(config: AppConfig = app_settings) -> list[Path]:
    """Built-in (đọc-only khi đóng gói) trước, thư mục người dùng sau → user thắng khi trùng id."""
    return [get_resource_path("modules"), config.data_dir / "modules"]


def load_manifests(dirs: list[Path]) -> tuple[dict[str, ModuleManifest], list[str]]:
    """Trả về (manifests theo id, danh sách lỗi "<path>: <msg>"). Module lỗi bị bỏ qua, không raise."""
    manifests: dict[str, ModuleManifest] = {}
    errors: list[str] = []
    for base in dirs:
        if not base.is_dir():
            continue
        for manifest_file in sorted(base.glob("*/module.yaml")):
            try:
                raw = yaml.safe_load(manifest_file.read_text(encoding="utf-8"))
                if not isinstance(raw, dict):
                    raise ValueError("module.yaml phải là một mapping")
                manifest = ModuleManifest.model_validate(raw)
                manifest.module_dir = manifest_file.parent
                manifests[manifest.id] = manifest  # dir sau ghi đè dir trước
            except ValidationError as exc:
                errors.append(f"{manifest_file}: {validation_error_summary(exc)}")
            except (OSError, ValueError, yaml.YAMLError) as exc:
                errors.append(f"{manifest_file}: {type(exc).__name__}: {str(exc)[:200]}")
    for err in errors:
        logger.warning("Bỏ qua module: %s", err)
    return manifests, errors


class ModuleRegistry(QObject):
    modules_changed = Signal()

    def __init__(self, config: AppConfig = app_settings, dirs: Optional[list[Path]] = None):
        super().__init__()
        self._config = config
        self._dirs = dirs if dirs is not None else default_module_dirs(config)
        self._manifests: dict[str, ModuleManifest] = {}
        self.errors: list[str] = []
        self.reload()

    def reload(self):
        self._manifests, self.errors = load_manifests(self._dirs)

    def all(self) -> list[ModuleManifest]:
        return sorted(self._manifests.values(), key=lambda m: (m.order, m.id))

    def get(self, module_id: str) -> Optional[ModuleManifest]:
        return self._manifests.get(module_id)

    def is_enabled(self, module_id: str) -> bool:
        manifest = self._manifests.get(module_id)
        if manifest is None:
            return False
        override = self._config.module_override(module_id).enabled
        return manifest.enabled if override is None else override

    def enabled(self) -> list[ModuleManifest]:
        return [m for m in self.all() if self.is_enabled(m.id)]

    def connection_for(self, module_id: str) -> Optional[str]:
        """Override trong Settings, nếu không có thì connection khai báo trong manifest."""
        manifest = self._manifests.get(module_id)
        override = self._config.module_override(module_id).connection
        return override or (manifest.connection if manifest else None)

    def active(self) -> Optional[ModuleManifest]:
        current = self._manifests.get(self._config.active_module)
        if current is not None and self.is_enabled(current.id):
            return current
        enabled = self.enabled()
        return enabled[0] if enabled else None

    def find_by_engine(self, engine: str) -> list[ModuleManifest]:
        return [m for m in self.enabled() if m.engine == engine]

    def set_enabled(self, module_id: str, on: bool):
        if module_id not in self._manifests:
            return
        self._config.set_module_override(module_id, enabled=on)
        self._config.save()
        self.modules_changed.emit()

    def set_active(self, module_id: str):
        if not self.is_enabled(module_id):
            return
        self._config.active_module = module_id
        self._config.save()
        self.modules_changed.emit()
