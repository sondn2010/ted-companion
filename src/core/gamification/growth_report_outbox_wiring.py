"""Nối outbox báo cáo tăng trưởng vào Hub: chạy ở snapshot đầu tiên (khởi động) rồi tối đa mỗi giờ 1 lần."""

import logging
import time
from typing import Any, Callable, Optional

from src.core.background_task_spawner import spawn_background_task
from src.core.gamification.growth_report_aggregation import GrowthSources
from src.core.gamification.growth_report_outbox_sender import GrowthReportOutboxSender

logger = logging.getLogger("ted")

MIN_INTERVAL_SECONDS = 3600


def attach_growth_report_outbox(ctx: Any, clock: Callable[[], float] = time.monotonic) -> Optional[GrowthReportOutboxSender]:
    """Gắn vào ctx.gamification.snapshot_changed. Thiếu Hub/registry/client_pool → bỏ qua (trả None)."""
    hub = getattr(ctx, "gamification", None)
    if hub is None or ctx.registry is None or ctx.client_pool is None:
        return None
    try:
        sender = GrowthReportOutboxSender(
            GrowthSources(hub._engine, hub.ledger, hub.wellbeing, hub.unlocks), ctx.registry, ctx.client_pool)
    except Exception:  # noqa: BLE001 - outbox hỏng không được làm sập app
        logger.exception("Không khởi tạo được outbox báo cáo tăng trưởng")
        return None
    last = {"at": None}

    def on_snapshot(_snap: Any) -> None:
        now = clock()
        if last["at"] is not None and now - last["at"] < MIN_INTERVAL_SECONDS:
            return
        last["at"] = now
        try:
            spawn_background_task(sender.run_cycle(), "growth-report-outbox")
        except Exception:  # noqa: BLE001 - không có event loop: thử lại ở snapshot sau
            last["at"] = None
            logger.warning("Chưa chạy được outbox báo cáo tăng trưởng", exc_info=True)

    hub.snapshot_changed.connect(on_snapshot)
    return sender
