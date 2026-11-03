"""Điều phối bật/tắt chế độ Họp từ mọi điểm vào (menu pet, tray, Dashboard, hotkey `meeting.toggle`).

Các điểm vào chỉ gọi `focus_engine.request_meeting_toggle()`; coordinator nghe tín hiệu đó:
đang họp → dừng; chưa → mở popup chủ đề (đã có sẵn thì đưa lên trước), chọn xong → `start_meeting`.
"""

import logging
from typing import Callable, Optional, Tuple

from PySide6.QtCore import QObject
from PySide6.QtGui import QGuiApplication

from src.ui.meeting_mode.meeting_topic_popup_dialog import MeetingTopicDialog

logger = logging.getLogger("ted")


class MeetingToggleCoordinator(QObject):
    def __init__(self, focus_engine, prefill: Callable[[], Tuple[str, str]], companion=None,
                 dialog_factory: Callable[..., MeetingTopicDialog] = MeetingTopicDialog, parent=None):
        super().__init__(parent)
        self._focus, self._prefill, self._companion, self._factory = focus_engine, prefill, companion, dialog_factory
        self._dialog: Optional[MeetingTopicDialog] = None
        focus_engine.meeting_toggle_requested.connect(self.toggle)

    def toggle(self) -> None:
        if self._focus.in_meeting:
            self._focus.stop_meeting()
            return
        if self._dialog is not None and self._dialog.isVisible():
            self._dialog.raise_()
            self._dialog.focus_input()
            return
        try:
            topic, kind = self._prefill()
        except Exception:  # noqa: BLE001 - gợi ý lỗi → popup trống, vẫn họp được
            logger.exception("Không lấy được gợi ý chủ đề họp")
            topic, kind = "", "team_meeting"
        dlg = self._factory(topic, kind)
        dlg.chosen.connect(lambda t, k: self._focus.start_meeting(t, k))
        self._place_near_companion(dlg)
        self._dialog = dlg
        dlg.show()
        dlg.raise_()
        dlg.focus_input()

    def _place_near_companion(self, dlg: MeetingTopicDialog) -> None:
        """Đặt popup cạnh Ted (kẹp trong màn hình)."""
        if self._companion is None:
            return
        screen = QGuiApplication.screenAt(self._companion.pos()) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        dlg.adjustSize()
        x = min(max(area.left() + 10, self._companion.pos().x() - dlg.width() + self._companion.width()),
                area.right() - dlg.width() - 10)
        y = min(max(area.top() + 10, self._companion.pos().y() - dlg.height() - 12), area.bottom() - dlg.height() - 10)
        dlg.move(x, y)


def install_meeting_mode(ctx, companion) -> MeetingToggleCoordinator:
    """Gọi từ main.py; coordinator là con của `companion` nên không bị GC."""
    from src.core.meeting_mode.meeting_topic_prefill import meeting_prefill
    from src.core.models import db
    return MeetingToggleCoordinator(ctx.focus_engine, lambda: meeting_prefill(db.engine), companion, parent=companion)
