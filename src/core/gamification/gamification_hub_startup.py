"""Khởi động Gamification Hub cho main.py: lỗi giữa chừng không để lại Hub nửa vời vẫn chạy timer."""

import logging
from typing import Any

logger = logging.getLogger("ted")


def start_gamification_hub(ctx: Any, engine: Any) -> None:
    """Dựng + start Hub, gắn outbox báo cáo và trang Nhân vật. Lỗi bất kỳ -> stop() Hub đã start dở,
    ctx.gamification = None và gỡ khóa skin (nếu không bộ mở khoá đóng băng, nhân vật bị khóa vĩnh viễn)."""
    hub = None
    try:
        from src.core.gamification.gamification_hub_service import GamificationHubService
        hub = GamificationHubService(ctx, engine)
        ctx.gamification = hub
        hub.start()
        from src.core.gamification.growth_report_outbox_wiring import attach_growth_report_outbox
        attach_growth_report_outbox(ctx)   # gửi báo cáo tăng trưởng sang Hermes (offline-safe, tối đa mỗi giờ)
        ctx.dashboard.bind_gamification(hub)   # trang Nhân vật hiện tiến độ mở khoá
    except Exception:
        logger.exception("Không khởi động được Gamification Hub, tiếp tục không có Hub")
        ctx.gamification = None
        if hub is not None:
            try:
                hub.stop()   # dừng timer + chặn tín hiệu focus của Hub nửa vời
            except Exception:  # noqa: BLE001
                logger.exception("Không dừng được Gamification Hub hỏng")
        from src.core.skin_unlock_gate import set_unlocked_skin_keys
        set_unlocked_skin_keys(None)
