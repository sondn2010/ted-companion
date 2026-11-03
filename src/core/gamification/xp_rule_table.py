"""Bảng luật XP — nguồn sự thật duy nhất. Chỉ đo việc làm & bài tập; nghỉ ngơi/đi chơi KHÔNG có XP."""

from typing import Optional

# (engine, kind) -> XP mặc định
XP_RULES = {
    ("focus", "session_completed"): 0,   # tính theo phút trong resolve_xp
    ("work", "task_done"): 15,
    ("work", "task_undone"): 0,          # bù trừ: repository truyền thẳng xp = −(xp task_done), không tra bảng
    ("core", "break_taken"): 3,
    ("coach", "quiz_answered"): 2,
    ("coach", "quiz_correct"): 3,        # đúng = 2 + 3 = 5
    ("coach", "agenda_done"): 20,
    ("coach", "writing_graded"): 25,
    ("core", "idea_untangled"): 10,      # hoàn tất 1 phiên Gỡ Rối Ý Tưởng (key untangle:<session_id>)
}
# (module_id, kind) -> XP ghi đè theo module
XP_MODULE_OVERRIDES = {
    ("duhoc", "writing_graded"): 35,
    ("caohoc", "quiz_correct"): 4,
    ("thcs", "agenda_done"): 25,
}
# Trần XP mỗi ngày theo kind (chống farm)
DAILY_CAPS = {"quiz_answered": 100, "quiz_correct": 150, "break_taken": 18, "idea_untangled": 30,
              "meeting_completed": 12}

PARKED_IDEA_TASK_XP = 5
FOCUS_MAX_MINUTES_XP = 60
FOCUS_NO_DISTRACTION_BONUS = 10
MEETING_MINUTES_PER_XP = 10   # họp/học nhóm: 1 XP / 10 phút (Deep Work ≈ 1 XP / phút); trần ngày: DAILY_CAPS["meeting_completed"]


def resolve_xp(engine: str, module_id: str, kind: str, meta: Optional[dict] = None) -> int:
    """XP cho một sự kiện. Kind lạ → 0 (không raise, tránh làm hỏng quét nền)."""
    meta = meta or {}
    if engine == "focus" and kind == "session_completed":
        mins = max(0, int(meta.get("mins", 0) or 0))
        if mins <= 0:
            return 0
        bonus = FOCUS_NO_DISTRACTION_BONUS if int(meta.get("distractions", 1) or 0) == 0 else 0
        return min(mins, FOCUS_MAX_MINUTES_XP) + bonus
    if engine == "meeting" and kind == "meeting_completed":
        return max(0, int(meta.get("mins", 0) or 0)) // MEETING_MINUTES_PER_XP
    if engine == "work" and kind == "task_done" and meta.get("category") == "parked_idea":
        return PARKED_IDEA_TASK_XP
    override = XP_MODULE_OVERRIDES.get((module_id, kind))
    if override is not None:
        return override
    return XP_RULES.get((engine, kind), 0)
