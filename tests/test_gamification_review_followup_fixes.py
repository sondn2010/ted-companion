"""Regression test cho các lỗi còn mở của review gamification core (H1 riêng tư learner, H3 single-instance,
M1 Hub nửa vời, M2 huy hiệu ngày, M3 họp trùng lịch, M5 data stat learning, M6 phản hồi lỗi health-break)."""

import asyncio
import json
from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace

import pytest
from growth_report_test_support import TODAY, FakePool, fake_registry, local_noon, make_sources, seed_study_day
from qt_offscreen_app_helper import get_qapp
from sqlmodel import Session

from src.core.gamification.badge_unlock_service import BadgeUnlockService
from src.core.gamification.day_signals_collector import collect_day_signals
from src.core.gamification.gamification_table_models import BadgeUnlock
from src.core.gamification.growth_report_aggregation import collect_day, collect_week
from src.core.gamification.growth_report_outbox_sender import GrowthReportOutboxSender
from src.core.gamification.growth_report_payload_builder import build_weekly_payload
from src.core.gamification.health_break_hermes_suggestion_fetcher import HealthBreakContext, fetch_hermes_suggestion
from src.core.gamification.wellbeing_daily_repository import WellbeingDailyRepository
from src.core.gamification.wellbeing_stat_formulas import compute_day_stats
from src.core.gamification.xp_ledger_repository import XpLedgerRepository
from src.core.meeting_mode.meeting_session_table_model_and_repository import MeetingSession
from src.core.models import FocusSession
from src.core.single_instance_guard import ALLOW_MULTIPLE_ENV, acquire_single_instance

NOW = datetime(2026, 10, 22, 5, 0, tzinfo=timezone.utc)
YESTERDAY = TODAY - timedelta(days=1)


def _two_children(engine):
    """thcs (bin) trên kết nối c1, duhoc (an) trên kết nối c2."""
    src = make_sources(engine)
    registry = fake_registry(("thcs", "coach", "bin"), ("duhoc", "coach", "an"))
    sender = GrowthReportOutboxSender(src, registry, FakePool({"thcs": "c1", "duhoc": "c2"}, {}),
                                      now=lambda: NOW, local_today=lambda: TODAY)
    return sender, src


def _seed_duhoc_quiz(src, day: date, n: int) -> None:
    for i in range(n):
        src.ledger.add(f"qa:duhoc:{day}:{i}", local_noon(day), "duhoc", "coach", "quiz_answered")
        src.ledger.add(f"qc:duhoc:{day}:{i}", local_noon(day), "duhoc", "coach", "quiz_correct")


# ---- H1: learning report chỉ chứa dữ liệu module của chính kết nối đích ----
def test_learning_reports_never_mix_data_between_children(memory_engine):
    sender, src = _two_children(memory_engine)
    seed_study_day(src, YESTERDAY, "thcs")           # thcs: 3 trả lời, 1 đúng
    _seed_duhoc_quiz(src, YESTERDAY, 10)             # duhoc: 10 trả lời, 10 đúng → đủ huy hiệu quiz_correct_day_bronze
    with Session(memory_engine) as s:                # huy hiệu đã mở toàn cục (ledger chung) vào hôm qua
        s.add(BadgeUnlock(badge_id="quiz_correct_day_bronze", week_start="2026-10-19",
                          unlocked_at=local_noon(YESTERDAY)))
        s.commit()
    assert sender.enqueue_missing() >= 2
    c1 = json.loads(sender.outbox.pending_reports("growth.daily@c1")[0].payload_json)
    c2 = json.loads(sender.outbox.pending_reports("growth.daily@c2")[0].payload_json)
    assert (c1["learner"], c1["counts"]["quiz_answered"], c1["counts"]["quiz_correct"]) == ("bin", 3, 1)
    assert (c2["learner"], c2["counts"]["quiz_answered"], c2["counts"]["quiz_correct"]) == ("an", 10, 10)
    assert 0 < c1["coach_xp"] < c2["coach_xp"]
    assert (c1["badges_total"], c1["badges_new"]) == (0, [])      # huy hiệu của duhoc không lộ sang thcs
    assert (c2["badges_total"], c2["badges_new"]) == (1, ["quiz_correct_day_bronze"])


