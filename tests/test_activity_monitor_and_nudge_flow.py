"""Unit tests cho ActivityMonitor state machine & luồng nhắc nhở xao nhãng."""

import time
from unittest.mock import MagicMock
import pytest
from sqlmodel import SQLModel, create_engine

from src.core.activity_watcher.activity_classifier import (
    ActivityCategory,
    ActivityClassifier,
)
from src.core.activity_watcher.activity_daily_repository import ActivityDailyRepository
from src.core.activity_watcher.activity_monitor import ActivityMonitor
from src.core.activity_watcher.window_inspector import ActiveWindowInfo, WindowInspector
from src.core.focus_engine import FocusState


@pytest.fixture
def test_db_engine():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    return engine


class DummyFocusEngine:
    def __init__(self, initial_state=FocusState.DEEP_WORK_RUNNING):
        self.state = initial_state
        self.distraction_count = 0

    def record_distraction(self, parked_idea_text=None):
        self.distraction_count += 1


def test_monitor_records_ticks_in_repository(test_db_engine):
    repo = ActivityDailyRepository(test_db_engine)
    focus = DummyFocusEngine()

    current_window = ActiveWindowInfo("Đại số 8 - Google Docs", "chrome.exe")
    inspector = WindowInspector(backend_fn=lambda: current_window)
    classifier = ActivityClassifier()

    monitor = ActivityMonitor(
        focus_engine=focus,
        repository=repo,
        inspector=inspector,
        classifier=classifier,
        tick_interval_ms=1000,
        today_fn=lambda: "2026-10-22",
        learner_fn=lambda: "uyen",
    )

    # 3 ticks of study
    monitor.tick()
    monitor.tick()
    monitor.tick()

    rec = repo.get_or_create("2026-10-22", "uyen")
    assert rec.study_seconds == 3
    assert rec.distraction_seconds == 0


def test_monitor_triggers_nudge_after_grace_period(test_db_engine):
    repo = ActivityDailyRepository(test_db_engine)
    focus = DummyFocusEngine(FocusState.DEEP_WORK_RUNNING)

    current_window = ActiveWindowInfo("TikTok - Watch trending videos", "chrome.exe")
    inspector = WindowInspector(backend_fn=lambda: current_window)
    classifier = ActivityClassifier()

    monitor = ActivityMonitor(
        focus_engine=focus,
        repository=repo,
        inspector=inspector,
        classifier=classifier,
        tick_interval_ms=2000,
        grace_period_secs=4,   # 4 giây = 2 ticks
        today_fn=lambda: "2026-10-22",
        learner_fn=lambda: "uyen",
    )

    nudge_events = []
    monitor.distraction_detected.connect(lambda app, title, dur: nudge_events.append((app, dur)))

    # Tick 1: 2s (chưa đủ grace period 4s)
    monitor.tick()
    assert len(nudge_events) == 0

    # Tick 2: 4s (đạt grace period -> phát tín hiệu nudge)
    monitor.tick()
    assert len(nudge_events) == 1
    assert nudge_events[0][0] == "TikTok"
    assert nudge_events[0][1] == 4

    # Tick 3: 6s (không phát lại nudge liên tục để tránh spam)
    monitor.tick()
    assert len(nudge_events) == 1


def test_monitor_self_correction_flow(test_db_engine):
    repo = ActivityDailyRepository(test_db_engine)
    focus = DummyFocusEngine(FocusState.DEEP_WORK_RUNNING)

    window_box = [ActiveWindowInfo("TikTok", "chrome.exe")]
    inspector = WindowInspector(backend_fn=lambda: window_box[0])
    classifier = ActivityClassifier()

    monitor = ActivityMonitor(
        focus_engine=focus,
        repository=repo,
        inspector=inspector,
        classifier=classifier,
        tick_interval_ms=2000,
        grace_period_secs=2,
        self_correct_window_secs=60,
        today_fn=lambda: "2026-10-22",
        learner_fn=lambda: "uyen",
    )

    self_corrected_events = []
    monitor.self_corrected.connect(lambda app: self_corrected_events.append(app))

    # Bật TikTok và bị nhắc
    monitor.tick()
    assert monitor.nudge_triggered is True

    # Con tắt TikTok, chuyển sang Microsoft Word (trong vòng 60s)
    window_box[0] = ActiveWindowInfo("BaiTapToan.docx - Word", "winword.exe")
    monitor.tick()

    assert len(self_corrected_events) == 1
    assert self_corrected_events[0] == "TikTok"
    assert monitor.nudge_triggered is False

    # Kiểm tra repository đã ghi nhận tự giác
    rec = repo.get_or_create("2026-10-22", "uyen")
    assert rec.self_corrected_count == 1


