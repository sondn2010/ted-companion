import json
from typing import List, Optional
from PySide6.QtCore import QObject, QTimer, Signal
from src.config import CHARACTER_SKINS, DEFAULT_CHARACTER_SKIN, settings
from src.core.i18n import tr
from src.core.meeting_mode.focus_engine_meeting_mixin import MEETING_STATE, FocusEngineMeetingMixin
from src.core.models import db
from src.core.skin_unlock_gate import is_skin_unlocked


class FocusState:
    IDLE = "IDLE"
    DEEP_WORK_RUNNING = "DEEP_WORK_RUNNING"
    PAUSED = "PAUSED"
    BREAK_RUNNING = "BREAK_RUNNING"
    MEETING_RUNNING = MEETING_STATE   # Họp / Học nhóm / Học với thầy cô (thay Deep Work, đếm lên)


class FocusEngine(FocusEngineMeetingMixin, QObject):
    """
    State Machine quản lý phiên tập trung Deep Work, Pomodoro, Mindful Pings,
    chuyển đổi nhân vật (Mèo / Cú / Gấu trúc / Shiba / Thỏ / Cánh cụt) và đồng bộ lệnh từ Ted MCP Server.
    """

    state_changed = Signal(str, str)          # (focus_state, ted_mood_svg_key)
    character_changed = Signal(str)           # (character_skin: 'cat' | 'owl' | 'panda' | 'shiba' | 'bunny' | 'penguin')
    timer_tick = Signal(int, int, str)        # (remaining_seconds, total_seconds, active_task_title)
    mindful_ping_triggered = Signal(str)      # (active_task_title)
    session_completed = Signal(str, int, int) # (active_task_title, actual_mins, distraction_count)
    external_mcp_message = Signal(str, str)   # (mood, message)
    tasks_updated = Signal()
    session_started = Signal(str, str)        # (task_id hoặc "", task_title) — chỉ phiên MỚI, không phát khi resume
    meeting_started = Signal(str, str)        # (meeting_kind, topic) — bắt đầu Họp/Học nhóm
    meeting_completed = Signal(str, int)      # (meeting_kind, actual_mins) — chỉ khi có phút (≥30s)
    meeting_toggle_requested = Signal()       # menu/tray/dashboard/hotkey → coordinator UI (hỏi chủ đề hoặc dừng)
    task_added = Signal(str, str)             # (task_id, title) — task/ý tưởng mới chưa có ô → engine work tự phân loại Eisenhower

    def __init__(self, audio_manager, parent=None):
        super().__init__(parent)
        self.audio = audio_manager
        self.state = FocusState.IDLE
        self.current_mood = "IDLE"

        self.active_task_id: Optional[str] = None
        self.active_task_title: str = "Tập trung sâu cùng Ted"
        self.current_session_id: Optional[str] = None

        self.total_seconds: int = settings.default_pomodoro_mins * 60
        self.remaining_seconds: int = self.total_seconds
        self.elapsed_seconds: int = 0
        self.distraction_count: int = 0
        self.session_distractions: List[str] = []
        self.last_session_distractions: List[str] = []

        self.tick_timer = QTimer(self)
        self.tick_timer.setInterval(1000)
        self.tick_timer.timeout.connect(self._on_second_tick)

        self.ipc_timer = QTimer(self)
        self.ipc_timer.setInterval(1500)
        self.ipc_timer.timeout.connect(self._poll_mcp_commands)
        self.ipc_timer.start()

    def set_mood(self, mood: str):
        valid = {"IDLE", "FOCUS", "GENTLE_NUDGE", "CHEER", "REST"}
        self.current_mood = mood if mood in valid else "IDLE"
        self.state_changed.emit(self.state, self.current_mood)

    def set_character(self, skin: str):
        skin_key = skin.lower().strip()
        if skin_key in CHARACTER_SKINS:
            if not is_skin_unlocked(skin_key):   # nhân vật bundle chưa mở khoá (cũng chặn lệnh MCP của Hermes)
                self.external_mcp_message.emit("GENTLE_NUDGE", tr("skin_locked_message"))
                return
            settings.character_skin = skin_key
            settings.save()
            self.character_changed.emit(skin_key)
            self.state_changed.emit(self.state, self.current_mood)

    def start_focus_session(
        self,
        task_title: str = "Phiên Deep Work",
        duration_mins: Optional[int] = None,
        task_id: Optional[str] = None,
    ):
        if self.state == FocusState.MEETING_RUNNING:   # Deep Work thay thế họp
            self.stop_meeting()
        mins = duration_mins or settings.default_pomodoro_mins
        self.active_task_id = task_id
        self.active_task_title = task_title.strip() or "Phiên Deep Work"
        self.total_seconds = mins * 60
        self.remaining_seconds = self.total_seconds
        self.elapsed_seconds = 0
        self.distraction_count = 0
        self.session_distractions = []

        fs = db.create_focus_session(
            intent=self.active_task_title,
            planned_minutes=mins,
            task_id=task_id,
        )
        self.current_session_id = fs.id
        self.state = FocusState.DEEP_WORK_RUNNING
        self.current_mood = "FOCUS"
        self.audio.play_chime()
        self.tick_timer.start()
        self.state_changed.emit(self.state, self.current_mood)
        self.timer_tick.emit(self.remaining_seconds, self.total_seconds, self.active_task_title)
        self.session_started.emit(task_id or "", self.active_task_title)

    def _default_pomodoro_seconds(self) -> int:
        return settings.default_pomodoro_mins * 60

    def pause_or_resume(self):
        if self.state == FocusState.MEETING_RUNNING:
            return  # họp không có tạm dừng; dừng bằng stop_session / nút ⏹
        if self.state == FocusState.DEEP_WORK_RUNNING:
            self.tick_timer.stop()
            self.state = FocusState.PAUSED
            self.current_mood = "IDLE"
            self.state_changed.emit(self.state, self.current_mood)
        elif self.state == FocusState.PAUSED:
            self.tick_timer.start()
            self.state = FocusState.DEEP_WORK_RUNNING
            self.current_mood = "FOCUS"
            self.state_changed.emit(self.state, self.current_mood)
        elif self.state == FocusState.IDLE:
            self.start_focus_session(self.active_task_title, settings.default_pomodoro_mins, self.active_task_id)

    def stop_session(self, completed: bool = False):
        if self.state == FocusState.MEETING_RUNNING:   # mọi lối "dừng" (hotkey, menu, MCP) đều dừng được buổi họp
            self.stop_meeting()
            return
        self.tick_timer.stop()
        actual_mins = max(1, round(self.elapsed_seconds / 60)) if self.elapsed_seconds >= 30 else 0
        if self.current_session_id and (completed or actual_mins > 0):
            db.finish_focus_session(
                session_id=self.current_session_id,
                actual_minutes=actual_mins,
                distraction_count=self.distraction_count,
                focus_rating=5 if completed else 4,
            )
            if completed and self.active_task_id:
                db.increment_task_pomodoro(self.active_task_id)

        finished_title = self.active_task_title
        distractions = self.distraction_count
        self.last_session_distractions = list(self.session_distractions)
        self.current_session_id = None
        self.state = FocusState.IDLE
        self.current_mood = "CHEER" if completed else "IDLE"
        self.remaining_seconds = settings.default_pomodoro_mins * 60
        self.total_seconds = self.remaining_seconds

        self.audio.play_chime()
        self.state_changed.emit(self.state, self.current_mood)
        self.timer_tick.emit(self.remaining_seconds, self.total_seconds, self.active_task_title)
        if completed:
            self.session_completed.emit(finished_title, actual_mins, distractions)
            self.tasks_updated.emit()

    def start_break(self, break_mins: Optional[int] = None):
        if self.state == FocusState.MEETING_RUNNING:
            self.stop_meeting()
        mins = break_mins or settings.default_break_mins
        self.active_task_title = "Nghỉ ngơi thư giãn mắt & uống nước"
        self.total_seconds = mins * 60
        self.remaining_seconds = self.total_seconds
        self.elapsed_seconds = 0
        self.state = FocusState.BREAK_RUNNING
        self.current_mood = "REST"
        self.tick_timer.start()
        self.state_changed.emit(self.state, self.current_mood)
        self.timer_tick.emit(self.remaining_seconds, self.total_seconds, self.active_task_title)

    def add_task(self, title: str, category: str = "deep_work", estimated_pomodoros: int = 1):
        """Cửa chung để thêm việc (Dashboard, Bãi đỗ, Hermes/MCP): lưu → refresh UI → phát task_added để phân loại."""
        task = db.add_task(title=title.strip(), category=category, estimated_pomodoros=estimated_pomodoros)
        self.tasks_updated.emit()
        self.task_added.emit(task.id, task.title)
        return task

    def note_distraction(self, app_name: str, window_title: str = "") -> None:
        """Ghi nhận một lần xao nhãng trong phiên hiện tại (không tạo ticket công việc)."""
        self.distraction_count += 1
        name = (app_name or "Khác").strip()
        if name:
            self.session_distractions.append(name)

    def record_distraction(self, parked_idea_text: Optional[str] = None, app_name: Optional[str] = None):
        """Ghi nhận xao nhãng. Nếu có parked_idea_text (từ nút 🅿️ Bãi đỗ) mới tạo task; xao nhãng tự động không tạo task."""
        self.distraction_count += 1
        if app_name and app_name.strip():
            self.session_distractions.append(app_name.strip())
        if parked_idea_text and parked_idea_text.strip():
            self.session_distractions.append(f"🅿️ {parked_idea_text.strip()}")
            return self.add_task(parked_idea_text, category="parked_idea")
        elif not app_name:
            self.session_distractions.append("Xao nhãng khác")
        return None

    def get_session_distractions_summary(self, multiline: bool = True) -> str:
        """Tổng hợp danh sách các ứng dụng/trang gây xao nhãng trong phiên vừa qua."""
        items = self.session_distractions if self.session_distractions else self.last_session_distractions
        if not items:
            return ""
        from collections import Counter
        counts = Counter(items)
        parts = []
        for name, count in counts.items():
            if count > 1:
                parts.append(f"• {name} ({count} lần)" if multiline else f"{name} ({count} lần)")
            else:
                parts.append(f"• {name}" if multiline else f"{name}")
        return "\n".join(parts) if multiline else ", ".join(parts)

    def get_context_snapshot(self) -> dict:
        return {
            "character": settings.character_skin,
            "status": self.state,
            "task": self.active_task_title,
            "remaining_mins": round(self.remaining_seconds / 60, 1),
            "distractions": self.distraction_count,
        }

    def _on_second_tick(self):
        if self.state == FocusState.MEETING_RUNNING:   # đếm lên, không kết thúc tự động, không mindful ping
            self.elapsed_seconds += 1
            self.timer_tick.emit(self.elapsed_seconds, 0, self.active_task_title)
            return
        if self.remaining_seconds > 0:
            self.remaining_seconds -= 1
            self.elapsed_seconds += 1
            self.timer_tick.emit(self.remaining_seconds, self.total_seconds, self.active_task_title)

            ping_interval_secs = settings.mindful_ping_mins * 60
            if (
                self.state == FocusState.DEEP_WORK_RUNNING
                and ping_interval_secs > 0
                and self.elapsed_seconds > 0
                and self.elapsed_seconds % ping_interval_secs == 0
                and self.remaining_seconds >= 60
            ):
                self.set_mood("GENTLE_NUDGE")   # không chime: đang Deep Work, chỉ nhắc im lặng ở bubble
                self.mindful_ping_triggered.emit(self.active_task_title)
        else:
            if self.state == FocusState.DEEP_WORK_RUNNING:
                self.stop_session(completed=True)
            else:
                self.stop_session(completed=False)

    def _poll_mcp_commands(self):
        """Đọc hàng đợi lệnh từ ted_mcp_server.py để Hermes Agent điều khiển giao diện theo thời gian thực."""
        cmd_file = settings.ipc_command_file
        if not cmd_file.exists():
            return
        try:
            raw = cmd_file.read_text(encoding="utf-8")
            cmd_file.unlink(missing_ok=True)
            commands = json.loads(raw)
            if not isinstance(commands, list):
                commands = [commands]
            for cmd in commands:
                action = cmd.get("type")
                if action == "control_pomodoro":
                    sub = cmd.get("action", "start")
                    title = cmd.get("task_title") or self.active_task_title
                    mins = int(cmd.get("duration_minutes", settings.default_pomodoro_mins))
                    if sub == "start":
                        self.start_focus_session(title, mins)
                    elif sub in ("pause", "resume"):
                        self.pause_or_resume()
                    elif sub == "stop":
                        self.stop_session(completed=False)
                elif action == "nudge_user":
                    mood = cmd.get("mood", "GENTLE_NUDGE")
                    msg = cmd.get("message", "Ted nhắc nhẹ: Bạn vẫn đang tập trung chứ?")
                    self.set_mood(mood)
                    if self.state != FocusState.DEEP_WORK_RUNNING:   # Deep Work: nhắc im lặng
                        self.audio.play_chime()
                    self.external_mcp_message.emit(mood, msg)
                elif action == "change_character":
                    skin = cmd.get("skin", DEFAULT_CHARACTER_SKIN)
                    self.set_character(skin)
                elif action == "refresh_tasks":
                    self.tasks_updated.emit()
                    if cmd.get("task_id"):  # task Hermes vừa tạo qua MCP → cũng tự phân loại như nhập tay
                        self.task_added.emit(cmd["task_id"], cmd.get("title", ""))
        except Exception:
            pass
