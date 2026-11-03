"""Tab Dashboard của module work: Rocks (vướng mắc tồn đọng) + panel "Lịch hôm nay" (phase 05 đổ dữ liệu thật)."""

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.engines.work.daily_briefing_builder import sanitize_untrusted_text
from src.engines.work.rock_model_and_repository import rock_age_days

logger = logging.getLogger("ted")
STATUS_LABELS = {"open": "đang mở", "resolved": "đã giải quyết", "dropped": "đã bỏ"}


class WorkRocksAndCalendarTab(QWidget):
    """Mọi thao tác đi qua `engine` (đồng bộ, trên UI thread) nên không có callback nền chạm widget đã huỷ."""

    def __init__(self, engine, parent=None):
        super().__init__(parent)
        self._engine = engine
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(12)

        title = QLabel("🪨 Rocks — vướng mắc tồn đọng")
        title.setObjectName("TitleLabel")
        layout.addWidget(title)

        add_row = QHBoxLayout()
        self.input_rock = QLineEdit()
        self.input_rock.setPlaceholderText("Thêm nhanh 1 Rock (việc đang vướng)...")
        self.input_rock.returnPressed.connect(self._on_add)
        btn_add = QPushButton("+ Thêm Rock")
        btn_add.setObjectName("PrimaryBtn")
        btn_add.clicked.connect(self._on_add)
        add_row.addWidget(self.input_rock, stretch=1)
        add_row.addWidget(btn_add)
        layout.addLayout(add_row)

        self.rock_list = QListWidget()
        self.rock_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.rock_list.customContextMenuRequested.connect(self._on_rock_context_menu)
        layout.addWidget(self.rock_list, stretch=1)

        action_row = QHBoxLayout()
        self.chk_show_closed = QCheckBox("Hiện đã đóng")
        self.chk_show_closed.toggled.connect(lambda _checked: self.refresh())
        self.btn_resolve = QPushButton("✅ Giải quyết")
        self.btn_resolve.setObjectName("PrimaryBtn")
        self.btn_resolve.clicked.connect(lambda: self._on_close("resolve"))
        self.btn_move_to_todo = QPushButton("📋 Chuyển sang Todo")
        self.btn_move_to_todo.clicked.connect(self._on_move_to_todo)
        self.btn_drop = QPushButton("🗑️ Bỏ")
        self.btn_drop.setObjectName("DangerBtn")
        self.btn_drop.clicked.connect(lambda: self._on_close("drop"))
        action_row.addWidget(self.btn_resolve)
        action_row.addWidget(self.btn_move_to_todo)
        action_row.addWidget(self.chk_show_closed)
        action_row.addStretch(1)
        action_row.addWidget(self.btn_drop)
        layout.addLayout(action_row)

        calendar_row = QHBoxLayout()
        lbl_calendar = QLabel("🗓️ Lịch hôm nay")
        lbl_calendar.setObjectName("SectionLabel")
        calendar_row.addWidget(lbl_calendar)
        self.calendar_status = QLabel()
        self.calendar_status.setObjectName("HintLabel")
        btn_sync = QPushButton("🔄")
        btn_sync.setObjectName("IconBtn")
        btn_sync.setToolTip("Đồng bộ lịch ngay")
        btn_sync.clicked.connect(lambda: self._engine.request_calendar_sync())
        calendar_row.addWidget(self.calendar_status, stretch=1)
        calendar_row.addWidget(btn_sync)
        layout.addLayout(calendar_row)
        self.calendar_list = QListWidget()
        self.calendar_list.setMaximumHeight(130)
        layout.addWidget(self.calendar_list)

        self.refresh()

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()

    def refresh(self):
        self._refresh_rocks()
        self._refresh_calendar()

    def _refresh_rocks(self):
        self.rock_list.clear()
        rocks = self._engine.rocks.list(include_closed=self.chk_show_closed.isChecked())
        for rock in rocks:
            text = f"{rock.title} — {rock_age_days(rock)} ngày — {STATUS_LABELS.get(rock.status, rock.status)}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, rock.id)
            self.rock_list.addItem(item)

    def _refresh_calendar(self):
        self.calendar_list.clear()
        self.calendar_status.setText(self._engine.calendar_status_text())
        events = self._engine.today_rows()
        if not events:
            self.calendar_list.addItem("Hôm nay chưa có lịch họp nào.")
            return
        for ev in events:  # tiêu đề lịch là dữ liệu ngoài → làm sạch trước khi hiển thị
            when = "Cả ngày" if ev.all_day else f"{ev.start_at.astimezone():%H:%M}"
            self.calendar_list.addItem(f"{when}  {sanitize_untrusted_text(ev.title)}")

    def _on_add(self):
        title = self.input_rock.text().strip()
        if not title:
            return
        try:
            self._engine.add_rock(title)
        except Exception:
            logger.exception("Không thêm được Rock")
            return
        self.input_rock.clear()
        self.refresh()

    def _on_close(self, how: str):
        item = self.rock_list.currentItem()
        if item is None:
            return
        rock_id = item.data(Qt.ItemDataRole.UserRole)
        try:
            (self._engine.resolve_rock if how == "resolve" else self._engine.drop_rock)(rock_id)
        except Exception:
            logger.exception("Không đóng được Rock")
            return
        self.refresh()

    def _on_move_to_todo(self):
        items = self.rock_list.selectedItems()
        if not items and self.rock_list.currentItem():
            items = [self.rock_list.currentItem()]
        if not items:
            return
        for item in items:
            rock_id = item.data(Qt.ItemDataRole.UserRole)
            try:
                if hasattr(self._engine, "move_rock_to_task"):
                    self._engine.move_rock_to_task(rock_id)
                else:
                    from src.core.models import db
                    db.move_rock_to_task(rock_id)
            except Exception:
                logger.exception("Không chuyển được Rock sang Todo: %s", rock_id)
        self.refresh()
        dashboard = getattr(getattr(self._engine, "ctx", None), "dashboard", None)
        if dashboard is not None and hasattr(dashboard, "refresh_all"):
            dashboard.refresh_all()

    def _on_rock_context_menu(self, pos):
        item = self.rock_list.itemAt(pos)
        if item is None:
            return
        menu = QMenu(self)
        act_move = menu.addAction("📋 Chuyển sang Todo")
        act_resolve = menu.addAction("✅ Giải quyết")
        act_drop = menu.addAction("🗑️ Bỏ")
        chosen = menu.exec(self.rock_list.viewport().mapToGlobal(pos))
        if chosen == act_move:
            self._on_move_to_todo()
        elif chosen == act_resolve:
            self._on_close("resolve")
        elif chosen == act_drop:
            self._on_close("drop")