def test_monitor_triggers_unsafe_immediately(test_db_engine):
    repo = ActivityDailyRepository(test_db_engine)
    focus = DummyFocusEngine(FocusState.IDLE)  # Kể cả không trong Deep Work

    unsafe_win = ActiveWindowInfo("Kubet Casino Trực Tuyến", "chrome.exe")
    inspector = WindowInspector(backend_fn=lambda: unsafe_win)
    classifier = ActivityClassifier()

    monitor = ActivityMonitor(
        focus_engine=focus,
        repository=repo,
        inspector=inspector,
        classifier=classifier,
        today_fn=lambda: "2026-10-22",
        learner_fn=lambda: "uyen",
    )

    unsafe_events = []
    monitor.unsafe_detected.connect(lambda app, title: unsafe_events.append(app))

    monitor.tick()
    assert len(unsafe_events) == 1
    assert "Cờ bạc" in unsafe_events[0]


def test_focus_engine_distraction_does_not_create_task():
    from unittest.mock import MagicMock
    from src.core.focus_engine import FocusEngine
    from src.core.models import db

    tasks_before = len(db.list_tasks())
    fe = FocusEngine(audio_manager=MagicMock())
    fe.start_focus_session("Học bài Toán", duration_mins=25)

    # 1. Ghi nhận xao nhãng Zalo bằng note_distraction
    fe.note_distraction(app_name="Zalo")
    assert fe.distraction_count == 1
    assert "Zalo" in fe.session_distractions

    # Không được tạo ticket/task trong database
    assert len(db.list_tasks()) == tasks_before

    # 2. Ghi nhận xao nhãng TikTok bằng record_distraction(app_name=...)
    fe.record_distraction(app_name="TikTok")
    assert fe.distraction_count == 2
    assert "TikTok" in fe.session_distractions

    # Vẫn không tạo ticket/task trong database
    assert len(db.list_tasks()) == tasks_before

    # 3. Thêm 1 lần xao nhãng Zalo nữa
    fe.note_distraction(app_name="Zalo")
    assert fe.distraction_count == 3

    # Kiểm tra summary danh sách xao nhãng
    summary_multi = fe.get_session_distractions_summary(multiline=True)
    assert "Zalo (2 lần)" in summary_multi
    assert "TikTok" in summary_multi

    summary_inline = fe.get_session_distractions_summary(multiline=False)
    assert "Zalo (2 lần)" in summary_inline
    assert "TikTok" in summary_inline

    # 4. Khi kết thúc phiên (stop_session completed=True)
    completed_events = []
    fe.session_completed.connect(lambda title, mins, dist: completed_events.append((title, mins, dist)))
    fe.stop_session(completed=True)

    assert len(completed_events) == 1
    assert completed_events[0][2] == 3  # 3 lần xao nhãng
    assert fe.get_session_distractions_summary() != ""

    # 5. Phân biệt với 🅿️ Bãi đỗ ý tưởng: User chủ động cất ý tưởng thì MỚI tạo task
    fe.record_distraction(parked_idea_text="Ý tưởng bài tập mới")
    assert len(db.list_tasks()) == tasks_before + 1
    tasks = db.list_tasks()
    parked = [t for t in tasks if t.title == "Ý tưởng bài tập mới"]
    assert len(parked) == 1
    assert parked[0].category == "parked_idea"
