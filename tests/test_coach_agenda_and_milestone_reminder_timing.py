"""Thời điểm nhắc agenda `when` và milestone 30/7/1 ngày."""

from datetime import date, datetime, timedelta, timezone

from src.engines.coach.coach_agenda_and_milestone_reminder_timing import (
    agenda_reminder_key,
    agenda_text,
    due_agenda_reminders,
    due_milestone_reminders,
    milestone_text,
)
from src.engines.coach.coach_sync_plan_schemas import AgendaItem, Milestone

TZ = timezone(timedelta(hours=7))


def at(hour, minute=0, day=19) -> datetime:
    return datetime(2026, 10, day, hour, minute, tzinfo=TZ)


def item(id_="a1", when="19:30", **kw) -> AgendaItem:
    return AgendaItem(id=id_, kind="task", title="Ôn câu điều kiện", minutes=15, when=when, **kw)


def test_agenda_fires_five_minutes_before_not_earlier():
    agenda = [item()]
    assert due_agenda_reminders(agenda, at(19, 24), set(), set()) == []
    assert due_agenda_reminders(agenda, at(19, 25), set(), set()) == agenda


def test_agenda_not_again_once_reminded():
    agenda = [item()]
    reminded = {agenda_reminder_key(date(2026, 10, 19), "a1")}
    assert due_agenda_reminders(agenda, at(19, 26), set(), reminded) == []


def test_agenda_done_or_without_when_never_fires():
    assert due_agenda_reminders([item()], at(19, 30), {"a1"}, set()) == []
    assert due_agenda_reminders([item(when=None)], at(19, 30), set(), set()) == []


def test_agenda_retries_until_thirty_minutes_after_when():
    agenda = [item()]
    assert due_agenda_reminders(agenda, at(20, 0), set(), set()) == agenda
    assert due_agenda_reminders(agenda, at(20, 1), set(), set()) == []


def test_agenda_reminder_text():
    assert agenda_text(item()) == "⏰ 19:30: Ôn câu điều kiện (15')"


def ms(due: date, before=(30, 7, 1), id_="m1") -> Milestone:
    return Milestone(id=id_, title="Thi HSK3", due_date=due, remind_before_days=list(before))


def test_milestone_exact_days_only():
    for days, expected in [(30, True), (7, True), (1, True), (6, False), (29, False), (0, False)]:
        due = date(2026, 10, 19) + timedelta(days=days)
        assert bool(due_milestone_reminders([ms(due)], at(9), set())) is expected, days


def test_milestone_first_check_late_in_day_still_fires_but_not_before_eight():
    due = date(2026, 10, 26)
    assert due_milestone_reminders([ms(due)], at(7, 59), set()) == []
    assert len(due_milestone_reminders([ms(due)], at(10), set())) == 1


def test_milestone_fires_once_per_day_via_key():
    due = date(2026, 10, 26)
    (milestone, days, key), = due_milestone_reminders([ms(due)], at(9), set())
    assert days == 7
    assert due_milestone_reminders([ms(due)], at(9, 1), {key}) == []
    # ngày hôm sau (còn 6 ngày) không nằm trong remind_before_days → im lặng
    assert due_milestone_reminders([ms(due)], at(9, day=20), {key}) == []


def test_milestone_text_format():
    assert milestone_text(ms(date(2027, 5, 15)), 7) == "🗓️ Còn 7 ngày: Thi HSK3 (15/05/2027)"
