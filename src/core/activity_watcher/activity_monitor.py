"""Bộ giám sát hoạt động & cảnh báo xao nhãng trong giờ học (Activity Monitor)."""

from datetime import date, datetime, timezone
import logging
import time
from typing import Callable, Optional

from PySide6.QtCore import QObject, QTimer, Signal

from src.core.activity_watcher.activity_classifier import (
    ActivityCategory,
    ActivityClassifier,
    ClassificationResult,
)
from src.core.activity_watcher.activity_daily_repository import ActivityDailyRepository
from src.core.activity_watcher.window_inspector import ActiveWindowInfo, WindowInspector
from src.core.focus_engine import FocusState

logger = logging.getLogger("ted")

DEFAULT_TICK_INTERVAL_MS = 3000          # Kiểm tra mỗi 3 giây
DEFAULT_GRACE_PERIOD_SECS = 6             # Chờ 6 giây (2 nhịp) trước khi nhắc nhở để tránh false alarm khi vô tình alt-tab
DEFAULT_SELF_CORRECT_WINDOW_SECS = 60     # Tắt xao nhãng trong 60 giây được tính là tự giác
DEFAULT_BREACH_THRESHOLD_SECS = 300       # Xem liên tục 5 phút = Vi phạm tập trung


class ActivityMonitor(QObject):
    """
    Giám sát cửa sổ người dùng trong giờ học, tự động phát hiện TikTok, YouTube Shorts,
    game hay web độc hại, phát tín hiệu nhắc nhở ân cần và ghi nhận vào sổ theo dõi.
    """

    distraction_detected = Signal(str, str, int)    # (app_name, window_title, duration_seconds)
    distraction_cleared = Signal(str)               # (app_name)
    self_corrected = Signal(str)                    # (app_name) - Con tự giác tắt sau khi bị nhắc
    distraction_breach = Signal(str, int)           # (app_name, duration_seconds) - Xem lì lợm > 5 phút
    unsafe_detected = Signal(str, str)              # (app_name, window_title) - Web cờ bạc/người lớn
    activity_ticked = Signal(str, str)              # (category, app_name)

    def __init__(
        self,
        focus_engine,
        repository: ActivityDailyRepository,
        inspector: Optional[WindowInspector] = None,
        classifier: Optional[ActivityClassifier] = None,
        tick_interval_ms: int = DEFAULT_TICK_INTERVAL_MS,
        grace_period_secs: int = DEFAULT_GRACE_PERIOD_SECS,
        self_correct_window_secs: int = DEFAULT_SELF_CORRECT_WINDOW_SECS,
        breach_threshold_secs: int = DEFAULT_BREACH_THRESHOLD_SECS,
        today_fn: Callable[[], str] = lambda: date.today().isoformat(),
        learner_fn: Callable[[], str] = lambda: "user",
        parent=None,
    ):
        super().__init__(parent)
        self.focus_engine = focus_engine
        self.repo = repository
        self.inspector = inspector or WindowInspector()
        self.classifier = classifier or ActivityClassifier()

        self.tick_interval_ms = tick_interval_ms
        self.grace_period_secs = grace_period_secs
        self.self_correct_window_secs = self_correct_window_secs
        self.breach_threshold_secs = breach_threshold_secs

        self.today_fn = today_fn
        self.learner_fn = learner_fn

        self.enabled = True
        self.consecutive_distraction_seconds = 0
        self.current_distraction_app: Optional[str] = None
        self.nudge_triggered = False
        self.nudge_timestamp: Optional[float] = None
        self.breach_triggered = False

        self._timer = QTimer(self)
        self._timer.setInterval(self.tick_interval_ms)
        self._timer.timeout.connect(self.tick)

    def start(self) -> None:
        """Bắt đầu vòng lặp giám sát."""
        if not self._timer.isActive():
            self._timer.start()

    def stop(self) -> None:
        """Dừng vòng lặp giám sát."""
        if self._timer.isActive():
            self._timer.stop()

    def tick(self) -> None:
        """Một nhịp kiểm tra cửa sổ active."""
        if not self.enabled:
            return

        window = self.inspector.get_active_window()
        if window is None:
            # Không lấy được cửa sổ hoặc màn hình lock/screensaver
            return

        result = self.classifier.classify(window.title, window.process_name)
        today = self.today_fn()
        learner = self.learner_fn()
        tick_secs = max(1, round(self.tick_interval_ms / 1000))

        # Lưu dồn thời lượng sử dụng vào SQLite
        try:
            self.repo.add_tick(
                day_str=today,
                category=result.category,
                app_name=result.app_name,
                seconds=tick_secs,
                learner=learner,
            )
        except Exception as exc:
            logger.debug("Lỗi khi ghi activity tick vào DB: %s", exc)

        self.activity_ticked.emit(result.category.value, result.app_name)

        # Kiểm tra trạng thái học tập
        is_in_focus = bool(
            self.focus_engine
            and hasattr(self.focus_engine, "state")
            and self.focus_engine.state in (FocusState.DEEP_WORK_RUNNING, FocusState.MEETING_RUNNING)
        )

        # 1. Phát hiện nội dung độc hại (Bất kể đang trong hay ngoài Pomodoro)
        if result.category == ActivityCategory.UNSAFE:
            self.unsafe_detected.emit(result.app_name, window.title)
            return

        # 2. Xử lý xao nhãng trong phiên học (Deep Work / Meeting)
        if is_in_focus:
            if result.category == ActivityCategory.DISTRACTION:
                self.consecutive_distraction_seconds += tick_secs

                # Nhắc nhở lần đầu khi vượt qua thời gian ân hạn (Grace Period)
                if self.consecutive_distraction_seconds >= self.grace_period_secs and not self.nudge_triggered:
                    self.nudge_triggered = True
                    self.nudge_timestamp = time.time()
                    self.current_distraction_app = result.app_name
                    self.distraction_detected.emit(
                        result.app_name,
                        window.title,
                        self.consecutive_distraction_seconds,
                    )

                # Cảnh báo vi phạm nghiêm trọng (Breach) nếu xem quá 5 phút liên tục
                if self.consecutive_distraction_seconds >= self.breach_threshold_secs and not self.breach_triggered:
                    self.breach_triggered = True
                    try:
                        self.repo.record_breach(today, learner=learner)
                    except Exception:
                        pass
                    self.distraction_breach.emit(result.app_name, self.consecutive_distraction_seconds)

            elif result.category in (ActivityCategory.STUDY, ActivityCategory.NEUTRAL):
                # Con đã thoát khỏi ứng dụng xao nhãng
                if self.nudge_triggered:
                    app_name = self.current_distraction_app or "nội dung giải trí"
                    # Nếu quay lại trong vòng 60 giây kể từ khi Ted nhắc -> Tự giác khắc phục
                    now = time.time()
                    if self.nudge_timestamp and (now - self.nudge_timestamp) <= self.self_correct_window_secs:
                        try:
                            self.repo.record_self_correction(today, learner=learner)
                        except Exception:
                            pass
                        self.self_corrected.emit(app_name)

                    self.distraction_cleared.emit(app_name)

                    # Reset trạng thái theo dõi phiên xao nhãng
                    self.consecutive_distraction_seconds = 0
                    self.nudge_triggered = False
                    self.nudge_timestamp = None
                    self.breach_triggered = False
                    self.current_distraction_app = None
        else:
            # Ngoài giờ học / phiên nghỉ: Reset đếm xao nhãng liên tục
            if self.consecutive_distraction_seconds > 0:
                self.consecutive_distraction_seconds = 0
                self.nudge_triggered = False
                self.nudge_timestamp = None
                self.breach_triggered = False
                self.current_distraction_app = None
