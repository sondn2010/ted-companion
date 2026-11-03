"""Kết nối ActivityMonitor với nhân vật Ted và bong bóng chat (Wiring)."""

import logging
from typing import Optional

from src.config import settings
from src.core.activity_watcher.activity_classifier import ActivityClassifier
from src.core.activity_watcher.activity_daily_repository import ActivityDailyRepository
from src.core.activity_watcher.activity_monitor import ActivityMonitor
from src.core.activity_watcher.activity_outbox_sender import ActivityOutboxSender
from src.core.activity_watcher.window_inspector import WindowInspector
from src.core.background_task_spawner import spawn_background_task
from src.core.models import db
from src.core.tts_service import tts_service

logger = logging.getLogger("ted")


def _get_learner_name(ctx) -> str:
    """Xác định tên học sinh đang học từ active module manifest."""
    try:
        if ctx.registry and hasattr(ctx.registry, "active"):
            mod = ctx.registry.active()
            if mod and hasattr(mod, "learner_id") and mod.learner_id:
                return str(mod.learner_id)
    except Exception:
        pass
    return "con"


def install_activity_monitor(ctx, companion) -> Optional[ActivityMonitor]:
    """Cài đặt và kích hoạt hệ thống giám sát hoạt động.
    
    Gắn vào `companion` để không bị thu hồi bộ nhớ (GC).
    """
    if not getattr(settings, "activity_monitor_enabled", True):
        logger.info("ActivityMonitor đang tắt trong cấu hình")
        return None

    try:
        repo = ActivityDailyRepository(db.engine)
        inspector = WindowInspector()
        classifier = ActivityClassifier()

        monitor = ActivityMonitor(
            focus_engine=ctx.focus_engine,
            repository=repo,
            inspector=inspector,
            classifier=classifier,
            learner_fn=lambda: _get_learner_name(ctx),
            parent=companion,
        )

        outbox = ActivityOutboxSender(
            repository=repo,
            client_pool=ctx.client_pool,
            registry=ctx.registry,
            learner_fn=lambda: _get_learner_name(ctx),
        )
        monitor.outbox = outbox

        # 1. Khi phát hiện xao nhãng (Zalo, TikTok, YouTube, Games...)
        CHAT_APPS = {"Zalo", "Messenger", "Telegram", "WhatsApp", "Discord", "Viber", "Skype", "WeChat", "LINE", "KakaoTalk"}

        def on_distraction(app_name: str, _title: str, _duration: int):
            # Ghi nhận xao nhãng vào phiên học hiện tại (KHÔNG tạo ticket công việc)
            if ctx.focus_engine:
                if hasattr(ctx.focus_engine, "note_distraction"):
                    ctx.focus_engine.note_distraction(app_name=app_name, window_title=_title)
                elif hasattr(ctx.focus_engine, "record_distraction"):
                    ctx.focus_engine.record_distraction(app_name=app_name)

            if ctx.focus_engine and hasattr(ctx.focus_engine, "set_mood"):
                ctx.focus_engine.set_mood("GENTLE_NUDGE")

            if app_name in CHAT_APPS:
                msg = (
                    f"🐾 {settings.user_display_name} ơi, mình đang trong phiên học bài mà! "
                    f"Tạm gác tin nhắn {app_name} lại rồi lát giải lao trò chuyện tiếp nhé!"
                )
            else:
                msg = (
                    f"🐾 {settings.user_display_name} ơi, mình đang trong phiên học bài mà! "
                    f"Tắt {app_name} đi rồi lát nghỉ giải lao Ted cùng xem nhé!"
                )
            if ctx.bubble and hasattr(ctx.bubble, "show_message"):
                ctx.bubble.show_message(msg, mood="GENTLE_NUDGE", timeout_ms=8000)

            if getattr(settings, "tts_enabled", False):
                try:
                    tts_service.speak_now(f"{settings.user_display_name} ơi, tập trung học bài nào!")
                except Exception:
                    pass

        monitor.distraction_detected.connect(on_distraction)

        # 2. Khi con tự giác quay lại học
        def on_self_corrected(app_name: str):
            if ctx.focus_engine and hasattr(ctx.focus_engine, "set_mood"):
                ctx.focus_engine.set_mood("CHEER")

            msg = f"✨ Giỏi lắm {settings.user_display_name}! Mình cùng tập trung giải quyết nốt bài tập nào!"
            if ctx.bubble and hasattr(ctx.bubble, "show_message"):
                ctx.bubble.show_message(msg, mood="CHEER", timeout_ms=6000)

        monitor.self_corrected.connect(on_self_corrected)

        # 3. Khi con xem hoặc chatchit kéo dài > 5 phút (Breach)
        def on_breach(app_name: str, duration_secs: int):
            mins = round(duration_secs / 60)
            if ctx.focus_engine and hasattr(ctx.focus_engine, "set_mood"):
                ctx.focus_engine.set_mood("GENTLE_NUDGE")

            if app_name in CHAT_APPS:
                msg = (
                    f"⏰ {settings.user_display_name} đã nhắn tin {app_name} hơn {mins} phút rồi đó. "
                    f"Hãy tạm dừng để hoàn thành mục tiêu học hôm nay nhé!"
                )
            else:
                msg = (
                    f"⏰ {settings.user_display_name} đã xem {app_name} hơn {mins} phút rồi đó. "
                    f"Hãy dừng lại để hoàn thành mục tiêu học hôm nay nhé!"
                )
            if ctx.bubble and hasattr(ctx.bubble, "show_message"):
                ctx.bubble.show_message(msg, mood="GENTLE_NUDGE", timeout_ms=10000)

        monitor.distraction_breach.connect(on_breach)

        # 4. Khi phát hiện web không an toàn
        def on_unsafe(app_name: str, _title: str):
            if ctx.focus_engine and hasattr(ctx.focus_engine, "set_mood"):
                ctx.focus_engine.set_mood("GENTLE_NUDGE")

            msg = (
                f"⚠️ Nội dung trang này ({app_name}) không an toàn cho việc học của {settings.user_display_name}, "
                f"mình hãy đóng lại nhé!"
            )
            if ctx.bubble and hasattr(ctx.bubble, "show_message"):
                ctx.bubble.show_message(msg, mood="GENTLE_NUDGE", timeout_ms=10000)

        monitor.unsafe_detected.connect(on_unsafe)

        # 5. Khi hoàn thành phiên tập trung (Deep Work completed) -> Báo cáo tổng kết & danh sách xao nhãng
        def on_session_completed(task_title: str, actual_mins: int, distraction_count: int):
            summary = ""
            if ctx.focus_engine and hasattr(ctx.focus_engine, "get_session_distractions_summary"):
                summary = ctx.focus_engine.get_session_distractions_summary(multiline=True)

            title_display = f"'{task_title}'" if task_title else "phiên làm việc"
            if distraction_count > 0 and summary:
                msg = (
                    f"🎉 {settings.user_display_name} vừa hoàn thành {actual_mins} phút cho {title_display}!\n\n"
                    f"📱 Danh sách xao nhãng trong phiên ({distraction_count} lần):\n"
                    f"{summary}\n\n"
                    f"Nghỉ ngơi một chút rồi mình tiếp tục nhé! ☕"
                )
            else:
                msg = (
                    f"🌟 Xuất sắc {settings.user_display_name}! Bạn đã tập trung trọn vẹn {actual_mins} phút cho {title_display} "
                    f"mà không hề bị xao nhãng! Tự hào quá! 👏"
                )

            if ctx.bubble and hasattr(ctx.bubble, "show_message"):
                ctx.bubble.show_message(msg, mood="CHEER", timeout_ms=10000)

        if ctx.focus_engine and hasattr(ctx.focus_engine, "session_completed"):
            ctx.focus_engine.session_completed.connect(on_session_completed)

        # 6. Hàm kích hoạt Báo cáo Cuối ngày (Hiện màn hình & Gửi Não AI)
        def trigger_end_of_day_report():
            summary_text = outbox.get_end_of_day_summary_text(display_name=settings.user_display_name)
            if ctx.focus_engine and hasattr(ctx.focus_engine, "set_mood"):
                ctx.focus_engine.set_mood("REST")
            if ctx.bubble and hasattr(ctx.bubble, "show_message"):
                ctx.bubble.show_message(summary_text, mood="REST", timeout_ms=15000)
            try:
                spawn_background_task(outbox.send_daily_report_async(), "activity-daily-report-outbox")
            except Exception:
                logger.warning("Không thể gửi báo cáo cuối ngày trong nền", exc_info=True)

        companion.trigger_activity_report = trigger_end_of_day_report

        # Khởi động monitor
        monitor.start()
        companion._activity_monitor = monitor
        logger.info("ActivityMonitor đã khởi động thành công cho học sinh '%s'", settings.user_display_name)
        return monitor

    except Exception:
        logger.exception("Không thể khởi động ActivityMonitor")
        return None
