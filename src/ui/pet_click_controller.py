from typing import Callable, Optional

from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QApplication


class PetClickController(QObject):
    """
    Phân biệt click đơn / đúp / nhiều lần (mặc định 5 lần = mở cấu hình nhân vật — hành động ẩn, ghi trong Trợ giúp).
    Qt gửi mouseRelease TRƯỚC mouseDoubleClick nên click đơn bị hoãn `doubleClickInterval` bằng QTimer.
    Mỗi click (kể cả cú thứ 2 của double click) đếm 1 lần; chuỗi click ngắt quãng > interval thì chốt hành động:
    1 lần → đơn, 2–4 lần → đúp, đủ `multi_count` → `on_multi` ngay lập tức. Kéo thả (dragged) không tính là click.
    Không truyền `on_multi` thì double click bắn ngay như trước (không cần chờ thêm click).
    """

    def __init__(self, on_single: Callable[[], None], on_double: Callable[[], None],
                 interval_ms: Callable[[], int] = QApplication.doubleClickInterval, parent=None,
                 on_multi: Optional[Callable[[], None]] = None, multi_count: int = 5):
        super().__init__(parent)
        self._on_single = on_single
        self._on_double = on_double
        self._on_multi = on_multi
        self._multi_count = multi_count
        self._interval_ms = interval_ms
        self._in_double_click = False
        self._count = 0
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._fire)

    def on_release(self, dragged: bool) -> None:
        if self._in_double_click:
            self._in_double_click = False  # release thứ 2 của cú double click
            return
        if not dragged:
            self._register_click()

    def on_double_click(self) -> None:
        self._in_double_click = True
        if self._on_multi is None:   # hành vi cũ: double click mở chat ngay
            self._timer.stop()
            self._count = 0
            self._on_double()
            return
        self._register_click()

    def _register_click(self) -> None:
        self._count += 1
        if self._on_multi is not None and self._count >= self._multi_count:
            self._timer.stop()
            self._count = 0
            self._on_multi()
            return
        self._timer.start(self._interval_ms())

    def _fire(self) -> None:
        count, self._count = self._count, 0
        if count == 1:
            self._on_single()
        elif count >= 2:
            self._on_double()
