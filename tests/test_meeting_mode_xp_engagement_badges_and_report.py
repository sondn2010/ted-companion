"""Hub phase 13: XP họp (vừa phải, trần ngày, không lẫn Deep Work), delta Gắn kết/Quan hệ, 3 huy hiệu mới, báo cáo Hermes (không topic)."""

import json
from datetime import date, datetime, time, timedelta, timezone

import pytest
from sqlmodel import Session

from src.core.app_state_key_value_store import KeyValueStore
from src.core.gamification.badge_catalog_loader import load_badge_catalog
from src.core.gamification.badge_unlock_evaluator import evaluate
from src.core.gamification.day_signals_collector import DaySignals, collect_day_signals
from src.core.gamification.growth_report_aggregation import GrowthSources, collect_day, collect_week
from src.core.gamification.growth_report_contract_schemas import GrowthReport
from src.core.gamification.growth_report_payload_builder import build_daily_payload, build_weekly_payload
from src.core.gamification.lifetime_totals_builder import build_lifetime_totals
from src.core.gamification.badge_unlock_repository import BadgeUnlockRepository
from src.core.gamification.week_context_builder import build_week_context, to_window_data_by_kind
from src.core.gamification.weekly_running_stats import running_week_stats, stats_delta
from src.core.gamification.wellbeing_daily_repository import WellbeingDailyRepository
from src.core.gamification.wellbeing_stat_formulas import compute_day_stats, has_stat_activity
from src.core.gamification.xp_ledger_repository import XpLedgerRepository
from src.core.gamification.xp_rule_table import DAILY_CAPS, resolve_xp
from src.core.gamification.xp_source_reconciler import XpSourceReconciler
from src.core.meeting_mode.meeting_session_table_model_and_repository import MeetingSession
from src.core.models import FocusSession

TOPIC = "Bí mật dự án X"


def _at(day: date, hour: int = 10) -> datetime:
    return datetime.combine(day, time(hour)).astimezone(timezone.utc)


def _meeting(engine, day: date, minutes: int, kind: str = "team_meeting", hour: int = 10) -> None:
    start = _at(day, hour)
    with Session(engine) as s:
        s.add(MeetingSession(kind=kind, topic=TOPIC, started_at=start, ended_at=start + timedelta(minutes=minutes),
                             actual_minutes=minutes))
        s.commit()


@pytest.fixture
def parts(memory_engine):
    return (XpLedgerRepository(memory_engine), WellbeingDailyRepository(memory_engine))


def _reconciler(engine, ledger):
    return XpSourceReconciler(engine, ledger, KeyValueStore(engine), lambda _m: "coach")


# ---- XP ----
def test_xp_rule_is_one_per_ten_minutes_and_far_below_deep_work():
    assert resolve_xp("meeting", "meeting", "meeting_completed", {"mins": 60}) == 6
    assert resolve_xp("meeting", "meeting", "meeting_completed", {"mins": 9}) == 0
    assert resolve_xp("focus", "focus", "session_completed", {"mins": 60, "distractions": 1}) == 60


def test_reconciler_awards_meeting_xp_once_and_caps_per_day(memory_engine, parts):
    ledger, _ = parts
    today = date.today()
    _meeting(memory_engine, today, 60)
    _meeting(memory_engine, today, 120, hour=12)
    _meeting(memory_engine, today, 30, hour=15)
    rec = _reconciler(memory_engine, ledger)
    now = datetime.now(timezone.utc)
    assert rec.run(now) == 3
    assert rec.run(now) == 0                                  # quét lại không cộng đôi
    assert ledger.daily_totals(today, today)[today] == DAILY_CAPS["meeting_completed"] == 12   # 6 + 12 + 3 → kẹp 12


def test_meeting_is_not_counted_as_deep_work(memory_engine, parts):
    ledger, wellbeing = parts
    today = date.today()
    _meeting(memory_engine, today, 45)
    _reconciler(memory_engine, ledger).run(datetime.now(timezone.utc))
    assert "session_completed" not in ledger.lifetime_counts()
    sig = collect_day_signals(memory_engine, ledger, wellbeing, today)
    assert (sig.focus_minutes, sig.sessions, sig.focus_chain_max) == (0, 0, 0)
    assert (sig.meeting_sessions, sig.meeting_session_minutes) == (1, 45)
    totals = build_lifetime_totals(memory_engine, ledger, today)
    assert totals["focus_minutes"] == 0 and totals["focus_sessions"] == 0 and totals["meetings_done"] == 1


