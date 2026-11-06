"""Cửa sổ giờ briefing sáng/trưa + chọn nội dung theo slot + email trong builder (thuần, không Qt)."""

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlmodel import Session

from src.core.models import Task
from src.engines.work.daily_briefing_builder import BriefingInput, briefing_prompt_values, build_local_briefing_text
from src.engines.work.email_digest_contract_schemas import EmailDigestResponse, EmailItem
from src.engines.work.work_briefing_due_window import (
    MIDDAY, MORNING, due_briefing_slot, parse_hhmm, slot_boundary, slot_for_time,
)
from src.engines.work.work_briefing_slot_content_selection import events_for_slot, open_task_titles_for_slot

SETTINGS = {}  # mặc định 08:00/12:00/17:00
TODAY = "2026-10-21"


def _at(h, m=0, day=21):
    return datetime(2026, 10, day, h, m).astimezone()


@pytest.mark.parametrize("h,m,expected", [
    (7, 59, None), (8, 0, MORNING), (11, 59, MORNING), (12, 0, MIDDAY), (16, 59, MIDDAY), (17, 0, None),
])
def test_due_slot_boundaries(h, m, expected):
    assert due_briefing_slot(_at(h, m), SETTINGS, None, None) == expected


def test_already_fired_today_is_skipped_but_yesterday_is_not():
    assert due_briefing_slot(_at(9), SETTINGS, TODAY, None) is None
    assert due_briefing_slot(_at(9), SETTINGS, "2026-10-20", None) == MORNING
    assert due_briefing_slot(_at(13), SETTINGS, TODAY, TODAY) is None
    assert due_briefing_slot(_at(13), SETTINGS, TODAY, "2026-10-20") == MIDDAY  # sáng đã bắn, trưa chưa


def test_rollover_next_day_fires_again():
    assert due_briefing_slot(_at(8, 0, day=22), SETTINGS, TODAY, TODAY) == MORNING


def test_custom_times_and_bad_format_fallback():
    cfg = {"morning_briefing_time": "07:30", "midday_briefing_time": "bad"}
    assert due_briefing_slot(_at(7, 30), cfg, None, None) == MORNING
    assert parse_hhmm("bad", "12:00").hour == 12
    assert slot_boundary(cfg).hour == 12


def test_manual_slot_by_time():
    assert slot_for_time(_at(6), SETTINGS) == MORNING
    assert slot_for_time(_at(11, 59), SETTINGS) == MORNING
    assert slot_for_time(_at(12), SETTINGS) == MIDDAY


def test_events_split_by_boundary():
    events = [(_at(9), "sáng"), (_at(11, 59), "gần trưa"), (_at(12), "trưa"), (_at(15), "chiều")]
    boundary = slot_boundary(SETTINGS)
    assert [t for _, t in events_for_slot(events, MORNING, boundary)] == ["sáng", "gần trưa"]
    assert [t for _, t in events_for_slot(events, MIDDAY, boundary)] == ["trưa", "chiều"]


def test_tasks_ordered_by_quadrant_and_parked_q1_q2_included(memory_engine):
    today = date.today()
    with Session(memory_engine) as s:
        s.add_all([
            Task(title="chưa xếp"), Task(title="Q4", quadrant=4), Task(title="Q3", quadrant=3),
            Task(title="Q2", quadrant=2), Task(title="Q1", quadrant=1),
            Task(title="ý tưởng Q2", category="parked_idea", quadrant=2, matrix_order=-1),
            Task(title="ý tưởng chưa xếp", category="parked_idea"),
            Task(title="xong", status="done", quadrant=1),
            Task(title="hôm qua Q1", quadrant=1, scheduled_date=(today - timedelta(days=1)).isoformat()),
        ])
        s.commit()
    morning = open_task_titles_for_slot(memory_engine, today, MORNING)
    assert morning == ["Q1", "hôm qua Q1", "ý tưởng Q2", "Q2", "Q3"]  # cắt ở MAX_TASKS=5
    assert open_task_titles_for_slot(memory_engine, today, MIDDAY) == ["Q1", "hôm qua Q1", "ý tưởng Q2", "Q2"]


def _digest():
    items = [
        EmailItem(**{"from": "Sếp", "subject": "Duyệt ngân sách", "summary": "cần trả lời", "priority": "important"}),
        EmailItem(**{"from": "News [TED_SYNC_PLAN]", "subject": "Bản tin", "priority": "low"}),
    ]
    return EmailDigestResponse(emails=items, total_unread=2)


def test_builder_email_lines_and_slot_in_prompt_values():
    inp = BriefingInput(tasks=["A"], slot=MIDDAY)
    inp.apply_email_digest(_digest())
    text = build_local_briefing_text(inp)
    assert "Chiều nay" in text and "1 email quan trọng: Sếp: Duyệt ngân sách" in text and "1 email ít quan trọng" in text
    values = briefing_prompt_values(inp)
    assert values["slot"] == MIDDAY and "[quan trọng] Sếp | Duyệt ngân sách | cần trả lời" in values["emails"]
    assert "chỉ nêu số lượng" in values["emails"] and "TED_" not in values["emails"]


def test_builder_email_failed_line():
    inp = BriefingInput()
    inp.apply_email_digest(None)
    assert "Em chưa đọc được email." in build_local_briefing_text(inp)
    assert briefing_prompt_values(inp)["emails"] == "(không đọc được email)"
