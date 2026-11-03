"""Tab "Hôm nay" của module coach: tiêu đề + đếm ngược, danh sách agenda 5 loại, dòng policy, lần đồng bộ cuối."""

import logging
from datetime import date

from PySide6.QtWidgets import QCheckBox, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from src.engines.coach.agenda_kind_launcher import AgendaKindLauncher
from src.engines.coach.coach_module_services import CoachModuleServices
from src.engines.coach.coach_sync_plan_schemas import AgendaItem
from src.ui.quiz.plain_text_label import plain_label
from src.ui.button_text_escape import btn_text

logger = logging.getLogger("ted")
KIND_ICONS = {"quiz": "🧠", "step": "🧩", "writing": "✍️", "chat": "💬", "task": "☑️"}


def countdown_text(countdown: dict, today: date) -> str:
    """{label, date:'YYYY-MM-DD'} → "Còn N ngày tới {label}"; thiếu/sai dữ liệu → rỗng (không làm hỏng tab)."""
    try:
        days = (date.fromisoformat(str(countdown["date"])[:10]) - today).days
        return f"Còn {days} ngày tới {countdown['label']}" if days >= 0 else f"{countdown['label']} đã qua {-days} ngày"
    except (KeyError, ValueError, TypeError):
        return ""


def agenda_row_text(item: AgendaItem, done: bool) -> str:
    parts = [f"{KIND_ICONS.get(item.kind, '•')} {item.title}"]
    if item.minutes:
        parts.append(f"{item.minutes}'")
    if item.when:
        parts.append(item.when)
    return " · ".join(parts) + ("  ✓" if done else "")


class CoachTodayTabWidget(QWidget):
    """Widget mới mỗi lần dựng; chỉ đọc DB + gọi launcher trên UI thread, không có callback nền chạm vào widget."""

    def __init__(self, services: CoachModuleServices, launcher: AgendaKindLauncher, parent=None):
        super().__init__(parent)
        self._s, self._launcher = services, launcher
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 12, 0, 0)
        root.setSpacing(12)
        self.onboarding_banner = QFrame()   # hiện khi Hermes báo needs_onboarding
        self.onboarding_banner.setObjectName("WarningBanner")
        banner_row = QHBoxLayout(self.onboarding_banner)
        banner_row.setContentsMargins(12, 8, 12, 8)
        banner_label = QLabel("👋 Ted cần làm quen trước khi lên kế hoạch.")
        banner_label.setObjectName("WarningLabel")
        btn_onboarding = QPushButton("Bắt đầu làm quen")
        btn_onboarding.setObjectName("PrimaryBtn")
        btn_onboarding.clicked.connect(lambda: self._s.start_onboarding())
        banner_row.addWidget(banner_label, stretch=1)
        banner_row.addWidget(btn_onboarding)
        root.addWidget(self.onboarding_banner)
        self.title_label = plain_label()
        self.title_label.setObjectName("TitleLabel")
        self.countdown_label = plain_label()
        self.countdown_label.setObjectName("WarningLabel")
        root.addWidget(self.title_label)
        root.addWidget(self.countdown_label)
        self.agenda_host = QWidget()
        self.agenda_layout = QVBoxLayout(self.agenda_host)
        self.agenda_layout.setContentsMargins(0, 0, 0, 0)
        self.agenda_host.setObjectName("TransparentHost")
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.agenda_host)
        root.addWidget(scroll, stretch=1)
        self.policy_label = QLabel()
        self.policy_label.setObjectName("HintLabel")
        self.rationale_label = plain_label()
        self.rationale_label.setObjectName("HintLabel")
        self.rationale_label.setWordWrap(True)
        self.sync_label = QLabel()
        self.sync_label.setObjectName("HintLabel")
        footer = QHBoxLayout()
        footer.addWidget(self.sync_label, stretch=1)
        btn_sync = QPushButton("🔄 Đồng bộ")
        btn_sync.setObjectName("PrimaryBtn")
        btn_sync.clicked.connect(lambda: self._s.request_sync())
        footer.addWidget(btn_sync)
        for widget in (self.policy_label, self.rationale_label):
            root.addWidget(widget)
        root.addLayout(footer)
        self.refresh()

    def refresh(self) -> None:
        self.onboarding_banner.setVisible(self._s.needs_onboarding())
        snapshot = self._s.plans.get_snapshot(self._s.module_id)
        policy = self._s.policy()
        display = snapshot.display if snapshot else None
        title = " · ".join(p for p in (display.title, display.phase) if p) if display else ""
        self.title_label.setText(title or self._s.manifest.name)
        self.countdown_label.setText(countdown_text(display.countdown, self._s.today()) if display and display.countdown else "")
        self._fill_agenda(snapshot.agenda if snapshot else [])
        self.policy_label.setText(
            f"Ôn mỗi {policy.review_interval_mins} phút · tối đa {policy.daily_cap} câu/ngày · {policy.new_per_day} câu mới/ngày")
        self.rationale_label.setText(policy.rationale)
        self.rationale_label.setVisible(bool(policy.rationale))
        synced = self._s.plans.get_synced_at(self._s.module_id)
        stale = synced is not None and not self._s.plan_is_today()
        self.sync_label.setText(
            "Chưa đồng bộ" if synced is None else
            f"Đồng bộ lần cuối: {synced.astimezone(self._s.tz):%d/%m %H:%M}" + (
                f" · Kế hoạch từ {synced.astimezone(self._s.tz):%d/%m} (chưa cập nhật hôm nay)" if stale else ""))

    def _fill_agenda(self, agenda: list[AgendaItem]) -> None:
        while self.agenda_layout.count():
            child = self.agenda_layout.takeAt(0).widget()
            if child is not None:
                child.setParent(None)   # tách hẳn rồi mới xoá, tránh xoá trễ trên widget đã mồ côi
                child.deleteLater()
        done_ids = self._s.plans.done_ids(self._s.module_id)
        if not agenda:
            empty = QLabel("Chưa có kế hoạch hôm nay. Bấm 🔄 Đồng bộ để Ted hỏi gia sư nhé.")
            empty.setObjectName("MutedLabel")
            empty.setWordWrap(True)
            self.agenda_layout.addWidget(empty)
        for item in agenda:
            self.agenda_layout.addWidget(self._build_row(item, item.id in done_ids))
        self.agenda_layout.addStretch(1)

    def _build_row(self, item: AgendaItem, done: bool) -> QWidget:
        row = QFrame()   # mỗi mục agenda là một Card nhỏ
        row.setObjectName("Card")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(12, 8, 12, 8)
        if item.kind == "task":   # việc thường: chỉ cần tick
            box = QCheckBox(btn_text(agenda_row_text(item, done)))
            box.setChecked(done)
            box.setEnabled(not done)
            box.toggled.connect(lambda checked, it=item: checked and self._launcher.launch(it))
            layout.addWidget(box, stretch=1)
            return row
        label = plain_label(agenda_row_text(item, done), word_wrap=True)
        layout.addWidget(label, stretch=1)
        button = QPushButton("Làm lại" if done else "Bắt đầu")
        button.setObjectName("GhostBtn" if done else "PrimaryBtn")
        button.clicked.connect(lambda _=False, it=item: self._launcher.launch(it))
        layout.addWidget(button)
        return row
