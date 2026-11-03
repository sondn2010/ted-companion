"""Quản lý phím tắt toàn cục: danh mục ⊕ override → đăng ký qua backend native (fallback QShortcut) → gọi callback.

Manager giữ nguồn sự thật của override (`overrides`); UI chỉ việc ghi `overrides` vào settings.hotkeys.
Trạng thái mỗi hành động: global | app_only | failed | disabled | unavailable.
"""

import logging
import sys
from typing import Callable, Optional

from PySide6.QtCore import QObject, Signal

from src.core.hotkeys.hotkey_action_catalog import ACTIONS_BY_ID, HOTKEY_ACTIONS
from src.core.hotkeys.hotkey_binding_resolution_and_conflicts import (
    Binding, conflicting_action, find_duplicates, overrides_from_bindings, resolve_bindings, validate_sequence,
)
from src.core.hotkeys.hotkey_backend_selection_and_fallback_registration import (
    create_backends, default_app_backend, default_native_backend, register_with_fallback,
)
from src.core.hotkeys.hotkey_key_sequence_text_parser import native_display_text, normalize_key_sequence

logger = logging.getLogger("ted")
_INT_IDS = {a.id: i + 1 for i, a in enumerate(HOTKEY_ACTIONS)}
_ID_BY_INT = {v: k for k, v in _INT_IDS.items()}


