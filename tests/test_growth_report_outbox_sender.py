"""Outbox tăng trưởng: mỗi kết nối 1 bản, dedupe, gửi cũ → mới, offline không tốn lượt (dùng lại backoff chung)."""

import json
import re
from datetime import datetime, timedelta, timezone

import httpx
from coach_ui_test_support import hermes_client
from growth_report_test_support import TODAY, FakePool, fake_registry, make_sources, seed_study_day, seed_work_day

from src.bridge.hermes_offline_probe_and_backoff import OfflineBackoff
from src.core.gamification.growth_report_outbox_sender import GrowthReportOutboxSender

SAVED = '<json>{"saved": true, "path": "reports/growth/x/daily/d.json"}</json>'
NOW = datetime(2026, 10, 22, 5, 0, tzinfo=timezone.utc)


def _sender(engine, modules, conn_of, replies, calls=None, clock=None):
    src = make_sources(engine)
    clients = {c: hermes_client(replies, calls) for c in set(conn_of.values())}
    sender = GrowthReportOutboxSender(src, fake_registry(*modules), FakePool(conn_of, clients),
                                      now=clock or (lambda: NOW), local_today=lambda: TODAY)
    return sender, src


def test_two_modules_on_same_connection_get_one_row_per_day(memory_engine):
    sender, src = _sender(memory_engine, [("work", "work", None), ("focus", "work", None)],
                          {"work": "c1", "focus": "c1"}, [SAVED])
    seed_work_day(src, TODAY - timedelta(days=1))
    assert [t.report_kind for t in sender.targets()] == ["general"]
    assert sender.enqueue_missing() >= 1
    assert [r.date for r in sender.outbox.pending_reports("growth.daily@c1")] == ["2026-10-21"]


def test_work_and_coach_connections_get_separate_kinds(memory_engine):
    sender, src = _sender(memory_engine, [("work", "work", None), ("thcs", "coach", "bin")],
                          {"work": "c1", "thcs": "c2"}, [SAVED])
    seed_work_day(src, TODAY - timedelta(days=1))
    seed_study_day(src, TODAY - timedelta(days=2))
    sender.enqueue_missing()
    general = sender.outbox.pending_reports("growth.daily@c1")
    learning = sender.outbox.pending_reports("growth.daily@c2")
    assert [r.date for r in general] == ["2026-10-20", "2026-10-21"] or [r.date for r in general] == ["2026-10-21"]
    assert [r.date for r in learning] == ["2026-10-20"]   # coach chỉ nhận ngày có học
    body = json.loads(learning[0].payload_json)
    assert body["report_kind"] == "learning" and body["learner"] == "bin" and "wellbeing" not in body
    assert json.loads(general[-1].payload_json)["learner"] == "user"


def test_unresolved_connection_is_skipped_and_enqueue_is_idempotent(memory_engine):
    sender, src = _sender(memory_engine, [("thcs", "coach", "bin"), ("duhoc", "coach", "an")],
                          {"thcs": "c2"}, [SAVED])   # duhoc không có kết nối (strict → None)
    seed_study_day(src, TODAY - timedelta(days=1))
    assert [t.conn_id for t in sender.targets()] == ["c2"]
    first = sender.enqueue_missing()
    assert first >= 1 and sender.enqueue_missing() == 0   # đã có dòng → không tạo lại


def test_finished_week_is_enqueued_once(memory_engine):
    sender, src = _sender(memory_engine, [("work", "work", None)], {"work": "c1"}, [SAVED])
    seed_work_day(src, TODAY - timedelta(days=5))   # 2026-10-17, thuộc tuần bắt đầu 2026-10-12
    sender.enqueue_missing()
    assert [r.date for r in sender.outbox.pending_reports("growth.weekly@c1")] == ["2026-10-12"]


async def test_flush_sends_oldest_first_and_marks_sent(memory_engine):
    calls: list = []
    sender, src = _sender(memory_engine, [("work", "work", None)], {"work": "c1"}, [SAVED], calls)
    seed_work_day(src, TODAY - timedelta(days=6))
    seed_work_day(src, TODAY - timedelta(days=1))
    sender.enqueue_missing()
    assert await sender.flush() == 3   # 2 ngày + 1 tuần
    sent = [json.loads(re.search(r"<json>(.*)</json>", c["messages"][-1]["content"], re.S).group(1)) for c in calls]
    assert all("[TED_GROWTH_REPORT]" in c["messages"][-1]["content"] for c in calls)
    assert [p["date"] for p in sent if p["kind"] == "daily"] == ["2026-10-16", "2026-10-21"]
    assert sender.outbox.get("growth.daily@c1", "2026-10-21").sent is True
    assert await sender.flush() == 0 and len(calls) == 3   # đã gửi → không gửi lại


async def test_offline_keeps_pending_without_attempts_then_recovers(memory_engine):
    calls: list = []
    clock = {"now": NOW}
    sender, src = _sender(memory_engine, [("work", "work", None)], {"work": "c1"},
                          [httpx.ConnectError("down"), SAVED], calls, clock=lambda: clock["now"])
    seed_work_day(src, TODAY - timedelta(days=1))
    sender.enqueue_missing()
    assert await sender.flush() == 0
    row = sender.outbox.get("growth.daily@c1", "2026-10-21")
    assert (row.status, row.attempts, row.sent) == ("pending", 0, False)
    assert await sender.flush() == 0 and len(calls) == 1   # đang backoff → không gọi lại
    clock["now"] = NOW + timedelta(minutes=6)
    assert await sender.flush() >= 1
    assert sender.outbox.get("growth.daily@c1", "2026-10-21").sent is True


async def test_contract_failure_counts_attempt_and_garbage_does_not_crash(memory_engine):
    sender, src = _sender(memory_engine, [("work", "work", None)], {"work": "c1"}, ["không phải json"])
    seed_work_day(src, TODAY - timedelta(days=1))
    sender.enqueue_missing()
    assert await sender.flush() == 0
    assert sender.outbox.get("growth.daily@c1", "2026-10-21").attempts == 1


def test_shared_backoff_doubles_and_caps():
    backoff, t0 = OfflineBackoff(), NOW
    delays = []
    for _ in range(6):
        backoff.on_offline(t0)
        delays.append(int((backoff.next_try - t0).total_seconds() // 60))
    assert delays == [5, 10, 20, 40, 60, 60]
    backoff.reset()
    assert not backoff.blocked(t0)