def test_learning_week_aggregate_is_scoped_per_learner(memory_engine):
    sender, src = _two_children(memory_engine)
    seed_study_day(src, YESTERDAY, "thcs")
    _seed_duhoc_quiz(src, YESTERDAY, 4)
    week = date(2026, 10, 19)
    payloads = {}
    for target in sender.targets():
        agg = collect_week(sender._sources_for(target), week, sender._learn)
        payloads[target.learner] = build_weekly_payload(target.report_kind, target.learner, agg)
    assert payloads["bin"]["counts"]["quiz_answered"] == 3 and payloads["an"]["counts"]["quiz_answered"] == 4
    total_xp = sum(src.ledger.daily_totals(week, week + timedelta(days=6)).values())   # XP của cả 2 con
    assert payloads["bin"]["coach_xp"] + payloads["an"]["coach_xp"] == total_xp   # chia đúng phần từng con
    assert 0 < payloads["bin"]["coach_xp"] < total_xp and 0 < payloads["an"]["coach_xp"] < total_xp


# ---- M5: `data` của learning không lẫn việc/focus công việc ----
def test_learning_data_stat_excludes_work_tasks_and_focus(memory_engine):
    registry = fake_registry(("work", "work", None), ("thcs", "coach", "bin"))
    src = make_sources(memory_engine)
    sender = GrowthReportOutboxSender(src, registry, FakePool({"work": "c1", "thcs": "c2"}, {}),
                                      now=lambda: NOW, local_today=lambda: TODAY)
    seed_study_day(src, YESTERDAY, "thcs")           # 2 sai + 1 đúng → pts = 2 + 2 = 4 → data = 10
    for i in range(5):
        src.ledger.add(f"task_done:t{i}:1", local_noon(YESTERDAY), "work", "work", "task_done")
    start = datetime.combine(YESTERDAY, time(9)).astimezone(timezone.utc)
    with Session(memory_engine) as s:
        s.add(FocusSession(actual_minutes=120, focus_rating=5, started_at=start, ended_at=start + timedelta(minutes=120)))
        s.commit()
    learning = next(t for t in sender.targets() if t.report_kind == "learning")
    agg = collect_day(sender._sources_for(learning), YESTERDAY, sender._learn)
    assert (agg.signals.tasks_done, agg.signals.focus_minutes) == (0, 0)
    assert compute_day_stats(agg.signals).data == 10                     # chỉ quiz: không +10 (task) / +12 (focus)
    general = collect_day(src, YESTERDAY, sender._learn)                 # báo cáo general vẫn thấy việc/focus
    assert general.signals.tasks_done == 5 and general.signals.focus_minutes == 120
    assert agg.stats.data < general.stats.data


# ---- H3: single-instance ----
def test_second_instance_exits_and_first_is_asked_to_show(tmp_path, monkeypatch):
    monkeypatch.delenv(ALLOW_MULTIPLE_ENV, raising=False)
    app = get_qapp()
    first = acquire_single_instance(tmp_path)
    assert first is not None
    shown = []
    first.on_activate = lambda: shown.append(1)
    assert acquire_single_instance(tmp_path) is None             # bản thứ hai bị chặn
    for _ in range(20):                                          # bản đầu nhận tín hiệu "show"
        app.processEvents()
        if shown:
            break
    assert shown
    first.release()                                              # nhả khóa (vd. trước relaunch) → bản mới lấy được
    again = acquire_single_instance(tmp_path)
    assert again is not None
    again.release()


def test_single_instance_env_flag_disables_guard(tmp_path, monkeypatch):
    get_qapp()
    monkeypatch.setenv(ALLOW_MULTIPLE_ENV, "1")
    a, b = acquire_single_instance(tmp_path), acquire_single_instance(tmp_path)
    assert a is not None and b is not None


# ---- M1: Hub hỏng giữa chừng phải bị stop ----
def test_half_started_hub_is_stopped_and_cleared(monkeypatch):
    from src.core.gamification import gamification_hub_service, growth_report_outbox_wiring
    from src.core.gamification.gamification_hub_startup import start_gamification_hub

    events = []

    class FakeHub:
        def __init__(self, ctx, engine):
            pass

        def start(self):
            events.append("start")

        def stop(self):
            events.append("stop")

    def boom(_ctx):
        raise RuntimeError("outbox hỏng")

    monkeypatch.setattr(gamification_hub_service, "GamificationHubService", FakeHub)
    monkeypatch.setattr(growth_report_outbox_wiring, "attach_growth_report_outbox", boom)
    ctx = SimpleNamespace(gamification=None, dashboard=SimpleNamespace(bind_gamification=lambda hub: None))
    start_gamification_hub(ctx, object())
    assert events == ["start", "stop"] and ctx.gamification is None


