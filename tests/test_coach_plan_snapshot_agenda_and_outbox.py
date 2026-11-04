from datetime import timedelta

import pytest

from src.engines.coach.coach_plan_snapshot_repository import CoachPlanRepository
from src.engines.coach.coach_policy_clamp import DEFAULT_POLICY
from src.engines.coach.coach_progress_report_outbox import ProgressReportOutboxRepository, validate_report_date
from src.engines.coach.coach_quiz_writing_report_schemas import WritingGradeResult
from src.engines.coach.coach_sync_plan_schemas import SyncPlanPayload
from coach_test_support import MODULE, NOW

POLICY = {"review_interval_mins": 30, "daily_cap": 99, "new_per_day": 5, "leitner_days": [0.01, 1, 2, 4, 8, 16]}


def _payload(**extra):
    return SyncPlanPayload.model_validate({"agenda": [{"id": "a1", "kind": "quiz", "title": "t"}], **extra})


def test_snapshot_absent_then_saved_and_policy_clamped(memory_engine):
    repo = CoachPlanRepository(memory_engine)
    assert repo.get_snapshot(MODULE) is None and repo.current_policy(MODULE) == DEFAULT_POLICY
    saved = repo.save_sync(MODULE, _payload(policy=POLICY), NOW)
    assert saved.policy.daily_cap == 40
    loaded = repo.get_snapshot(MODULE)
    assert loaded.agenda[0].id == "a1" and loaded.policy.daily_cap == 40
    assert repo.get_synced_at(MODULE) == NOW and repo.current_policy(MODULE).review_interval_mins == 30


def test_sync_without_valid_policy_keeps_previous_policy(memory_engine):
    repo = CoachPlanRepository(memory_engine)
    repo.save_sync(MODULE, _payload(policy=POLICY), NOW)
    broken = _payload(policy={**POLICY, "leitner_days": [1, 2]})   # sai cấu trúc → None
    repo.save_sync(MODULE, broken, NOW + timedelta(hours=1))
    assert repo.current_policy(MODULE).review_interval_mins == 30
    repo.save_sync(MODULE, _payload(), NOW + timedelta(hours=2))   # không có policy
    assert repo.current_policy(MODULE).review_interval_mins == 30


def test_snapshot_replaced_wholesale_per_module(memory_engine):
    repo = CoachPlanRepository(memory_engine)
    repo.save_sync(MODULE, _payload(), NOW)
    repo.save_sync("caohoc", SyncPlanPayload(), NOW)
    repo.save_sync(MODULE, SyncPlanPayload.model_validate({"agenda": []}), NOW + timedelta(days=1))
    assert repo.get_snapshot(MODULE).agenda == [] and repo.get_snapshot("caohoc") is not None


def test_corrupt_snapshot_returns_none(memory_engine):
    from src.engines.coach.coach_data_models import PlanSnapshot, open_session
    with open_session(memory_engine) as s:
        s.add(PlanSnapshot(module_id=MODULE, synced_at=NOW, payload_json='{"agenda": "oops"}'))
        s.commit()
    assert CoachPlanRepository(memory_engine).get_snapshot(MODULE) is None


def test_agenda_done_is_idempotent_and_keeps_first_timestamp(memory_engine):
    repo = CoachPlanRepository(memory_engine)
    assert repo.mark_done(MODULE, "a1", NOW) is True
    assert repo.mark_done(MODULE, "a1", NOW + timedelta(hours=3)) is False
    assert repo.done_ids(MODULE) == {"a1"} and repo.unreported_done_ids(MODULE) == ["a1"]


def test_inflight_sync_does_not_lose_item_completed_during_flight(memory_engine):
    """Red Team #8: a2 xong sau khi request sync đã gửi đi → không được đánh dấu đã báo."""
    repo = CoachPlanRepository(memory_engine)
    repo.mark_done(MODULE, "a1", NOW)
    sent_ids = repo.unreported_done_ids(MODULE)           # request đi với done_today=[a1]
    repo.mark_done(MODULE, "a2", NOW + timedelta(seconds=5))   # tick trong lúc đang chờ Hermes
    repo.save_sync(MODULE, _payload(), NOW + timedelta(seconds=9), reported_ids=sent_ids)
    assert repo.unreported_done_ids(MODULE) == ["a2"]


