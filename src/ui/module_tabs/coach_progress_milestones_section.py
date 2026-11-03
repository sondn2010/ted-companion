"""Mục "Tiến độ & mốc": mốc theo ngày, checklist, thống kê 7 ngày theo môn, câu bị cờ, lịch sử bài viết."""

import logging
from collections import defaultdict
from datetime import date, timedelta

from pydantic import ValidationError
from PySide6.QtWidgets import QCheckBox, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from src.engines.coach.agenda_kind_launcher import AgendaKindLauncher, show_dialog
from src.engines.coach.coach_local_day import day_bounds_utc
from src.engines.coach.coach_module_services import CoachModuleServices
from src.engines.coach.coach_quiz_writing_report_schemas import WritingGradeResult
from src.engines.coach.coach_stats_builder import subject_of
from src.ui.quiz.writing_result_dialog import WritingResultDialog
from src.ui.quiz.plain_text_label import plain_label
from src.ui.button_text_escape import btn_text

logger = logging.getLogger("ted")


def subject_stats_7d(services: CoachModuleServices) -> list[tuple[str, int, int]]:
    """[(môn, số câu trả lời, số đúng)] trong 7 ngày địa phương gần nhất, nhiều câu nhất trước."""
    today = services.today()
    start, _ = day_bounds_utc(today - timedelta(days=6), services.tz)
    _, end = day_bounds_utc(today, services.tz)
    attempts = services.attempts.attempts_between(services.module_id, start, end)
    items = services.attempts.load_items({a.item_id for a in attempts})
    totals: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for attempt in attempts:
        item = items.get(attempt.item_id)
        if item is not None:
            bucket = totals[subject_of(item.topic)]
            bucket[0] += 1
            bucket[1] += int(attempt.correct)
    return sorted(((subject, n, ok) for subject, (n, ok) in totals.items()), key=lambda row: -row[1])


def _heading(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("SectionLabel")
    return label


class CoachProgressMilestonesSection(QWidget):
    def __init__(self, services: CoachModuleServices, launcher: AgendaKindLauncher, parent=None):
        super().__init__(parent)
        self._s, self._launcher = services, launcher
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 12, 0, 0)
        self._host = QWidget()
        self._host.setObjectName("TransparentHost")
        self._layout = QVBoxLayout(self._host)
        self._layout.setSpacing(8)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._host)
        outer.addWidget(scroll)
        self.refresh()

    def refresh(self) -> None:
        while self._layout.count():
            child = self._layout.takeAt(0).widget()
            if child is not None:
                child.setParent(None)   # tách hẳn rồi mới xoá, tránh xoá trễ trên widget đã mồ côi
                child.deleteLater()
        snapshot = self._s.plans.get_snapshot(self._s.module_id)
        self._add_milestones(snapshot.milestones if snapshot else [])
        self._add_checklist(snapshot.checklist if snapshot else [])
        self._add_stats()
        self._add_flagged()
        self._add_writing_history()
        self._layout.addStretch(1)

    def _add(self, widget: QWidget) -> None:
        self._layout.addWidget(widget)

    def _add_milestones(self, milestones) -> None:
        self._add(_heading("🗓️ Mốc quan trọng"))
        today = self._s.today()
        for m in sorted(milestones, key=lambda x: x.due_date):
            days = (m.due_date - today).days
            suffix = f"còn {days} ngày" if days >= 0 else f"quá hạn {-days} ngày"
            label = plain_label(f"{m.due_date:%d/%m/%Y} · {m.title} ({suffix})")
            if days < 0:
                label.setObjectName("ErrorLabel")
            self._add(label)
        if not milestones:
            self._add(QLabel("Chưa có mốc nào."))

    def _add_checklist(self, checklist) -> None:
        self._add(_heading("☑️ Checklist"))
        done_ids = self._s.plans.done_ids(self._s.module_id)
        for entry in checklist:
            hermes_done = entry.status == "done"
            local_done = entry.id in done_ids   # ✓ cục bộ (chưa báo) tính đến lần sync sau; đã báo thì Hermes quyết định
            done = hermes_done or local_done
            text = entry.title + (f" · hạn {entry.due_date:%d/%m}" if entry.due_date else "") + \
                ("" if entry.status == "todo" else f" [{entry.status}]")
            box = QCheckBox(btn_text(text))
            box.setChecked(done)
            box.setEnabled(not hermes_done)   # tick cục bộ còn hoàn tác được trước khi báo Hermes
            box.toggled.connect(lambda checked, eid=entry.id: self._toggle(eid, checked))
            self._add(box)
        if not checklist:
            self._add(QLabel("Chưa có checklist."))

    def _toggle(self, entry_id: str, checked: bool) -> None:
        (self._s.mark_done if checked else self._s.unmark_done)(entry_id)

    def _add_stats(self) -> None:
        self._add(_heading("📊 7 ngày qua"))
        rows = subject_stats_7d(self._s)
        for subject, answered, correct in rows:
            self._add(QLabel(f"{subject}: {correct}/{answered} đúng ({round(100 * correct / answered)}%)"))
        if not rows:
            self._add(QLabel("Chưa có lượt trả lời nào."))

    def _add_flagged(self) -> None:
        self._add(_heading("🚩 Câu đã báo sai"))
        for item in self._s.items.flagged_items(self._s.module_id):
            self._add(self._row(f"{item.question} — {item.flag_reason}", "Bỏ cờ",
                                lambda iid=item.id: self._unflag(iid)))

    def _unflag(self, item_id: str) -> None:
        self._s.items.unflag_item(item_id)
        self.refresh()

    def _add_writing_history(self) -> None:
        self._add(_heading("✍️ Lịch sử bài viết"))
        for row in self._s.plans.recent_submissions(self._s.module_id, 10):
            when = row.created_at.astimezone(self._s.tz)
            title = f"{when:%d/%m %H:%M} · {row.prompt[:60]}"
            if row.result_json:
                try:
                    result = WritingGradeResult.model_validate_json(row.result_json)
                except ValidationError:   # 1 dòng hỏng không được làm hỏng cả tab
                    logger.warning("Kết quả chấm của bài %s hỏng, hiện như chưa chấm", row.id)
                    self._add(self._row(f"{title} · kết quả hỏng", "Chấm lại",
                                        lambda sid=row.id: self._launcher.regrade_writing(sid)))
                    continue
                self._add(self._row(f"{title} · {result.overall:g}/10", "Xem",
                                    lambda r=result: show_dialog(WritingResultDialog(r))))
            else:
                self._add(self._row(f"{title} · chưa chấm", "Chấm lại",
                                    lambda sid=row.id: self._launcher.regrade_writing(sid)))

    @staticmethod
    def _row(text: str, button_text: str, on_click) -> QWidget:
        row = QFrame()
        row.setObjectName("Card")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(12, 8, 12, 8)
        label = plain_label(text, word_wrap=True)
        layout.addWidget(label, stretch=1)
        button = QPushButton(btn_text(button_text))
        button.clicked.connect(lambda _=False: on_click())
        layout.addWidget(button)
        return row
