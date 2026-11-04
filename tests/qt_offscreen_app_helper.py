"""Tạo QApplication offscreen dùng chung cho test widget (không cần màn hình thật)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402


def get_qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def flush_qt_garbage() -> None:
    """Đóng/xoá ngay widget top-level mà test tạo ra (deleteLater + GC) để không dồn sang test đo thời gian sau."""
    import gc

    from PySide6.QtCore import QCoreApplication, QEvent

    app = QApplication.instance()
    if app is None:
        return
    for widget in app.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    gc.collect()
    app.processEvents()
