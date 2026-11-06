"""Nộp bài viết: lưu trước khi gọi mạng, chấm được, rác 2 lần / offline → giữ bài chưa chấm, chấm lại được."""

import json
import re

import httpx
from coach_ui_test_support import hermes_client, make_services

from src.engines.coach.writing_submission_service import WritingSubmissionService

GRADED = json.dumps({"topic": "hsk.writing", "overall": 7.5, "scores": {"grammar": 7}, "estimated_level": "HSK3",
                     "strengths": ["rõ ý"], "errors": [{"original": "a", "fixed": "b", "why": "c"}]})


def _service(engine, replies, calls=None):
    services, _ = make_services(engine, hermes_client(replies, calls))
    return WritingSubmissionService(services), services


async def test_graded_result_saved_and_payload_has_contract_fields(memory_engine):
    calls: list = []
    service, services = _service(memory_engine, [f"<json>{GRADED}</json>"], calls)
    outcome = await service.submit("Tả gia đình", "我的家有四口人。", 12, agenda_id="a7", topic="hsk.writing")
    assert outcome.result.overall == 7.5
    row = services.plans.get_writing_submission(outcome.submission_id)
    assert row.result_json and row.agenda_id == "a7"
    text = calls[0]["messages"][-1]["content"]
    assert text.startswith("[TED_WRITING_SUBMISSION]")
    payload = json.loads(re.search(r"<json>(.*)</json>", text, re.S).group(1))
    assert payload == {"learner": "con", "agenda_id": "a7", "topic": "hsk.writing", "prompt": "Tả gia đình",
                       "text": "我的家有四口人。", "minutes_spent": 12}


async def test_garbage_twice_keeps_ungraded_row(memory_engine):
    calls: list = []
    service, services = _service(memory_engine, ["xin lỗi tôi không biết"], calls)
    outcome = await service.submit("Đề", "Bài làm", 5)
    assert outcome.result is None
    assert len(calls) == 2                                  # request_json retry đúng 1 lần
    row = services.plans.get_writing_submission(outcome.submission_id)
    assert row.text == "Bài làm" and row.result_json == ""
    assert [r.id for r in services.plans.ungraded_submissions(services.module_id)] == [row.id]


async def test_offline_saves_before_network_and_keeps_text(memory_engine):
    service, services = _service(memory_engine, [httpx.ConnectError("down")])
    outcome = await service.submit("Đề", "Bài làm", 5)
    assert outcome.result is None
    assert services.plans.get_writing_submission(outcome.submission_id).text == "Bài làm"


async def test_regrade_after_failure_grades_same_row(memory_engine):
    service, services = _service(memory_engine, [httpx.ConnectError("down"), f"<json>{GRADED}</json>"])
    first = await service.submit("Đề", "Bài làm", 5)
    again = await service.regrade(first.submission_id)
    assert again.submission_id == first.submission_id and again.result.estimated_level == "HSK3"
    assert services.plans.ungraded_submissions(services.module_id) == []
    assert len(services.plans.recent_submissions(services.module_id)) == 1   # không tạo bản ghi mới


async def test_no_client_means_ungraded_without_crash(memory_engine):
    services, _ = make_services(memory_engine, None)
    outcome = await WritingSubmissionService(services).submit("Đề", "Bài", 1)
    assert outcome.result is None
