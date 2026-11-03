"""Backend dự phòng (không toàn cục): bắt KeyPress bằng event filter mức QApplication – chỉ hoạt động khi
một cửa sổ Ted đang có focus.

Không dùng QShortcut gắn vào QWidget ẩn: Qt bỏ qua shortcut có widget chủ không visible (kể cả
ApplicationShortcut) nên phím tắt dự phòng sẽ không bao giờ chạy.
"""

from PySide6.QtCore import QCoreApplication, QEvent, QObject, Signal
from PySide6.QtGui import QKeyEvent, QKeySequence


class AppLevelQShortcutBackend(QObject):
    is_global = False
    activated = Signal(int)

    def __init__(self):
        super().__init__()
        self._combos: dict[int, int] = {}   # tổ hợp Qt (keyCombination.toCombined) → hotkey_id
        app = QCoreApplication.instance()
        if app is None:
            raise RuntimeError("Cần QApplication trước khi tạo backend phím tắt trong app")
        app.installEventFilter(self)

    def eventFilter(self, obj, event) -> bool:
        if (self._combos and event.type() == QEvent.Type.KeyPress and isinstance(event, QKeyEvent)
                and not event.isAutoRepeat()):
            hotkey_id = self._combos.get(event.keyCombination().toCombined())
            if hotkey_id is not None:
                self.activated.emit(hotkey_id)
                return True   # nuốt phím: tương đương ApplicationShortcut
        return False

    def register(self, hotkey_id: int, seq: str) -> tuple[bool, str]:
        key_seq = QKeySequence(seq)
        if key_seq.isEmpty():
            return False, "unsupported_key"
        combo = key_seq[0].toCombined()
        if self._combos.get(combo, hotkey_id) != hotkey_id:   # giống RegisterHotKey: tổ hợp đã thuộc id khác
            return False, "os_taken"
        self.unregister(hotkey_id)
        self._combos[combo] = hotkey_id
        return True, ""

    def unregister(self, hotkey_id: int) -> None:
        for combo in [c for c, hid in self._combos.items() if hid == hotkey_id]:
            del self._combos[combo]
