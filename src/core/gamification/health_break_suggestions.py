"""Bảng gợi ý sức khỏe nhỏ OFFLINE (khi Hermes lỗi/quá 3s/không phải profile Work) + chọn xoay vòng.

Quy tắc: không lặp 2 loại gần nhất; nước nếu >90 phút chưa uống; khuya (22h–5h) hoặc bản an toàn cho trẻ
→ bỏ động tác mạnh (chống đẩy). Không có XP: nghỉ ngơi không bao giờ kiếm XP.
"""

import random
from typing import List, Optional, Sequence, Tuple

from src.core.gamification.health_break_contract_schema import HealthBreakKind, HealthBreakSuggestion

WATER_DUE_MINUTES = 90
AVOID_LAST_KINDS = 2
LATE_NIGHT_FROM_HOUR, LATE_NIGHT_TO_HOUR = 22, 5

# (action_id, kind, giây, mạnh?, vi, en)
_TABLE: Tuple[Tuple[str, HealthBreakKind, int, bool, str, str], ...] = (
    ("stand_up_stretch", "move", 30, False, "Đứng dậy vươn vai thật dài 30 giây nhé!", "Stand up and stretch tall for 30 seconds!"),
    ("walk_one_minute", "move", 60, False, "Đi lại một vòng quanh phòng khoảng 1 phút nhé.", "Take a one-minute stroll around the room."),
    ("calf_raises", "move", 30, False, "Nhón gót 10 cái cho máu lưu thông nè.", "Do 10 slow calf raises to get the blood moving."),
    ("pushups_small", "move", 30, True, "Thử 5 cái chống đẩy nhẹ nhàng, vừa sức thôi nha!", "Try 5 easy push-ups, only what feels comfortable!"),
    ("pushups_set", "move", 60, True, "Làm 10–15 cái chống đẩy tại chỗ để kích hoạt cơ bắp và bơm máu lên não nào! 💪", "Do 10–15 push-ups right here to energize your body and pump fresh blood to your brain! 💪"),
    ("pullups_bar", "move", 60, True, "Lên xà đơn kéo 5–10 cái hoặc đu xà thả lỏng cột sống thật sảng khoái nhé! 🏋️", "Do 5–10 pull-ups or hang from the bar to decompress your spine! 🏋️"),
    ("back_bend_stretch", "posture", 45, False, "Đứng thẳng rồi từ từ cúi gập lưng sâu, tay chạm ngón chân để giải tỏa áp lực cột sống 30 giây nha! 🧘", "Stand tall and gently bend forward to touch your toes for 30 seconds to ease spinal tension! 🧘"),
    ("back_arch_chest", "posture", 30, False, "Đan tay sau lưng, ưỡn ngực và ngửa lưng nhẹ nhàng 30 giây để giãn toàn bộ cột sống lưng.", "Clasp hands behind your back, open your chest, and gently arch back for 30 seconds."),
    ("squats_set", "move", 45, True, "Làm 10–15 cái squat tại chỗ để thư giãn khớp háng và đôi chân sau thời gian ngồi làm việc.", "Do 10–15 bodyweight squats to wake up your legs and refresh your body."),
    ("lumbar_twist_stretch", "posture", 30, False, "Đứng xoay vặn thân người nhẹ nhàng sang hai bên để thư giãn thắt lưng và cơ liên sườn 30 giây.", "Gently twist your torso side to side to loosen up your lower back and ribs for 30 seconds."),
    ("drink_water_glass", "water", 15, False, "Uống một ly nước nhé, cơ thể đang cần đó.", "Have a glass of water, your body will thank you."),
    ("refill_bottle", "water", 30, False, "Đi rót đầy bình nước rồi uống vài ngụm nha.", "Refill your bottle and take a few sips."),
    ("rule_20_20_20", "eyes", 20, False, "Nhìn xa 6 mét trong 20 giây để mắt được nghỉ nhé.", "Look at something 20 feet away for 20 seconds to rest your eyes."),
    ("palming_eyes", "eyes", 30, False, "Xoa hai bàn tay cho ấm rồi úp nhẹ lên mắt 30 giây.", "Rub your palms warm and rest them gently over your eyes for 30 seconds."),
    ("box_breathing", "breath", 60, False, "Hít vào 4 nhịp, giữ 4, thở ra 4, lặp lại trong 1 phút nhé.", "Breathe in for 4, hold 4, out for 4, repeat for a minute."),
    ("slow_breath_4_6", "breath", 45, False, "Hít sâu 4 nhịp, thở ra chậm 6 nhịp, vài lần thôi.", "Inhale for 4, exhale slowly for 6, a few rounds."),
    ("shoulder_rolls", "posture", 20, False, "Xoay vai ra sau 10 vòng cho đỡ mỏi nhé.", "Roll your shoulders back 10 times to ease the tension."),
    ("neck_gentle_stretch", "posture", 30, False, "Nghiêng cổ nhẹ nhàng sang mỗi bên 15 giây, đừng gồng nha.", "Gently tilt your neck to each side for 15 seconds, no forcing."),
    ("wrist_stretch", "posture", 20, False, "Duỗi và xoay cổ tay vài vòng cho tay đỡ mỏi nhé.", "Stretch and rotate your wrists a few times."),
)
KINDS: Tuple[HealthBreakKind, ...] = ("move", "water", "eyes", "breath", "posture")


