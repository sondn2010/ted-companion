"""Dịch vụ nhắc nhở đi ngủ sớm và cảnh báo làm việc muộn / thức khuya.

Luồng hoạt động:
1. Sắp đến giờ đi ngủ (T - warning_mins, mặc định 15p trước giờ ngủ):
   -> Nhắc chuẩn bị đi ngủ, tắt máy tính, thư giãn mắt.
2. Đúng giờ đi ngủ (bedtime, mặc định 23:00):
   -> Nhắc đến giờ ngủ, chúc ngủ ngon và khuyên nghỉ ngơi.
3. Làm việc muộn / Thức khuya (sau bedtime đến trước 05:00 sáng):
   -> Nếu vẫn đang chạy Deep Work hoặc máy vẫn hoạt động:
      Cứ mỗi late_work_nudge_interval_mins (mặc định 30p), Ted nhắc nhở làm việc muộn,
      khuyên bảo vệ sức khỏe, chuyển mood REST hoặc GENTLE_NUDGE.
4. Tương tác trên Bong bóng (Speech Bubble):
   - "Đi ngủ ngay 🛌" -> ghi nhận, chuyển mood REST (chibi cuộn tròn ngủ say), phát chuông/nói chúc ngủ ngon.
   - "Thêm 15 phút ⏳" -> hoãn nhắc nhở (snooze) trong 15 phút.
"""

from datetime import date, datetime, time, timedelta, timezone
import logging
from typing import Callable, Optional

from PySide6.QtCore import QObject, QTimer

from src.config import settings
from src.core.focus_engine import FocusEngine, FocusState
from src.core.i18n import tr
from src.core.tts_service import tts_service

logger = logging.getLogger("ted")

DEFAULT_BEDTIME = (23, 0)
TICK_INTERVAL_MS = 30_000
BUBBLE_TIMEOUT_MS = 25_000


def parse_bedtime(target_str: Optional[str]) -> tuple[int, int]:
    """Phân tích chuỗi giờ ngủ (vd: '23:00', '22:30', '00:30') thành (hour, minute)."""
    if not target_str or not isinstance(target_str, str):
        return DEFAULT_BEDTIME
    try:
        parts = target_str.strip().split(":")
        h, m = int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
        if 0 <= h <= 23 and 0 <= m <= 59:
            return h, m
    except (ValueError, IndexError):
        pass
    return DEFAULT_BEDTIME


def night_cycle_date(dt: datetime) -> date:
    """Trả về ngày của chu kỳ đêm: nếu giờ < 5h sáng thì đêm đó thuộc về ngày hôm trước."""
    if dt.hour < 5:
        return (dt - timedelta(days=1)).date()
    return dt.date()