def test_failed_sync_leaves_done_items_unreported(memory_engine):
    repo = CoachPlanRepository(memory_engine)
    repo.mark_done(MODULE, "a1", NOW)
    assert repo.unreported_done_ids(MODULE) == ["a1"]   # chưa gọi save_sync → vẫn sẽ gửi lại lần sau


def test_writing_submission_lifecycle(memory_engine):
    repo = CoachPlanRepository(memory_engine)
    sub = repo.add_writing_submission(MODULE, "đề", "bài viết", NOW, agenda_id="a3", topic="van.nghi-luan")
    assert [s.id for s in repo.ungraded_submissions(MODULE)] == [sub.id]
    assert repo.save_writing_result(sub.id, WritingGradeResult(overall=7.5)) is True
    assert repo.ungraded_submissions(MODULE) == []
    assert WritingGradeResult.model_validate_json(repo.get_writing_submission(sub.id).result_json).overall == 7.5
    assert repo.save_writing_result("ghost", WritingGradeResult(overall=1)) is False


# ---- outbox ----
@pytest.mark.parametrize("bad", ["2026-1-5", "../../etc/passwd", "2026-10-19\n", "2026-13-45", "", "２０２６-10-19", "2026-10-19/x"])
def test_outbox_rejects_bad_dates(memory_engine, bad):
    with pytest.raises(ValueError):
        ProgressReportOutboxRepository(memory_engine).upsert_report(MODULE, bad, {}, NOW)
    with pytest.raises(ValueError):
        validate_report_date(bad)


def test_outbox_upsert_replaces_pending_but_never_overwrites_sent(memory_engine):
    box = ProgressReportOutboxRepository(memory_engine)
    assert box.upsert_report(MODULE, "2026-10-19", {"v": 1}, NOW) is True
    assert box.upsert_report(MODULE, "2026-10-19", {"v": 2}, NOW) is True
    assert '"v": 2' in box.get(MODULE, "2026-10-19").payload_json
    box.mark_sent(MODULE, "2026-10-19", NOW)
    assert box.upsert_report(MODULE, "2026-10-19", {"v": 3}, NOW) is False
    row = box.get(MODULE, "2026-10-19")
    assert row.sent is True and row.status == "sent" and '"v": 2' in row.payload_json
    assert box.pending_reports(MODULE) == []


def test_outbox_head_of_line_poison_message_does_not_block_others(memory_engine):
    box = ProgressReportOutboxRepository(memory_engine)
    box.upsert_report(MODULE, "2026-10-17", {"d": 17}, NOW)
    box.upsert_report(MODULE, "2026-10-18", {"d": 18}, NOW)
    statuses = [box.mark_failed(MODULE, "2026-10-17", "Hermes 500", NOW) for _ in range(5)]
    assert statuses[:4] == ["pending"] * 4 and statuses[4] == "failed_permanently"
    assert [r.date for r in box.pending_reports(MODULE)] == ["2026-10-18"]   # ngày xấu không chặn đầu hàng
    assert box.get(MODULE, "2026-10-17").last_error == "Hermes 500"


def test_outbox_pending_ordered_oldest_first_and_per_module(memory_engine):
    box = ProgressReportOutboxRepository(memory_engine)
    for day in ("2026-10-19", "2026-10-17", "2026-10-18"):
        box.upsert_report(MODULE, day, {}, NOW)
    box.upsert_report("caohoc", "2026-10-01", {}, NOW)
    assert [r.date for r in box.pending_reports(MODULE)] == ["2026-10-17", "2026-10-18", "2026-10-19"]


def test_outbox_resubmitting_failed_day_resets_attempts(memory_engine):
    box = ProgressReportOutboxRepository(memory_engine)
    box.upsert_report(MODULE, "2026-10-19", {"v": 1}, NOW)
    for _ in range(5):
        box.mark_failed(MODULE, "2026-10-19", "x", NOW)
    assert box.upsert_report(MODULE, "2026-10-19", {"v": 2}, NOW) is True
    row = box.get(MODULE, "2026-10-19")
    assert row.status == "pending" and row.attempts == 0
    assert box.mark_failed(MODULE, "2026-12-31", "x", NOW) == ""