def is_late_night(hour: int) -> bool:
    return hour >= LATE_NIGHT_FROM_HOUR or hour < LATE_NIGHT_TO_HOUR


def _items_of(kind: str, gentle_only: bool) -> List[HealthBreakSuggestion]:
    return [HealthBreakSuggestion(action_id=i, text_vi=vi, text_en=en, duration_sec=sec, kind=k)
            for i, k, sec, strong, vi, en in _TABLE if k == kind and not (gentle_only and strong)]


def pick_offline_suggestion(
    recent_kinds: Sequence[str] = (),
    minutes_since_water: Optional[float] = None,
    local_hour: int = 12,
    kid_safe: bool = False,
    rng: Optional[random.Random] = None,
) -> HealthBreakSuggestion:
    """recent_kinds: loại đã gợi ý (cũ → mới). minutes_since_water None = chưa biết → coi như đã lâu."""
    rng = rng or random.Random()
    gentle_only = kid_safe or is_late_night(local_hour)
    last = list(recent_kinds)[-AVOID_LAST_KINDS:]
    water_due = (minutes_since_water is None or minutes_since_water > WATER_DUE_MINUTES) \
        and not (last and last[-1] == "water")
    if water_due:
        return rng.choice(_items_of("water", gentle_only))
    candidates = [k for k in KINDS if k not in last] or [k for k in KINDS if k != (last[-1] if last else None)]
    return rng.choice(_items_of(rng.choice(candidates), gentle_only))


EXERCISE_ACTION_IDS: Tuple[str, ...] = (
    "pushups_small",
    "pushups_set",
    "pullups_bar",
    "back_bend_stretch",
    "back_arch_chest",
    "squats_set",
    "lumbar_twist_stretch",
)


def pick_exercise_suggestion(
    recent_actions: Sequence[str] = (),
    local_hour: int = 12,
    kid_safe: bool = False,
    rng: Optional[random.Random] = None,
) -> HealthBreakSuggestion:
    """Chọn bài tập thể dục tại chỗ (chống đẩy, kéo xà, gập lưng, squats,...) xoay vòng sau Deep Work."""
    rng = rng or random.Random()
    gentle_only = kid_safe or is_late_night(local_hour)
    items = [
        HealthBreakSuggestion(action_id=i, text_vi=vi, text_en=en, duration_sec=sec, kind=k)
        for i, k, sec, strong, vi, en in _TABLE
        if i in EXERCISE_ACTION_IDS and not (gentle_only and strong)
    ]
    if not items:
        items = [
            HealthBreakSuggestion(action_id=i, text_vi=vi, text_en=en, duration_sec=sec, kind=k)
            for i, k, sec, strong, vi, en in _TABLE
            if i in EXERCISE_ACTION_IDS
        ]
    recent_set = set(recent_actions[-2:] if len(recent_actions) >= 2 else recent_actions)
    candidates = [it for it in items if it.action_id not in recent_set] or items
    return rng.choice(candidates)
