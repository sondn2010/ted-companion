"""Outbox báo cáo tiến độ: đóng băng ngày đã qua, gửi cũ → mới, lỗi dừng hàng đợi, failed_permanently không chặn đầu hàng."""

import json
import re
from datetime import timedelta

from coach_ui_test_support import LOCAL_NOW, LOCAL_TZ, hermes_client, make_services
from coach_test_support import MODULE, seed

from src.engines.coach.progress_outbox_sender import ProgressOutboxSender

SAVED = '<json>{"saved": true, "path": "reports/progress/con/x.md"}</json>'
NOT_SAVED = '<json>{"saved": false, "error": "disk"}</json>'


def _answer_on(services, item, days_back: int):
    when = (LOCAL_NOW - timedelta(days=days_back)).astimezone(LOCAL_TZ)
    services.attempts.record_answer(MODULE, item.id, "x", True, 30, when, [0.007, 1, 3, 7, 14, 30])


def _sender(engine, replies, calls=None):
    syncs = []
    services, _ctx = make_services(engine, hermes_client(replies, calls))
    return ProgressOutboxSender(services, lambda: syncs.append(1)), services, syncs


def _seed_days(engine, services, days):
    items = seed(engine, [f"Q{d}" for d in days], now=LOCAL_NOW)
    for item, back in zip(items, days):
        _answer_on(services, item, back)


def test_enqueue_freezes_past_days_with_attempts_only(memory_engine):
    sender, services, _ = _sender(memory_engine, [SAVED])
    _seed_days(memory_engine, services, [0, 1, 3, 9])      # hôm nay + quá 7 ngày bị bỏ qua
    assert sender.enqueue_missing() == 2
    dates = [r.date for r in services.outbox.pending_reports(MODULE)]
    assert dates == ["2026-10-16", "2026-10-18"]
    assert sender.enqueue_missing() == 0                   # đã có dòng → không tạo lại


async def test_flush_sends_oldest_first_marks_sent_and_requests_sync(memory_engine):
    calls: list = []
    sender, services, syncs = _sender(memory_engine, [SAVED], calls)
    _seed_days(memory_engine, services, [1, 3])
    sender.enqueue_missing()
    assert await sender.flush() == 2
    sent_dates = [json.loads(re.search(r"<json>(.*)</json>", c["messages"][-1]["content"], re.S).group(1))["date"] for c in calls]
    assert sent_dates == ["2026-10-16", "2026-10-18"]
    assert all("[TED_PROGRESS_REPORT]" in c["messages"][-1]["content"] for c in calls)
    assert services.outbox.get(MODULE, "2026-10-18").sent is True
    assert syncs == [1]                                    # chỉ gọi hook 1 lần sau khi gửi xong


async def test_saved_false_keeps_row_unsent_with_attempt_counted(memory_engine):
    sender, services, syncs = _sender(memory_engine, [NOT_SAVED])
    _seed_days(memory_engine, services, [1])
    sender.enqueue_missing()
    assert await sender.flush() == 0
    row = services.outbox.get(MODULE, "2026-10-18")
    assert (row.sent, row.attempts, row.status, row.last_error) == (False, 1, "pending", "disk")
    assert syncs == []


async def test_failure_on_day_two_stops_day_three(memory_engine):
    calls: list = []
    sender, services, _ = _sender(memory_engine, [SAVED, NOT_SAVED, SAVED], calls)
    _seed_days(memory_engine, services, [1, 2, 3])         # 16, 17, 18 tháng 10
    sender.enqueue_missing()
    assert await sender.flush() == 1
    assert len(calls) == 2                                 # ngày 3 không được thử
    assert services.outbox.get(MODULE, "2026-10-16").sent is True
    assert services.outbox.get(MODULE, "2026-10-17").attempts == 1
    assert services.outbox.get(MODULE, "2026-10-18").attempts == 0


async def test_sent_row_is_never_resent(memory_engine):
    calls: list = []
    sender, services, _ = _sender(memory_engine, [SAVED], calls)
    _seed_days(memory_engine, services, [1])
    sender.enqueue_missing()
    await sender.flush()
    await sender.flush()
    sender.enqueue_missing()
    await sender.flush()
    assert len(calls) == 1


async def test_failed_permanently_does_not_block_following_dates(memory_engine):
    calls: list = []
    sender, services, _ = _sender(memory_engine, [NOT_SAVED, SAVED], calls)
    _seed_days(memory_engine, services, [1, 2])            # 17 (cũ hơn) rồi 18
    sender.enqueue_missing()
    with memory_engine.begin() as conn:
        conn.exec_driver_sql("UPDATE progressreportoutbox SET attempts = 4 WHERE date = '2026-10-17'")
    assert await sender.flush() == 1                       # 17 → 5 lần thất bại = bỏ hẳn; 18 vẫn được gửi
    assert services.outbox.get(MODULE, "2026-10-17").status == "failed_permanently"
    assert services.outbox.get(MODULE, "2026-10-18").sent is True


async def test_offline_does_not_consume_attempts_and_backs_off(memory_engine):
    import httpx

    calls: list = []
    sender, services, _ = _sender(memory_engine, [httpx.ConnectError("down"), SAVED], calls)
    _seed_days(memory_engine, services, [1])
    sender.enqueue_missing()
    assert await sender.flush() == 0
    assert services.outbox.get(MODULE, "2026-10-18").attempts == 0   # không tốn lượt
    assert await sender.flush() == 0 and len(calls) == 1             # đang backoff → không gọi lại
    services._clock = lambda: LOCAL_NOW + timedelta(minutes=6)
    assert await sender.flush() == 1                                 # hết backoff, online lại
    assert services.outbox.get(MODULE, "2026-10-18").sent is True


async def test_garbage_reply_counts_as_real_failure(memory_engine):
    sender, services, _ = _sender(memory_engine, ["không phải json"])
    _seed_days(memory_engine, services, [1])
    sender.enqueue_missing()
    assert await sender.flush() == 0
    assert services.outbox.get(MODULE, "2026-10-18").attempts == 1


def test_enqueue_without_attempts_adds_nothing(memory_engine):
    sender, services, _ = _sender(memory_engine, [SAVED])
    assert sender.enqueue_missing() == 0