class SleepReminderService(QObject):
    def __init__(
        self,
        focus_engine: FocusEngine,
        bubble,
        audio_manager=None,
        kv=None,
        now_fn: Callable[[], datetime] = lambda: datetime.now().astimezone(),
        is_untangle_dialog_visible: Callable[[], bool] = lambda: False,
        parent=None,
    ):
        super().__init__(parent)
        self._focus = focus_engine
        self._bubble = bubble
        self._audio = audio_manager
        self._kv = kv
        self._now_fn = now_fn
        self._untangle_visible = is_untangle_dialog_visible

        self._timer = QTimer(self)
        self._timer.setInterval(TICK_INTERVAL_MS)
        self._timer.timeout.connect(lambda: self.tick())

        # Bộ nhớ đệm cục bộ (nếu không có KV store)
        self._warned_night: Optional[str] = None
        self._due_night: Optional[str] = None
        self._last_late_nudge: Optional[datetime] = None
        self._snooze_until: Optional[datetime] = None
        self._user_sleeping_night: Optional[str] = None

    def start(self) -> None:
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def _get_val(self, key: str, default: Optional[str] = None) -> Optional[str]:
        if self._kv is not None:
            return self._kv.get(key) or default
        return default

    def _set_val(self, key: str, val: str) -> None:
        if self._kv is not None:
            self._kv.set(key, val)

    def _compute_bedtime_dt(self, night: date, tzinfo) -> datetime:
        """Tính datetime chính xác của giờ đi ngủ trong chu kỳ đêm `night`."""
        target_str = getattr(settings, "bedtime_target", "23:00")
        b_hour, b_min = parse_bedtime(target_str)
        if b_hour < 5:
            # Giờ ngủ sau nửa đêm (vd: 00:30 hoặc 01:00) -> sang ngày hôm sau của chu kỳ
            day = night + timedelta(days=1)
        else:
            day = night
        return datetime(day.year, day.month, day.day, b_hour, b_min, tzinfo=tzinfo)

    def _can_show_bubble(self) -> bool:
        if self._bubble is None:
            return False
        if hasattr(self._bubble, "has_pending_actions") and self._bubble.has_pending_actions():
            return False
        if self._untangle_visible():
            return False
        return True

    def tick(self, now: Optional[datetime] = None) -> Optional[str]:
        """Kiểm tra và kích hoạt lời nhắc phù hợp. Trả về loại nhắc ('approaching', 'due', 'late_work') hoặc None."""
        if not getattr(settings, "sleep_reminder_enabled", True):
            return None

        current = now or self._now_fn()
        current_local = current
        night = night_cycle_date(current_local)
        night_iso = night.isoformat()

        # Kiểm tra Snooze
        snooze_str = self._get_val("sleep_reminder.snooze_until")
        snooze_dt = self._snooze_until
        if snooze_str:
            try:
                snooze_dt = datetime.fromisoformat(snooze_str)
                if current_local.tzinfo is not None and snooze_dt.tzinfo is None:
                    snooze_dt = snooze_dt.replace(tzinfo=current_local.tzinfo)
            except ValueError:
                pass
        if snooze_dt and current_local < snooze_dt:
            return None

        # Kiểm tra nếu user đã chọn "Đi ngủ ngay" cho đêm nay
        user_sleeping = self._get_val("sleep_reminder.user_sleeping_night", self._user_sleeping_night)
        if user_sleeping == night_iso:
            # Nếu user đã ngủ mà không bật Deep Work thì không làm phiền
            if self._focus is None or self._focus.state != FocusState.DEEP_WORK_RUNNING:
                return None

        bedtime_dt = self._compute_bedtime_dt(night, current_local.tzinfo)
        warning_mins = getattr(settings, "bedtime_warning_mins", 15)
        warning_dt = bedtime_dt - timedelta(minutes=warning_mins)

        warned_night = self._get_val("sleep_reminder.warned_night", self._warned_night)
        due_night = self._get_val("sleep_reminder.due_night", self._due_night)

        # 1. Giai đoạn: Sắp đến giờ ngủ (Bedtime Approaching)
        if warning_mins > 0 and warning_dt <= current_local < bedtime_dt:
            if warned_night != night_iso:
                if not self._can_show_bubble():
                    return None
                self._warned_night = night_iso
                self._set_val("sleep_reminder.warned_night", night_iso)
                self._announce_approaching_bedtime(bedtime_dt)
                return "approaching"

        # 2. Giai đoạn: Đúng giờ đi ngủ (Bedtime Due)
        if bedtime_dt <= current_local < bedtime_dt + timedelta(minutes=15):
            if due_night != night_iso:
                if not self._can_show_bubble():
                    return None
                self._due_night = night_iso
                self._set_val("sleep_reminder.due_night", night_iso)
                self._announce_bedtime_due(bedtime_dt)
                return "due"

        # 3. Giai đoạn: Làm việc muộn / Thức khuya (Late Night Working)
        # Bắt đầu từ sau bedtime + 15 phút kéo dài đến 05:00 sáng
        is_late_window = current_local >= (bedtime_dt + timedelta(minutes=15)) and (
            current_local.hour < 5 or current_local.hour >= 21
        )
        if is_late_window:
            interval_mins = max(10, getattr(settings, "late_work_nudge_interval_mins", 30))
            last_nudge_str = self._get_val("sleep_reminder.last_late_nudge")
            last_nudge_dt = self._last_late_nudge
            if last_nudge_str:
                try:
                    last_nudge_dt = datetime.fromisoformat(last_nudge_str)
                    if current_local.tzinfo is not None and last_nudge_dt.tzinfo is None:
                        last_nudge_dt = last_nudge_dt.replace(tzinfo=current_local.tzinfo)
                except ValueError:
                    pass

            if last_nudge_dt is None or (current_local - last_nudge_dt).total_seconds() >= interval_mins * 60:
                if not self._can_show_bubble():
                    return None
                self._last_late_nudge = current_local
                self._set_val("sleep_reminder.last_late_nudge", current_local.isoformat())
                self._announce_late_work(current_local)
                return "late_work"

        return None

    def _announce_approaching_bedtime(self, bedtime_dt: datetime) -> None:
        target_str = f"{bedtime_dt:%H:%M}"
        msg = tr("sleep_bedtime_approaching", bedtime=target_str)
        self._notify(msg, mood="REST")

    def _announce_bedtime_due(self, bedtime_dt: datetime) -> None:
        target_str = f"{bedtime_dt:%H:%M}"
        msg = tr("sleep_bedtime_due", bedtime=target_str)
        self._notify(msg, mood="REST")

    def _announce_late_work(self, now: datetime) -> None:
        time_str = f"{now:%H:%M}"
        if self._focus and self._focus.state == FocusState.DEEP_WORK_RUNNING:
            msg = tr("sleep_late_deep_work", time=time_str)
            mood = "GENTLE_NUDGE"
        elif now.hour < 5:
            msg = tr("sleep_late_midnight", time=time_str)
            mood = "REST"
        else:
            msg = tr("sleep_late_night", time=time_str)
            mood = "REST"
        self._notify(msg, mood=mood)

    def _notify(self, text: str, mood: str = "REST") -> None:
        if self._focus:
            self._focus.set_mood(mood)
        if self._audio:
            self._audio.play_chime()

        actions = [
            (tr("sleep_action_sleep"), self.record_user_sleep),
            (tr("sleep_action_snooze"), lambda: self.snooze(15)),
        ]
        if self._bubble:
            self._bubble.show_message(text, mood=mood, actions=actions, timeout_ms=BUBBLE_TIMEOUT_MS)

        if getattr(settings, "tts_enabled", False):
            try:
                first_line = text.split("\n", 1)[0]
                for emo in ("🌙", "🛌", "⚠️", "🦉", "🥱", "😴", "💤", "😵‍💫", "✨", "*"):
                    first_line = first_line.replace(emo, "")
                first_line = first_line.strip()
                tts_service.speak_now(first_line)
            except Exception:
                pass

    def record_user_sleep(self) -> None:
        """Xử lý khi người dùng chọn 'Đi ngủ ngay'."""
        now = self._now_fn()
        night = night_cycle_date(now)
        night_iso = night.isoformat()
        self._user_sleeping_night = night_iso
        self._set_val("sleep_reminder.user_sleeping_night", night_iso)

        if self._focus:
            if self._focus.state == FocusState.DEEP_WORK_RUNNING:
                self._focus.pause_or_resume()
            self._focus.set_mood("REST")

        if self._audio:
            self._audio.play_chime()

        goodnight_msg = tr("sleep_goodnight_msg")
        if self._bubble:
            self._bubble.show_message(goodnight_msg, mood="REST", timeout_ms=8000)

        if getattr(settings, "tts_enabled", False):
            try:
                tts_service.speak_now("Chúc bạn ngủ thật ngon!")
            except Exception:
                pass

    def snooze(self, minutes: int = 15) -> None:
        """Hoãn nhắc nhở thêm `minutes` phút."""
        now = self._now_fn()
        snooze_dt = now + timedelta(minutes=minutes)
        self._snooze_until = snooze_dt
        self._set_val("sleep_reminder.snooze_until", snooze_dt.isoformat())

        ack = tr("sleep_snooze_ack")
        if self._bubble:
            self._bubble.show_message(ack, mood="REST", timeout_ms=3000)


def install_sleep_reminder(ctx, companion) -> SleepReminderService:
    """Khởi tạo và cài đặt SleepReminderService vào companion."""
    service = SleepReminderService(
        focus_engine=ctx.focus_engine,
        bubble=ctx.bubble,
        audio_manager=getattr(ctx, "audio", None),
        kv=getattr(ctx, "kv", None),
        is_untangle_dialog_visible=lambda: bool(
            getattr(companion, "untangle_dialog", None) and companion.untangle_dialog.isVisible()
        ),
        parent=companion,
    )
    service.start()
    companion._sleep_reminder = service
    logger.info("SleepReminderService đã được cài đặt và khởi động thành công.")
    return service
