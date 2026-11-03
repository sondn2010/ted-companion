"""Engine base + factory (lazy import) + host quản lý vòng đời engine; lỗi 1 engine không làm sập app."""

import importlib
import logging
from typing import TYPE_CHECKING, Optional

from src.modules_runtime.module_manifest_schema import ModuleManifest

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget

    from src.modules_runtime.app_runtime_context import AppRuntimeContext

logger = logging.getLogger("ted")

# Map cứng trong code (không nạp code từ manifest). Import lười: engine chưa viết → bỏ qua.
ENGINE_CLASSES = {
    "work": "src.engines.work.work_module_engine:WorkModuleEngine",
    "coach": "src.engines.coach.coach_module_engine:CoachModuleEngine",
}


class ModuleEngineBase:
    def __init__(self, manifest: ModuleManifest, ctx: "AppRuntimeContext"):
        self.manifest = manifest
        self.ctx = ctx

    def start(self) -> None:
        """Khởi động timer/scheduler của module."""

    def stop(self) -> None:
        """Dừng và giải phóng tài nguyên."""

    def handle_action(self, action_id: str) -> None:
        """Xử lý 1 mục trong ENGINE_MENUS."""

    def build_dashboard_tab(self) -> "Optional[QWidget]":
        return None

    def on_pet_click(self) -> bool:
        """True nếu engine đã xử lý click đơn (thay cho câu động viên mặc định)."""
        return False


def load_engine_class(engine: str) -> type[ModuleEngineBase]:
    path = ENGINE_CLASSES[engine]
    module_name, _, class_name = path.partition(":")
    return getattr(importlib.import_module(module_name), class_name)


class ModuleEngineHost:
    """Sở hữu các engine đang chạy; `sync()` đồng bộ theo registry.enabled()."""

    def __init__(self, ctx: "AppRuntimeContext"):
        self._ctx = ctx
        self.engines: dict[str, ModuleEngineBase] = {}

    def sync(self):
        wanted = {m.id: m for m in self._ctx.registry.enabled()}
        for module_id in [i for i in self.engines if i not in wanted]:
            self._stop(module_id)
        for module_id, manifest in wanted.items():
            if module_id not in self.engines:
                self._start(manifest)

    def active_engine(self) -> Optional[ModuleEngineBase]:
        active = self._ctx.registry.active()
        return self.engines.get(active.id) if active else None

    def stop_all(self):
        for module_id in list(self.engines):
            self._stop(module_id)

    def dispatch(self, module_id: str, action_id: str):
        engine = self.engines.get(module_id)
        if engine is None:
            logger.warning("Module %s chưa chạy, bỏ qua action %s", module_id, action_id)
            return
        try:
            engine.handle_action(action_id)
        except Exception:
            logger.exception("Engine %s lỗi khi xử lý action %s", module_id, action_id)

    def _start(self, manifest: ModuleManifest):
        try:
            engine = load_engine_class(manifest.engine)(manifest, self._ctx)
            engine.start()
        except ModuleNotFoundError as exc:
            if exc.name != ENGINE_CLASSES[manifest.engine].partition(":")[0]:
                logger.exception("Lỗi import bên trong engine của module %s", manifest.id)
            else:
                logger.warning("Engine '%s' chưa được cài đặt, bỏ qua module %s", manifest.engine, manifest.id)
        except Exception:
            logger.exception("Không khởi động được module %s", manifest.id)
        else:
            self.engines[manifest.id] = engine

    def _stop(self, module_id: str):
        engine = self.engines.pop(module_id, None)
        if engine is None:
            return
        try:
            engine.stop()
        except Exception:
            logger.exception("Engine %s lỗi khi dừng", module_id)
