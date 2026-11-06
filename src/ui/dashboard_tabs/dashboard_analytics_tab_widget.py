from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton, QTextEdit, QVBoxLayout, QWidget
from shiboken6 import isValid
from src.bridge.openai_client_pool import openai_client_pool
from src.bridge.sync_worker import sync_worker
from src.config import settings
from src.core.background_task_spawner import spawn_background_task
from src.core.i18n import i18n, tr
from src.core.models import db
from src.ui.button_text_escape import btn_text


class DashboardAnalyticsTabWidget(QWidget):
    """Tab 3: Focus Analytics (phiên tập trung, số phút Deep Work, xao nhãng) + đồng bộ lịch sử lên Hermes."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        self.lbl_title = QLabel(tr("analytics_title"))
        self.lbl_title.setObjectName("TitleLabel")
        layout.addWidget(self.lbl_title)

        cards_row = QHBoxLayout()
        cards_row.setSpacing(16)
        self.lbl_t_sessions, self.lbl_metric_sessions = self._create_metric_card(
            cards_row, tr("analytics_card_sessions"), "0"
        )
        self.lbl_t_minutes, self.lbl_metric_minutes = self._create_metric_card(
            cards_row, tr("analytics_card_minutes"), tr("analytics_minutes_unit", minutes=0)
        )
        self.lbl_t_distractions, self.lbl_metric_distractions = self._create_metric_card(
            cards_row, tr("analytics_card_distractions"), "0"
        )
        self.lbl_t_rating, self.lbl_metric_rating = self._create_metric_card(
            cards_row, tr("analytics_card_rating"), "5.0 ★"
        )
        layout.addLayout(cards_row)

        self.txt_analytics_detail = QTextEdit()
        self.txt_analytics_detail.setReadOnly(True)
        self.txt_analytics_detail.setObjectName("AnalyticsReport")
        layout.addWidget(self.txt_analytics_detail, stretch=1)

        btn_row = QHBoxLayout()
        self.btn_refresh = QPushButton(btn_text(tr("analytics_btn_refresh")))
        self.btn_refresh.clicked.connect(self.refresh)
        self.btn_sync = QPushButton(btn_text(tr("analytics_btn_sync")))
        self.btn_sync.setObjectName("PrimaryBtn")
        self.btn_sync.clicked.connect(lambda: spawn_background_task(self._run_sync(), "analytics-sync"))
        btn_row.addWidget(self.btn_sync)
        btn_row.addWidget(self.btn_refresh)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        i18n.language_changed.connect(lambda _: self.retranslate_ui())

    @staticmethod
    def _create_metric_card(parent_layout: QHBoxLayout, title: str, initial_val: str) -> tuple[QLabel, QLabel]:
        frame = QFrame()
        frame.setObjectName("MetricCard")
        fl = QVBoxLayout(frame)
        lbl_t = QLabel(title)
        lbl_t.setObjectName("MetricLabel")
        lbl_v = QLabel(initial_val)
        lbl_v.setObjectName("MetricValue")
        fl.addWidget(lbl_t)
        fl.addWidget(lbl_v)
        parent_layout.addWidget(frame)
        return lbl_t, lbl_v

    def retranslate_ui(self):
        self.lbl_title.setText(tr("analytics_title"))
        self.lbl_t_sessions.setText(tr("analytics_card_sessions"))
        self.lbl_t_minutes.setText(tr("analytics_card_minutes"))
        self.lbl_t_distractions.setText(tr("analytics_card_distractions"))
        self.lbl_t_rating.setText(tr("analytics_card_rating"))
        self.btn_refresh.setText(btn_text(tr("analytics_btn_refresh")))
        self.btn_sync.setText(btn_text(tr("analytics_btn_sync")))
        self.refresh()

    def refresh(self):
        stats = db.get_today_analytics()
        self.lbl_metric_sessions.setText(str(stats["completed_sessions"]))
        self.lbl_metric_minutes.setText(tr("analytics_minutes_unit", minutes=stats["total_focus_minutes"]))
        self.lbl_metric_distractions.setText(str(stats["total_distractions"]))
        self.lbl_metric_rating.setText(f"{stats['average_focus_rating']} ★")
        report_header = tr("analytics_report_header", date=stats['date'])
        companion_label = tr("analytics_report_companion")
        completed_label = tr("analytics_report_completed", count=len(stats['completed_tasks']))
        pending_label = tr("analytics_report_pending", count=len(stats['pending_tasks']))
        none_text = tr("analytics_none")
        empty_text = tr("analytics_empty")
        self.txt_analytics_detail.setHtml(
            f"{report_header}"
            f"<p><b>{companion_label}</b> {settings.character_display_name}</p>"
            f"<p><b>{completed_label}</b> "
            f"{', '.join(stats['completed_tasks']) or none_text}</p>"
            f"<p><b>{pending_label}</b> "
            f"{', '.join(stats['pending_tasks']) or empty_text}</p>"
            f"<p><b>• Parking Lot ({len(stats['parked_ideas'])}):</b> "
            f"{', '.join(stats['parked_ideas']) or empty_text}</p>"
        )

    async def _run_sync(self):
        count = await sync_worker.sync_completed_sessions()
        if not isValid(self):
            return
        work_client = openai_client_pool.for_module("work")
        conn_name = work_client.connection.name if work_client else "Chưa cấu hình"
        QMessageBox.information(
            self, "Sync", f"Đã đồng bộ {count} phiên tập trung mới lên bộ nhớ của Não AI ({conn_name})."
        )