class GlobalHotkeyManager(QObject):
    bindings_changed = Signal()

    def __init__(self, platform: Optional[str] = None, native_factory: Optional[Callable] = None,
                 app_factory: Optional[Callable] = None):
        super().__init__()
        self.platform = platform or sys.platform
        self._native_factory = native_factory or default_native_backend
        self._app_factory = app_factory or default_app_backend
        self._native = self._app = None
        self._backends_ready = self._applied = self._suspended = False
        self._callbacks: dict[str, Callable] = {}
        self._available: dict[str, Callable[[], bool]] = {}
        self._bindings = resolve_bindings({}, self.platform)
        self._status: dict[str, str] = {a.id: "unavailable" for a in HOTKEY_ACTIONS}

    # ---------- backend (tạo lười: cần QApplication) ----------
    def _ensure_backends(self) -> None:
        if self._backends_ready:
            return
        self._backends_ready = True
        self._native, self._app = create_backends(self._native_factory, self._app_factory)
        for backend in filter(None, (self._native, self._app)):
            backend.activated.connect(self._on_activated)

    def _on_activated(self, int_id: int) -> None:
        action_id = _ID_BY_INT.get(int_id)
        callback = self._callbacks.get(action_id or "")
        if callback is None or self._suspended or not self.is_available(action_id or ""):
            return
        try:
            callback()
        except Exception:
            logger.exception("Callback phím tắt %s lỗi", action_id)

    # ---------- API đăng ký callback ----------
    def bind_callback(self, action_id: str, fn: Callable, available: Optional[Callable[[], bool]] = None) -> None:
        if action_id not in ACTIONS_BY_ID:
            raise KeyError(f"Hành động phím tắt không tồn tại: {action_id}")
        self._callbacks[action_id] = fn
        self._available[action_id] = available or (lambda: True)
        if self._applied:   # gắn muộn (vd. phase Untangle/Hub) → đăng ký ngay
            self._register(action_id)
            self.bindings_changed.emit()

    def is_available(self, action_id: str) -> bool:
        if action_id not in self._callbacks:
            return False
        try:
            return bool(self._available[action_id]())
        except Exception:
            return False

    # ---------- đăng ký / huỷ ----------
    def _unregister(self, action_id: str) -> None:
        for backend in filter(None, (self._native, self._app)):
            backend.unregister(_INT_IDS[action_id])

    def _register(self, action_id: str) -> None:
        self._unregister(action_id)
        b = self._bindings[action_id]
        if not b.enabled:
            self._status[action_id] = "disabled"
        elif not self.is_available(action_id):
            self._status[action_id] = "unavailable"
        elif not validate_sequence(b.seq, self.platform)[0]:
            self._status[action_id] = "failed"
        else:
            self._status[action_id] = register_with_fallback(
                self._native, self._app, _INT_IDS[action_id], b.seq, action_id)

    def _register_all(self) -> None:
        duplicates = {i for ids in find_duplicates(self._bindings).values() for i in ids[1:]}   # trùng: chỉ giữ hành động đầu
        for action in HOTKEY_ACTIONS:
            self._register(action.id)
            if action.id in duplicates:
                self._unregister(action.id)
                self._status[action.id] = "failed"

    def apply(self, overrides: Optional[dict] = None) -> dict[str, str]:
        """Áp dụng override đã lưu và đăng ký tất cả; trả trạng thái từng hành động."""
        self._ensure_backends()
        self._bindings = resolve_bindings(overrides, self.platform)
        self._applied = True
        self._register_all()
        if self._suspended:
            self.suspend()
        self.bindings_changed.emit()
        return dict(self._status)

    def try_rebind(self, action_id: str, seq: str) -> tuple[bool, str]:
        """Đổi phím; lỗi → giữ nguyên phím cũ. reason ∈ "" | "invalid" | "conflict_app" | "conflict_os"."""
        ok, _reason = validate_sequence(seq, self.platform)
        if not ok:
            return False, "invalid"
        norm = normalize_key_sequence(seq) or seq
        if conflicting_action(self._bindings, action_id, norm) is not None:
            return False, "conflict_app"
        old = self._bindings[action_id]
        self._ensure_backends()
        self._bindings[action_id] = Binding(norm, old.enabled)
        if self._native is not None and old.enabled and self.is_available(action_id):
            self._unregister(action_id)
            native_ok, _ = self._native.register(_INT_IDS[action_id], norm)
            if not native_ok:
                self._bindings[action_id] = old   # khôi phục phím cũ
                self._register(action_id)
                self._finish_change(action_id, notify=False)
                return False, "conflict_os"
            self._status[action_id] = "global"
        else:
            self._register(action_id)
        self._finish_change(action_id)
        return True, ""

    def _finish_change(self, action_id: str, notify: bool = True) -> None:
        """Đang suspend (Cài đặt bắt phím) → không để đăng ký mới nuốt phím; rồi báo UI."""
        if self._suspended:
            self._unregister(action_id)
        if notify:
            self.bindings_changed.emit()

    def set_enabled(self, action_id: str, enabled: bool) -> tuple[bool, str]:
        """Bật/tắt; bật lại mà phím đang trùng hành động khác đang bật → từ chối, (False, "conflict_app")."""
        if enabled and conflicting_action(self._bindings, action_id, self._bindings[action_id].seq) is not None:
            return False, "conflict_app"
        self._set_enabled_unchecked(action_id, enabled)
        return True, ""

    def _set_enabled_unchecked(self, action_id: str, enabled: bool) -> None:
        old = self._bindings[action_id]
        self._ensure_backends()
        self._bindings[action_id] = Binding(old.seq, enabled)
        self._register(action_id)
        self._finish_change(action_id)

    def reset(self, action_id: str) -> tuple[bool, str]:
        """Về phím mặc định + bật; trùng/bị chiếm → (False, reason)."""
        default = ACTIONS_BY_ID[action_id].default_for(self.platform)
        if not self._bindings[action_id].enabled:
            self._set_enabled_unchecked(action_id, True)   # phím cũ có thể trùng: try_rebind ngay sau đó đặt phím mặc định
        return self.try_rebind(action_id, default)

    def suspend(self) -> None:
        """Tạm huỷ đăng ký khi Cài đặt đang bắt phím (tổ hợp không bị phím tắt của Ted nuốt)."""
        self._suspended = True
        for action in HOTKEY_ACTIONS:
            self._unregister(action.id)

    def resume(self) -> None:
        if self._suspended:
            self._suspended = False
            self._register_all()
            self.bindings_changed.emit()

    def unregister_all(self) -> None:
        for action in HOTKEY_ACTIONS:
            self._unregister(action.id)

    # ---------- truy vấn ----------
    @property
    def overrides(self) -> dict:
        return overrides_from_bindings(self._bindings, self.platform)

    def status(self, action_id: str) -> str:
        return self._status.get(action_id, "unavailable")

    def sequence(self, action_id: str) -> str:
        return self._bindings[action_id].seq

    def is_enabled(self, action_id: str) -> bool:
        return self._bindings[action_id].enabled

    def display_text(self, action_id: str) -> str:
        """Chữ phím theo OS (vd "⌃⌥⌘Space"); rỗng khi đang tắt / chưa khả dụng → menu không hiện gợi ý."""
        if action_id not in self._bindings or self.status(action_id) in ("disabled", "unavailable"):
            return ""
        return native_display_text(self._bindings[action_id].seq, self.platform)


hotkey_manager = GlobalHotkeyManager()
