"""Đánh giá điều kiện mở khoá nhân vật theo số liệu trọn đời + mô tả điều kiện theo ngôn ngữ hiện tại (thuần, không Qt)."""

import logging
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Dict, FrozenSet, Tuple

from src.core.i18n import i18n, tr
from src.core.unlockable_skin_registry_model import METRIC_LABELS, SkinCondition


@dataclass(frozen=True)
class SkinProgressInputs:
    badge_ids: FrozenSet[str] = field(default_factory=frozenset)   # mọi huy hiệu từng mở
    metrics: Dict[str, float] = field(default_factory=dict)        # chỉ số trọn đời (tên trong METRIC_LABELS)


def condition_progress(condition: SkinCondition, inputs: SkinProgressInputs) -> Tuple[float, float]:
    """(hiện tại, mục tiêu) — thanh tiến độ; free = (1, 1). Hiện tại có thể vượt mục tiêu (caller tự kẹp)."""
    if condition.type == "badges":
        return float(len(inputs.badge_ids)), float(condition.count)
    if condition.type == "badge":
        return (1.0 if condition.badge_id in inputs.badge_ids else 0.0), 1.0
    if condition.type == "metric":
        return float(inputs.metrics.get(condition.metric, 0.0)), float(condition.value)
    return 1.0, 1.0


def is_condition_met(condition: SkinCondition, inputs: SkinProgressInputs) -> bool:
    current, target = condition_progress(condition, inputs)
    return current >= target


@lru_cache(maxsize=1)
def _catalog_badge_names() -> Dict[str, dict]:
    """{badge_id: {"vi","en"}} từ badge_catalog.json (đọc 1 lần); catalog hỏng → rỗng, UI rơi về hiện id."""
    try:
        from src.core.gamification.badge_catalog_loader import load_badge_catalog
        return {b.id: dict(b.name) for b in load_badge_catalog().badges}
    except Exception:
        logging.getLogger("ted").warning("Không đọc được tên huy hiệu cho điều kiện mở khoá", exc_info=True)
        return {}


def _badge_display_name(badge_id: str, badge_names: Dict[str, str] | None) -> str:
    """Tên huy hiệu theo ngôn ngữ hiện tại (badge_names truyền vào ưu tiên); không có thì dùng id thô."""
    if badge_names and badge_id in badge_names:
        return badge_names[badge_id]
    names = _catalog_badge_names().get(badge_id) or {}
    return names.get(i18n.current_language) or names.get("en") or badge_id


def describe_condition(condition: SkinCondition, badge_names: Dict[str, str] | None = None) -> str:
    """Câu mô tả ("Cần 5 huy hiệu", "Làm 10 bài tập") theo ngôn ngữ đang chọn."""
    if condition.type == "badges":
        return tr("skin_cond_badges", n=condition.count)
    if condition.type == "badge":
        return tr("skin_cond_badge", name=_badge_display_name(condition.badge_id, badge_names))
    if condition.type == "metric":
        vi, en = METRIC_LABELS[condition.metric]
        what = vi if i18n.current_language == "vi" else en
        return tr("skin_cond_metric", n=int(condition.value), what=what)
    return tr("skin_cond_free")
