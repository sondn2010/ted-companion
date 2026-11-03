"""Logic Họp / Học nhóm / Học với thầy cô của FocusEngine (tách file để focus_engine.py gọn).

Họp là MỘT TRẠNG THÁI RIÊNG (MEETING_RUNNING) thay cho phiên Deep Work:
- đồng hồ đếm LÊN (elapsed), không có áp lực Pomodoro, không "hoàn thành" kiểu rating=5 → không vào XP focus;
- mọi cổng `state == DEEP_WORK_RUNNING` (mindful ping, nhắc Gỡ Rối, cheer...) tự động không kích hoạt;
- khi kết thúc phát `meeting_completed` để nhắc sức khỏe nhỏ chạy như sau Deep Work.
Signal khai báo ở FocusEngine (mixin không phải QObject).
"""

import logging
from typing import Optional

from src.core.i18n import tr
from src.core.meeting_mode.meeting_session_table_model_and_repository import (
    KIND_TEAM_MEETING, MIN_SECONDS_TO_COUNT, MeetingSessionRepository, normalize_kind, normalize_topic)

logger = logging.getLogger("ted")

MEETING_STATE = "MEETING_RUNNING"


class FocusEngineMeetingMixin:
    meeting_kind: str = KIND_TEAM_MEETING
    meeting_topic: str = ""
    current_meeting_id: Optional[str] = None
    _meeting_repo: Optional[MeetingSessionRepository] = None

    @property
    def meeting_repo(self) -> MeetingSessionRepository:
        """Tạo lười (cần db.engine); test có thể gán repo riêng."""
        if self._meeting_repo is None:
            from src.core.models import db
            self._meeting_repo = MeetingSessionRepository(db.engine)
        return self._meeting_repo

    @meeting_repo.setter
    def meeting_repo(self, repo: MeetingSessionRepository) -> None:
        self._meeting_repo = repo

    @property
    def in_meeting(self) -> bool:
        return self.state == MEETING_STATE

    def request_meeting_toggle(self) -> None:
        """Cửa chung cho menu/tray/dashboard/hotkey: UI coordinator nghe tín hiệu này (đang họp → dừng, chưa → hỏi chủ đề)."""
        self.meeting_toggle_requested.emit()

    def start_meeting(self, topic: str = "", kind: str = KIND_TEAM_MEETING) -> None:
        """Bắt đầu họp ngay (chủ đề tuỳ chọn). Đang Deep Work/nghỉ → dừng phiên đó trước (họp thay thế Deep Work)."""
        if self.in_meeting:
            return
        if self.state != "IDLE":
            self.stop_session(completed=False)
        self.meeting_kind, self.meeting_topic = normalize_kind(kind), normalize_topic(topic)
        try:
            self.current_meeting_id = self.meeting_repo.start(self.meeting_kind, self.meeting_topic)
        except Exception:  # noqa: BLE001 - lỗi DB không được chặn buổi họp (chỉ mất bản ghi)
            logger.exception("Không lưu được phiên họp")
            self.current_meeting_id = None
        self.active_task_id = None
        self.active_task_title = self.meeting_topic or tr(f"meeting_kind_{self.meeting_kind}")
        self.elapsed_seconds, self.remaining_seconds, self.total_seconds = 0, 0, 0
        self.state, self.current_mood = MEETING_STATE, "FOCUS"
        self.audio.play_chime()
        self.tick_timer.start()
        self.state_changed.emit(self.state, self.current_mood)
        self.timer_tick.emit(0, 0, self.active_task_title)
        self.meeting_started.emit(self.meeting_kind, self.meeting_topic)

    def stop_meeting(self) -> None:
        """Kết thúc họp: lưu phút (≥30s mới tính, ngắn hơn xoá), về IDLE, phát meeting_completed khi có phút."""
        if not self.in_meeting:
            return
        self.tick_timer.stop()
        mins = max(1, round(self.elapsed_seconds / 60)) if self.elapsed_seconds >= MIN_SECONDS_TO_COUNT else 0
        kind, meeting_id = self.meeting_kind, self.current_meeting_id
        try:
            if meeting_id:
                (self.meeting_repo.finish(meeting_id, mins) if mins > 0 else self.meeting_repo.discard(meeting_id))
        except Exception:  # noqa: BLE001
            logger.exception("Không đóng được phiên họp")
        self.current_meeting_id = None
        self.state, self.current_mood = "IDLE", "CHEER" if mins > 0 else "IDLE"
        self.remaining_seconds = self.total_seconds = self._default_pomodoro_seconds()
        self.elapsed_seconds = 0
        self.active_task_title = "Tập trung sâu cùng Ted"
        self.audio.play_chime()
        self.state_changed.emit(self.state, self.current_mood)
        self.timer_tick.emit(self.remaining_seconds, self.total_seconds, self.active_task_title)
        if mins > 0:
            self.meeting_completed.emit(kind, mins)
