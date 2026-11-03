"""Cầu nối gửi báo cáo hoạt động cuối ngày lên Não AI Hermes & hiển thị tổng kết trên màn hình."""

from datetime import date, datetime, timezone
import json
import logging
from typing import Any, Callable, Dict, Optional

from src.core.activity_watcher.activity_daily_repository import ActivityDailyRepository
from src.core.activity_watcher.activity_report_builder import (
    build_activity_report_dict,
    format_ted_activity_report_message,
)

logger = logging.getLogger("ted")


class ActivityOutboxSender:
    """Quản lý việc gửi báo cáo hoạt động ngày sang Hermes và hiển thị tổng kết cho học sinh."""

    def __init__(
        self,
        repository: ActivityDailyRepository,
        client_pool: Any,
        registry: Any,
        today_fn: Callable[[], str] = lambda: date.today().isoformat(),
        learner_fn: Callable[[], str] = lambda: "con",
    ):
        self._repo = repository
        self._pool = client_pool
        self._registry = registry
        self._today_fn = today_fn
        self._learner_fn = learner_fn

    def get_end_of_day_summary_text(self, display_name: str, day_str: Optional[str] = None) -> str:
        """Tạo câu tổng kết ấm áp, ngắn gọn để hiện trên bong bóng Ted lúc chuẩn bị tắt máy."""
        day = day_str or self._today_fn()
        learner = self._learner_fn()
        rec = self._repo.get_or_create(day, learner)
        payload = build_activity_report_dict(rec)

        study_mins = payload.get("study_minutes", 0)
        distract_mins = payload.get("distraction_minutes", 0)
        focus_pct = payload.get("focus_percentage", 100)
        self_corrected = payload.get("self_corrected_count", 0)

        lines = [
            f"🌙 **Tổng kết buổi tối cùng {display_name}:**",
            f"🎯 Học sâu: **{study_mins} phút** (Độ tập trung: {focus_pct}%)",
        ]

        if distract_mins > 0:
            lines.append(f"📱 Xao nhãng: **{distract_mins} phút** ({self_corrected} lần tự giác quay lại học)")

        if focus_pct >= 80:
            lines.append(f"✨ Hôm nay {display_name} rất tập trung và nỗ lực! Chúc bạn ngủ thật ngon nhé! 🌟")
        else:
            lines.append(f"🌱 Mai mình sẽ làm tốt hơn nữa nhé! Đi ngủ sớm giữ gìn sức khỏe nào!")

        return "\n".join(lines)

    async def send_daily_report_async(self, day_str: Optional[str] = None) -> bool:
        """Gửi gói tin [TED_ACTIVITY_REPORT] sang Hermes connection đang hoạt động."""
        day = day_str or self._today_fn()
        learner = self._learner_fn()
        rec = self._repo.get_or_create(day, learner)

        # Nếu cả ngày không có hoạt động nào -> không cần gửi
        if rec.study_seconds == 0 and rec.distraction_seconds == 0 and rec.neutral_seconds == 0:
            logger.debug("Không có hoạt động nào trong ngày %s để gửi báo cáo", day)
            return False

        payload = build_activity_report_dict(rec)
        msg_text = format_ted_activity_report_message(payload)

        # Xác định connection ID của coach hoặc active module
        conn_id = None
        if self._registry and hasattr(self._registry, "active"):
            mod = self._registry.active()
            if mod:
                conn_id = getattr(mod, "connection", None)

        if not conn_id and self._pool:
            conn_id = self._pool.default_connection_id()

        if not conn_id:
            logger.warning("Không tìm thấy kết nối Hermes để gửi báo cáo hoạt động")
            return False

        client = self._pool.get(conn_id)
        if client is None:
            logger.warning("Client Hermes cho kết nối '%s' không sẵn sàng", conn_id)
            return False

        try:
            # Gửi tin nhắn hợp đồng sang Hermes
            reply = await client.chat_completion(
                [{"role": "user", "content": msg_text}],
                temperature=0.1,
            )
            logger.info("Đã gửi báo cáo hoạt động ngày %s lên Hermes: %s", day, str(reply)[:80])
            self._repo.mark_synced(day, learner)
            return True
        except Exception as exc:
            logger.warning("Gửi báo cáo hoạt động lên Hermes thất bại: %s", exc)
            return False
