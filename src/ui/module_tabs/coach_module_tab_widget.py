"""Tab Dashboard của module coach = 2 trang con: "📅 Hôm nay" và "📈 Tiến độ & mốc"."""

from PySide6.QtWidgets import QTabWidget

from src.engines.coach.agenda_kind_launcher import AgendaKindLauncher
from src.engines.coach.coach_module_services import CoachModuleServices
from src.ui.module_tabs.coach_progress_milestones_section import CoachProgressMilestonesSection
from src.ui.module_tabs.coach_today_tab_widget import CoachTodayTabWidget
from src.ui.button_text_escape import btn_text


class CoachModuleTabWidget(QTabWidget):
    def __init__(self, services: CoachModuleServices, launcher: AgendaKindLauncher, parent=None):
        super().__init__(parent)
        self.today = CoachTodayTabWidget(services, launcher)
        self.progress = CoachProgressMilestonesSection(services, launcher)
        self.addTab(self.today, "📅 Hôm nay")
        self.addTab(self.progress, btn_text("📈 Tiến độ & mốc"))

    def refresh(self) -> None:
        self.today.refresh()
        self.progress.refresh()

    def show_progress(self) -> None:
        self.progress.refresh()
        self.setCurrentWidget(self.progress)

    def show_today(self) -> None:
        self.today.refresh()
        self.setCurrentWidget(self.today)
