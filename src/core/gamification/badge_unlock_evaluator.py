"""Evaluator thuần: so rule của catalog với WindowData → danh sách badge id mới đạt."""

import logging
import operator
from typing import Dict, List, Optional, Set

from src.core.gamification.badge_catalog_loader import BadgeCatalog, BadgeDef, BadgeRule
from src.core.gamification.badge_metric_calculators import FINISHED_DAY_ONLY_METRICS, METRICS, WindowData

logger = logging.getLogger("ted")

_OPS = {">=": operator.ge, "<=": operator.le}
MIN_ACTIVE_DAYS_FOR_WEEK_LE = 3  # rule "<=" theo tuần cần >= 3 ngày hoạt động (tránh mở huy hiệu cho tuần trống)


def rule_satisfied(rule: BadgeRule, data: WindowData) -> bool:
    calc = METRICS.get(rule.metric)
    if calc is None:
        logger.warning("Metric chưa đăng ký: %s", rule.metric)
        return False
    if rule.min is not None and METRICS[rule.min.metric](data) < rule.min.value:
        return False
    if rule.op == "<=" and rule.window == "week" and METRICS["active_days"](data) < MIN_ACTIVE_DAYS_FOR_WEEK_LE:
        return False
    return _OPS[rule.op](calc(data), rule.value)


def _badge_earned(badge: BadgeDef, windows: Dict[str, object]) -> bool:
    key = badge.rule.window
    if key == "day" and badge.rule.metric in FINISHED_DAY_ONLY_METRICS and "day_final" in windows:
        key = "day_final"   # chỉ các ngày đã kết thúc (không gồm hôm nay)
    data = windows.get(key)
    if data is None:
        return False  # cửa sổ không được cung cấp (vd backfill không có lifetime)
    if badge.rule.window == "day":
        return any(rule_satisfied(badge.rule, d) for d in data)  # data = list[WindowData], mỗi phần tử 1 ngày
    return rule_satisfied(badge.rule, data)


def evaluate(catalog: BadgeCatalog, windows: Dict[str, object], unlocked_this_week: Set[str],
             unlocked_ever: Optional[Set[str]] = None) -> List[str]:
    """windows = {"day": [WindowData...], "week": WindowData, "lifetime": WindowData}.
    day/week: bỏ qua nếu đã mở trong tuần này; lifetime: bỏ qua nếu đã từng mở."""
    ever = unlocked_ever or set()
    earned = []
    for badge in catalog.badges:
        if badge.rule.window == "lifetime":
            if badge.id in ever:
                continue
        elif badge.id in unlocked_this_week:
            continue
        if _badge_earned(badge, windows):
            earned.append(badge.id)
    return earned