# ---- M2: huy hiệu sức khỏe theo ngày chỉ chấm ngày đã kết thúc ----
def test_day_wellbeing_badges_wait_for_day_to_finish(memory_engine):
    ledger, wellbeing = XpLedgerRepository(memory_engine), WellbeingDailyRepository(memory_engine)
    from src.core.gamification.badge_unlock_repository import BadgeUnlockRepository
    unlocks = BadgeUnlockRepository(memory_engine)
    svc = BadgeUnlockService(memory_engine, ledger, wellbeing, unlocks)
    wellbeing.add_away(TODAY, 300)                    # sáng sớm: toàn "vắng mặt", app_on ~0 → Health ≈ 90
    svc.refresh(TODAY)
    assert not {"balanced_day", "away_day", "full_rest_day"} & unlocks.ids_for_week("2026-10-19")
    svc.refresh(TODAY + timedelta(days=1))            # sang ngày sau: ngày đó đã kết thúc → mới được chấm
    assert {"balanced_day", "away_day", "full_rest_day"} <= unlocks.ids_for_week("2026-10-19")


# ---- M3: họp trùng giữa lịch và phiên Ted chỉ tính 1 lần ----
def _calendar_event(engine, day: date, hour: int, minutes: int) -> None:
    from src.engines.work.calendar_event_cache_model_and_repository import CalendarEventCache
    start = datetime.combine(day, time(hour)).astimezone(timezone.utc)
    with Session(engine) as s:
        s.add(CalendarEventCache(key=f"ev|{hour}", title="Họp", start_at=start,
                                 end_at=start + timedelta(minutes=minutes), fetched_at=NOW))
        s.commit()


def _ted_meeting(engine, day: date, hour: int, minute: int, minutes: int) -> None:
    start = datetime.combine(day, time(hour, minute)).astimezone(timezone.utc)
    with Session(engine) as s:
        s.add(MeetingSession(kind="team_meeting", started_at=start, ended_at=start + timedelta(minutes=minutes),
                             actual_minutes=minutes))
        s.commit()


@pytest.mark.parametrize("minute,minutes,expect_calendar", [(0, 60, 0), (30, 30, 30), (0, 20, 40)])
def test_calendar_minutes_overlapping_ted_meeting_counted_once(memory_engine, minute, minutes, expect_calendar):
    day = date(2026, 10, 21)   # thứ Tư, 10:00–11:00 là giờ làm việc
    _calendar_event(memory_engine, day, 10, 60)
    _ted_meeting(memory_engine, day, 10, minute, minutes)
    sig = collect_day_signals(memory_engine, XpLedgerRepository(memory_engine),
                              WellbeingDailyRepository(memory_engine), day)
    assert sig.meeting_session_minutes == minutes
    assert sig.work_meeting_minutes == expect_calendar


def test_calendar_event_without_ted_meeting_still_counts_fully(memory_engine):
    day = date(2026, 10, 21)
    _calendar_event(memory_engine, day, 10, 60)
    sig = collect_day_signals(memory_engine, XpLedgerRepository(memory_engine),
                              WellbeingDailyRepository(memory_engine), day)
    assert sig.work_meeting_minutes == 60 and sig.meeting_session_minutes == 0


# ---- M6: {"error": "no_suggestion"} là fallback sạch, không retry trong ngân sách 3 giây ----
def test_no_suggestion_reply_falls_back_without_retry():
    calls = []

    class Client:
        async def complete_text(self, messages, timeout=None):
            calls.append(messages)
            return '<json>{"error": "no_suggestion"}</json>'

    ctx = HealthBreakContext(25, 0, 0, None, None, 14, 60)
    assert asyncio.run(fetch_hermes_suggestion(Client(), ctx)) is None
    assert len(calls) == 1


def test_stopped_hub_ignores_late_focus_signals(memory_engine):
    """Hub đã stop() (vd. khởi động hỏng giữa chừng) không được tự refresh khi tín hiệu focus còn nối."""
    from PySide6.QtCore import QObject, Signal
    from src.core.app_state_key_value_store import KeyValueStore
    from src.core.gamification.gamification_hub_service import GamificationHubService
    get_qapp()

    class _Focus(QObject):
        session_completed = Signal(str, int, int)
        tasks_updated = Signal()
        state_changed = Signal(str, str)
        meeting_completed = Signal(str, int)

    focus = _Focus()
    ctx = SimpleNamespace(kv=KeyValueStore(memory_engine), focus_engine=focus, registry=None,
                          bubble=SimpleNamespace(is_busy=lambda: False, show_message=lambda *a, **k: None))
    hub = GamificationHubService(ctx, memory_engine, skins=[])
    hub.start()
    hub.stop()
    focus.tasks_updated.emit()
    assert not hub._debounce.isActive()
