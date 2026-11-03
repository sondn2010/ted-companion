"""Soạn + phát bubble của Hub: câu "huy hiệu / nhân vật mới" và hàng đợi 1 tin khi bubble đang bận (không Qt)."""

import logging
from typing import Any, Optional

from src.core.gamification.badge_catalog_loader import BadgeDef
from src.core.i18n import i18n, tr

logger = logging.getLogger("ted")


def _badge_name(badge: BadgeDef) -> str:
    return badge.name.get("vi") or badge.name.get("en") or badge.id


def _skin_unlocked_message(skins: list) -> str:
    """"🎭 Mở khóa nhân vật mới: A, B +3" — tên theo ngôn ngữ hiện tại, tối đa 2 tên."""
    vi = i18n.current_language == "vi"
    names = ", ".join((s.name_vi if vi else s.name_en) for s in skins[:2])
    return tr("skin_unlocked_bubble", name=names + (f" +{len(skins) - 2}" if len(skins) > 2 else ""))


def compose_unlock_message(new_badges: list, new_skins: list) -> str:
    """Gộp huy hiệu + nhân vật mới thành 1 câu; rỗng nếu không có gì mới."""
    parts = (["🏅 " + ", ".join(_badge_name(b) for b in new_badges)] if new_badges else []) + \
            ([_skin_unlocked_message(new_skins)] if new_skins else [])
    return " · ".join(parts)


class PendingBubble:
    """Hiện bubble; đang bận -> giữ 1 tin chờ (tin mới ghi đè), thử lại ở tick/refresh sau."""

    def __init__(self, ctx: Any):
        self._ctx = ctx
        self._pending: Optional[str] = None

    def say(self, text: str) -> None:
        self._pending = text
        self.flush()

    def flush(self) -> None:
        bubble = getattr(self._ctx, "bubble", None)
        if not self._pending or bubble is None:
            return
        try:
            if bubble.is_busy():
                return
            bubble.show_message(self._pending, "CHEER")
            self._pending = None
        except Exception:  # noqa: BLE001
            logger.exception("Không hiện được bubble gamification")
            self._pending = None
