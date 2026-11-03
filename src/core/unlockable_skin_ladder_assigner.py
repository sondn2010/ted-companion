"""Bậc thang điều kiện tự gán cho nhân vật MỚI (xen kẽ số huy hiệu và mục tiêu chỉ số, độ khó tăng dần).

Vị trí i trong registry → LADDER[i]; quá bậc cuối → thêm huy hiệu mỗi bậc (trần 50). Không bao giờ ghi đè điều kiện
đã có trong registry (dev có thể sửa tay).
"""

from typing import Iterable

from src.core.unlockable_skin_registry_model import SkinCondition, UnlockableSkin


def _b(count: int) -> SkinCondition:
    return SkinCondition("badges", count=count)


def _m(metric: str, value: int) -> SkinCondition:
    return SkinCondition("metric", metric=metric, value=value)


LADDER: tuple[SkinCondition, ...] = (
    _b(1), _m("focus_sessions", 3), _b(2), _m("tasks_done", 5), _b(3), _m("quiz_answered", 10),
    _m("untangle_sessions", 1), _b(5), _m("peak_level", 6), _m("focus_sessions", 10), _b(7), _m("tasks_done", 20),
    _m("best_streak_days", 3), _m("quiz_correct", 20), _b(10), _m("untangle_sessions", 5), _m("quiz_answered", 30),
    _m("peak_level", 7), _b(12), _m("focus_sessions", 25), _m("best_streak_days", 7), _m("tasks_done", 50),
    _b(15), _m("quiz_answered", 100), _m("writing_graded", 3), _b(18), _m("quiz_correct", 100), _m("peak_level", 9),
    _m("best_streak_days", 14), _b(22), _m("focus_sessions", 50), _m("tasks_done", 100), _b(26),
    _m("quiz_answered", 300), _b(30), _m("focus_minutes", 3000),
)
MAX_BADGE_TARGET = 50
_LAST_BADGE_TARGET = 30   # mốc huy hiệu cuối của LADDER, các bậc vượt thêm 4 huy hiệu mỗi nhân vật


def ladder_condition(index: int) -> SkinCondition:
    if index < len(LADDER):
        return LADDER[index]
    return _b(min(MAX_BADGE_TARGET, _LAST_BADGE_TARGET + 4 * (index - len(LADDER) + 1)))


def assign_new_skins(existing: list[UnlockableSkin],
                     candidates: Iterable[tuple[str, str, str, str]]) -> list[UnlockableSkin]:
    """existing giữ nguyên thứ tự + điều kiện; candidates = (key, pack, name_vi, name_en) chưa có → nối đuôi với bậc thang."""
    result = list(existing)
    known = {s.key for s in result}
    for key, pack, name_vi, name_en in candidates:
        if key in known:
            continue
        known.add(key)
        result.append(UnlockableSkin(key, pack, name_vi, name_en, ladder_condition(len(result))))
    return result
