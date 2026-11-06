"""Phase 01 gamification: sổ cái XP (dedupe, trần ngày, thu hồi task, truy vấn tổng hợp)."""

from datetime import date, datetime, timezone

import pytest
from sqlmodel import SQLModel

from src.core.gamification.gamification_table_models import (
    BadgeUnlock, DailyWellbeing, WeeklySnapshot, XpEvent,
)
from src.core.gamification.xp_ledger_repository import XpLedgerRepository, local_date_of

TS = datetime(2026, 10, 21, 5, 0, tzinfo=timezone.utc)


@pytest.fixture
def ledger(memory_engine):
    return XpLedgerRepository(memory_engine)


def test_memory_engine_creates_four_gamification_tables(memory_engine):
    names = set(SQLModel.metadata.tables)
    assert {"xpevent", "dailywellbeing", "weeklysnapshot", "badgeunlock"} <= names
    assert all(m.__table__.name in names for m in (XpEvent, DailyWellbeing, WeeklySnapshot, BadgeUnlock))


def test_add_is_idempotent(ledger):
    first = ledger.add("k1", TS, "work", "work", "task_done", {"category": "deep_work"})
    assert first is not None and first.xp == 15
    assert ledger.add("k1", TS, "work", "work", "task_done") is None
    assert ledger.has_key("k1") and not ledger.has_key("zzz")
    assert ledger.lifetime_counts()["task_done"] == 1


def test_daily_cap_clamps_then_stores_zero_xp_event(ledger):
    # break_taken cap 18 XP/ngày: 6 lần × 3 chạm trần → các lần sau xp=0 nhưng vẫn lưu (giữ dedupe)
    xps = [ledger.add(f"b{i}", TS, "core", "core", "break_taken").xp for i in range(8)]
    assert xps == [3] * 6 + [0, 0]
    assert ledger.add("b0", TS, "core", "core", "break_taken") is None
    day = local_date_of(TS)
    assert ledger.daily_totals(day, day)[day] == 18
    assert ledger.lifetime_counts()["break_taken"] == 8


def test_task_undo_redo_generations_and_negative_bypasses_cap(ledger):
    assert ledger.task_net_xp("T") == (0, 0)
    ledger.add("task_done:T:1", TS, "work", "work", "task_done")
    assert ledger.task_net_xp("T") == (15, 1)
    ledger.add("task_undone:T:1", TS, "work", "work", "task_undone", xp=-15)
    assert ledger.task_net_xp("T") == (0, 1)
    ledger.add("task_done:T:2", TS, "work", "work", "task_done")
    assert ledger.task_net_xp("T") == (15, 2)
    assert ledger.task_net_xp("OTHER") == (0, 0)


def test_totals_counts_and_first_date(ledger):
    assert ledger.first_event_date() is None
    ledger.add("a", TS, "work", "work", "task_done")
    ledger.add("b", TS, "work", "work", "task_undone", xp=-15)
    ledger.add("c", TS, "coach", "coach", "agenda_done")
    day = local_date_of(TS)
    assert ledger.daily_totals(day, day) == {day: 20}
    assert ledger.kind_counts_by_day(day, day)[day]["task_done"] == 1
    assert ledger.first_event_date() == day
    assert ledger.daily_totals(date(2020, 1, 1), date(2020, 1, 2)) == {}
