"""Thời điểm nhắc agenda (`when`) và mốc (milestone) — thuần hàm; trạng thái "đã nhắc" do bên gọi giữ (KV)."""

from datetime import date, datetime, time, timedelta
from typing import Collection

from src.engines.coach.coach_sync_plan_schemas import AgendaItem, Milestone

AGENDA_LEAD = timedelta(minutes=5)
AGENDA_GRACE = timedelta(minutes=30)       # quá `when` 30 phút thì thôi không nhắc nữa
MILESTONE_FROM_HOUR = 8


def agenda_reminder_key(day: date, agenda_id: str) -> str:
    return f"agenda:{day.isoformat()}:{agenda_id}"


def milestone_reminder_key(milestone: Milestone, days: int) -> str:
    return f"milestone:{milestone.id}:{milestone.due_date.isoformat()}:{days}"


def _when_at(day: date, when: str, tzinfo) -> datetime:
    hour, minute = when.split(":")
    return datetime.combine(day, time(int(hour), int(minute)), tzinfo=tzinfo)


def due_agenda_reminders(
    agenda: list[AgendaItem], now: datetime, done_ids: Collection[str], reminded: Collection[str],
) -> list[AgendaItem]:
    """Mục chưa xong, có `when` trong [when-5', when+30'], chưa nhắc hôm nay."""
    today = now.date()
    due = []
    for item in agenda:
        if not item.when or item.id in done_ids or agenda_reminder_key(today, item.id) in reminded:
            continue
        at = _when_at(today, item.when, now.tzinfo)
        if at - AGENDA_LEAD <= now <= at + AGENDA_GRACE:
            due.append(item)
    return due


def due_milestone_reminders(
    milestones: list[Milestone], now: datetime, fired: Collection[str],
) -> list[tuple[Milestone, int, str]]:
    """(milestone, số ngày còn lại, key) cần nhắc: từ 08:00 địa phương, đúng số ngày trong remind_before_days."""
    if now.hour < MILESTONE_FROM_HOUR:
        return []
    today = now.date()
    due = []
    for milestone in milestones:
        days = (milestone.due_date - today).days
        key = milestone_reminder_key(milestone, days)
        if days in milestone.remind_before_days and key not in fired:
            due.append((milestone, days, key))
    return due


def milestone_text(milestone: Milestone, days: int) -> str:
    when = "Hôm nay" if days == 0 else f"Còn {days} ngày"
    return f"🗓️ {when}: {milestone.title} ({milestone.due_date:%d/%m/%Y})"


def agenda_text(item: AgendaItem) -> str:
    return f"⏰ {item.when}: {item.title}" + (f" ({item.minutes}')" if item.minutes else "")