# ---- Gắn kết / Quan hệ ----
def _engagement_delta(sig: DaySignals) -> int:
    run = running_week_stats([compute_day_stats(sig)], [has_stat_activity(sig)])
    return stats_delta(None, run[0])["engagement"]


def test_meeting_gives_strong_positive_engagement_delta():
    quiet_day = DaySignals(app_on_minutes=300)
    one_hour = DaySignals(app_on_minutes=300, meeting_sessions=1, meeting_session_minutes=60)
    assert _engagement_delta(quiet_day) < 0
    assert _engagement_delta(one_hour) >= 10
    assert _engagement_delta(DaySignals(meeting_sessions=1, meeting_session_minutes=10)) > _engagement_delta(quiet_day)


def test_meeting_only_day_counts_as_active_day():
    assert has_stat_activity(DaySignals(meeting_session_minutes=20)) and not has_stat_activity(DaySignals())


# ---- huy hiệu ----
def _earned(engine, ledger, wellbeing, today: date) -> set:
    week = today - timedelta(days=today.weekday())
    ctx = build_week_context(engine, ledger, wellbeing, week, today)
    totals = build_lifetime_totals(engine, ledger, today)
    return set(evaluate(load_badge_catalog(), to_window_data_by_kind(ctx, totals), set()))


def test_three_new_badges_are_in_catalog_with_images():
    catalog = load_badge_catalog(strict=True)
    ids = {b.id: b for b in catalog.badges}
    assert len(ids) == 53
    for bid in ("team_player", "study_with_teacher", "steady_connection"):
        assert ids[bid].image_path().exists()
    assert ids["team_player"].rule.window == "week" and ids["steady_connection"].rule.value == 10


def test_team_player_needs_three_meetings_in_one_week(memory_engine, parts):
    ledger, wellbeing = parts
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    _meeting(memory_engine, monday, 30)
    _meeting(memory_engine, monday, 30, hour=14)
    assert "team_player" not in _earned(memory_engine, ledger, wellbeing, today)
    _meeting(memory_engine, monday, 30, hour=17)
    assert "team_player" in _earned(memory_engine, ledger, wellbeing, today)


def test_teacher_and_lifetime_badges(memory_engine, parts):
    ledger, wellbeing = parts
    today = date.today()
    for i in range(3):
        _meeting(memory_engine, today - timedelta(days=20 + i), 40, kind="teacher")
    got = _earned(memory_engine, ledger, wellbeing, today)
    assert "study_with_teacher" in got and "steady_connection" not in got and "team_player" not in got
    for i in range(7):
        _meeting(memory_engine, today - timedelta(days=40 + i), 30)
    assert "steady_connection" in _earned(memory_engine, ledger, wellbeing, today)


# ---- báo cáo Hermes: chỉ số đếm, KHÔNG topic ----
def test_growth_reports_carry_counts_but_never_topics(memory_engine, parts):
    ledger, wellbeing = parts
    today = date.today()
    _meeting(memory_engine, today, 45, kind="teacher")
    _meeting(memory_engine, today, 30, hour=14)
    src = GrowthSources(memory_engine, ledger, wellbeing, BadgeUnlockRepository(memory_engine))
    day, week = collect_day(src, today, set()), collect_week(src, today - timedelta(days=today.weekday()), set())
    payloads = [build_daily_payload(k, "bin", day) for k in ("general", "learning")]
    payloads += [build_weekly_payload(k, "bin", week) for k in ("general", "learning")]
    for p in payloads:
        GrowthReport.model_validate(p)
        assert TOPIC not in json.dumps(p, ensure_ascii=False) and "topic" not in json.dumps(p)
    assert payloads[0]["counts"]["meetings"] == 2 and payloads[0]["counts"]["meeting_minutes"] == 75
    assert payloads[1]["counts"]["study_meetings"] == 1 and payloads[1]["counts"]["study_meeting_minutes"] == 45
    assert payloads[2]["counts"] == {"meetings": 2, "meeting_minutes": 75}
    assert payloads[3]["counts"]["study_meetings"] == 1


def test_focus_rows_and_meeting_rows_coexist_in_day_signals(memory_engine, parts):
    ledger, wellbeing = parts
    today = date.today()
    with Session(memory_engine) as s:
        s.add(FocusSession(actual_minutes=25, focus_rating=5, started_at=_at(today, 9), ended_at=_at(today, 9) + timedelta(minutes=25)))
        s.commit()
    _meeting(memory_engine, today, 20, hour=13)
    sig = collect_day_signals(memory_engine, ledger, wellbeing, today)
    assert sig.focus_minutes == 25 and sig.meeting_session_minutes == 20
