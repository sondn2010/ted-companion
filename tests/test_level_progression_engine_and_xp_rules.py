"""Phase 01 gamification: engine tiến độ tuần % + level + bảng luật XP (thuần, không DB)."""

from datetime import date

from src.core.gamification.level_progression_engine import START_PCT, level_for_pct, replay_week, week_start_of
from src.core.gamification.xp_rule_table import resolve_xp

MON = date(2026, 10, 19)  # thứ Hai
D = lambda n: date.fromordinal(MON.toordinal() + n)  # noqa: E731


def test_level_mapping_from_pct():
    assert [level_for_pct(x) for x in (0, 10, 10.01, 50, 57, 90, 90.01, 100)] == [1, 1, 2, 5, 6, 9, 10, 10]
    assert level_for_pct(-5) == 1 and level_for_pct(250) == 10


def test_week_start_is_monday():
    assert week_start_of(date(2026, 10, 25)) == MON  # Chủ nhật
    assert week_start_of(MON) == MON


def test_monday_starts_at_fifty_percent_level_five():
    p = replay_week({}, MON, today=MON)
    assert p.pct == START_PCT == 50 and p.level == 5 and p.peak_level == 5 and p.pct_today_delta == 0
    # XP của tuần trước không kéo sang: thứ Hai mới luôn về 50% (+ XP của chính hôm nay)
    p = replay_week({date(2026, 10, 18): 900, MON: 30}, MON, today=MON)
    assert p.pct == 53 and p.pct_today_delta == 3


def test_xp_converts_to_pct_and_level_derives_from_it():
    p = replay_week({D(0): 90}, MON, today=D(0))
    assert p.pct == 59 and p.level == 6 and p.pct_today_delta == 9


def test_day_gain_cap_prevents_maxing_on_day_one():
    p = replay_week({D(0): 5000}, MON, today=D(0))
    assert p.pct == 65 and p.level == 7  # 50 + trần 15
    p = replay_week({D(i): 5000 for i in range(4)}, MON, today=D(3))
    assert p.pct == 100 and p.level == 10  # 4 ngày kịch trần → kẹp 100


def test_decay_applies_on_ended_low_days_including_weekend():
    # 100 XP thứ Hai (+10), các ngày sau 0 XP: −5% mỗi ngày đã kết thúc, hôm nay (CN) chưa decay
    p = replay_week({D(0): 100}, MON, today=D(6))
    assert p.pct == 60 - 5 * 5 and p.decay_days == 5 and p.active_days == 1


def test_today_not_decayed_and_no_xp_day_counts_as_decay():
    p = replay_week({D(0): 10}, MON, today=D(0))
    assert p.pct == 51 and p.decay_days == 0
    p = replay_week({D(0): 10}, MON, today=D(1))
    assert p.pct == 46 and p.decay_days == 1 and p.pct_today_delta == 0   # D(1) chưa kết thúc, 0 XP
    p = replay_week({D(0): 10, D(1): 100}, MON, today=D(2))
    assert p.pct == 51 - 5 + 10 and p.decay_days == 1


def test_revocation_lowers_pct_symmetrically():
    p = replay_week({D(0): 100, D(1): -100}, MON, today=D(1))
    assert p.pct == 50  # +10 rồi −10 đối xứng, không bị trần
    p = replay_week({D(0): -150}, MON, today=D(0))
    assert p.pct == 35 and p.pct_today_delta == -15


def test_pct_clamped_at_zero_and_hundred():
    p = replay_week({D(0): -9000}, MON, today=D(0))
    assert p.pct == 0 and p.level == 1
    p = replay_week({}, MON, today=D(6))  # cả tuần trống: 6 ngày decay −30
    assert p.pct == 20 and p.level == 2
    p = replay_week({D(0): -9000}, MON, today=D(6))
    assert p.pct == 0   # decay không đẩy âm
    p = replay_week({D(i): 150 for i in range(7)}, MON, today=D(6))
    assert p.pct == 100


def test_demotion_then_recovery_flag():
    # T2 +15 → 65 (Lv7); T3 0 XP, kết thúc → decay; thứ Tư & Năm không XP → rớt dưới Lv7; sau đó tăng lại về Lv7
    daily = {D(0): 150, D(4): 150}
    p = replay_week(daily, MON, today=D(5))
    assert p.peak_level >= 7 and p.demoted_then_recovered is True
    no_recover = replay_week({D(0): 150}, MON, today=D(3))
    assert no_recover.demoted_then_recovered is False


def test_week_boundary_sunday_to_monday_resets():
    # today vượt Chủ nhật → chỉ phát lại đến Chủ nhật, ngày CN (< today) cũng decay
    p = replay_week({D(0): 30}, MON, today=D(10))
    assert len(p.day_end_levels) == 7


def test_resolve_xp_rules():
    assert resolve_xp("work", "work", "task_done", {}) == 15
    assert resolve_xp("work", "work", "task_done", {"category": "parked_idea"}) == 5
    assert resolve_xp("coach", "duhoc", "writing_graded") == 35
    assert resolve_xp("coach", "thcs", "writing_graded") == 25
    assert resolve_xp("coach", "caohoc", "quiz_correct") == 4
    assert resolve_xp("coach", "thcs", "agenda_done") == 25
    assert resolve_xp("core", "core", "break_taken") == 3
    assert resolve_xp("core", "core", "rest_whatever") == 0
    assert resolve_xp("focus", "focus", "session_completed", {"mins": 25, "distractions": 0}) == 35
    assert resolve_xp("focus", "focus", "session_completed", {"mins": 90, "distractions": 2}) == 60
    assert resolve_xp("focus", "focus", "session_completed", {"mins": 0, "distractions": 0}) == 0
