"""Cài watcher nudge Gỡ Rối vào app: hiện bubble GENTLE_NUDGE (không TTS), nút mở → watcher.nudge_requested.

Phase 06 gọi `install_untangle_nudge_watcher(...)` từ main.py và nối `watcher.nudge_requested` vào hộp thoại.
"""

from typing import Callable, Optional, Tuple

from sqlalchemy.engine import Engine

from src.core.app_state_key_value_store import KeyValueStore
from src.core.i18n import tr
from src.core.idea_untangle.untangle_nudge_watcher import NudgeOffer, UntangleNudgeWatcher

NUDGE_BUBBLE_TIMEOUT_MS = 20_000
_TEXT_KEY_BY_REASON = {
    "overrun": "untangle_nudge_overrun",
    "streak": "untangle_nudge_streak",
    "distracted": "untangle_nudge_distracted",
    "wrong_streak": "untangle_nudge_wrong_streak",
}


def install_untangle_nudge_watcher(
    focus_engine,
    bubble,
    db_engine: Engine,
    kv: KeyValueStore,
    module_context: Callable[[], Tuple[str, str]],
    is_untangle_dialog_visible: Callable[[], bool] = lambda: False,
    parent=None,
) -> UntangleNudgeWatcher:
    """Trả watcher đã connect; caller PHẢI giữ tham chiếu (không parent thì bị GC) và nối `nudge_requested(module_id, task_id, kind, trigger)`.

    module_context() → (module_id, engine "work"|"coach"). Bubble đang hiện / dialog đang mở → không nudge.
    """
    watcher: Optional[UntangleNudgeWatcher] = None

    def on_offer(offer: NudgeOffer) -> None:
        text = tr(_TEXT_KEY_BY_REASON.get(offer.reason, "untangle_nudge_overrun"), task=offer.task_title)
        focus_engine.set_mood("GENTLE_NUDGE")
        bubble.show_message(
            text, mood="GENTLE_NUDGE", timeout_ms=NUDGE_BUBBLE_TIMEOUT_MS,
            actions=[(tr("untangle_nudge_action_open"), watcher.open_offer),
                     (tr("untangle_nudge_action_later"), lambda: None)],   # "Để sau" / timeout = bị bỏ qua (đã tính lúc hiện)
        )

    watcher = UntangleNudgeWatcher(
        focus_engine, db_engine, kv, module_context, on_offer,
        is_suppressed=lambda: bubble.is_busy() or is_untangle_dialog_visible(), parent=parent)
    watcher.connect_signals()
    return watcher
