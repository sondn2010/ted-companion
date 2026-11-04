"""Unit tests cho ActivityOutboxSender & luồng Báo cáo Cuối ngày."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock
import pytest
from sqlmodel import SQLModel, create_engine

from src.core.activity_watcher.activity_daily_repository import ActivityDailyRepository
from src.core.activity_watcher.activity_outbox_sender import ActivityOutboxSender
from src.core.activity_watcher.activity_table_models import DailyActivityRecord


@pytest.fixture
def test_db_engine():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    return engine


def test_end_of_day_summary_text_generation(test_db_engine):
    repo = ActivityDailyRepository(test_db_engine)
    rec = repo.get_or_create("2026-10-22", "uyen")
    rec.study_seconds = 5100       # 85 phút
    rec.distraction_seconds = 900  # 15 phút
    rec.self_corrected_count = 2
    rec.top_apps_json = json.dumps({"Microsoft Word": 3000, "TikTok": 900})
    with repo._engine.connect() as conn:
        with repo._engine.begin() as tx:
            from sqlmodel import Session
            with Session(repo._engine) as s:
                s.add(rec)
                s.commit()

    sender = ActivityOutboxSender(
        repository=repo,
        client_pool=None,
        registry=None,
        today_fn=lambda: "2026-10-22",
        learner_fn=lambda: "uyen",
    )

    text = sender.get_end_of_day_summary_text(display_name="Uyên")
    assert "Tổng kết buổi tối cùng Uyên" in text
    assert "85.0 phút" in text
    assert "15.0 phút" in text
    assert "2 lần tự giác" in text
    assert "ngủ thật ngon" in text


@pytest.mark.asyncio
async def test_send_daily_report_async_success(test_db_engine):
    repo = ActivityDailyRepository(test_db_engine)
    rec = repo.get_or_create("2026-10-22", "uyen")
    rec.study_seconds = 3600
    rec.distraction_seconds = 600
    from sqlmodel import Session
    with Session(repo._engine) as s:
        s.add(rec)
        s.commit()

    # Mock client pool & client
    mock_client = MagicMock()
    mock_client.chat_completion = AsyncMock(return_value='{"saved": true}')

    mock_pool = MagicMock()
    mock_pool.default_connection_id.return_value = "conn-coach"
    mock_pool.get.return_value = mock_client

    mock_registry = MagicMock()
    mock_registry.active.return_value = None

    sender = ActivityOutboxSender(
        repository=repo,
        client_pool=mock_pool,
        registry=mock_registry,
        today_fn=lambda: "2026-10-22",
        learner_fn=lambda: "uyen",
    )

    sent = await sender.send_daily_report_async("2026-10-22")
    assert sent is True
    assert mock_client.chat_completion.called

    # Check payload sent
    call_args = mock_client.chat_completion.call_args[0][0]
    prompt = call_args[0]["content"]
    assert prompt.startswith("[TED_ACTIVITY_REPORT]\n<json>")
    assert '"learner": "uyen"' in prompt
    assert '"study_minutes": 60.0' in prompt

    # Verify synced_to_hermes updated
    updated_rec = repo.get_or_create("2026-10-22", "uyen")
    assert updated_rec.synced_to_hermes is True


@pytest.mark.asyncio
async def test_send_daily_report_skips_when_empty(test_db_engine):
    repo = ActivityDailyRepository(test_db_engine)
    mock_pool = MagicMock()

    sender = ActivityOutboxSender(
        repository=repo,
        client_pool=mock_pool,
        registry=None,
        today_fn=lambda: "2026-10-22",
        learner_fn=lambda: "uyen",
    )

    sent = await sender.send_daily_report_async("2026-10-22")
    assert sent is False
    assert not mock_pool.get.called
