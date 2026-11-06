"""Hồi quy cho các lỗi từ code review Phase 02/03: lazy import 3.15, config, DB, pool, bubble, tab dashboard, cheer."""

import asyncio
import shutil
from datetime import datetime, timezone
from types import SimpleNamespace

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QTabWidget, QWidget

from tests.qt_offscreen_app_helper import get_qapp

from src.bridge.hermes_client_pool import HermesClientPool
from src.config import AppConfig
from src.core.connection_registry_and_settings_migration import HermesConnection
from src.core.focus_engine import FocusState
from src.core.models import FocusSession, db
from src.modules_runtime.cheer_line_provider import CheerLineProvider
from src.ui.dashboard_window import DashboardWindow
from src.ui.pet_speech_bubble_widget import PetSpeechBubble
from sqlmodel import Session


def test_to_thread_works_after_pyside_import():
    assert asyncio.run(asyncio.to_thread(lambda: 42)) == 42


def test_config_survives_bad_env_ints_and_failed_corrupt_backup(tmp_path, monkeypatch):
    monkeypatch.setenv("DEFAULT_POMODORO_MINUTES", "abc")
    monkeypatch.setenv("MINDFUL_PING_INTERVAL_MINUTES", "")
    (tmp_path / "settings.json").write_text("{không phải json", encoding="utf-8")

    def boom(*_a, **_k):
        raise OSError("disk full")

    monkeypatch.setattr(shutil, "copy2", boom)
    cfg = AppConfig(data_dir=tmp_path)
    assert cfg.default_pomodoro_mins == 25 and cfg.mindful_ping_mins == 15
    assert cfg.connections  # vẫn có kết nối seed


def test_today_analytics_counts_session_by_local_date():
    local_early = datetime.now().astimezone().replace(hour=0, minute=30, second=0, microsecond=0)
    utc_naive = local_early.astimezone(timezone.utc)  # lưu aware UTC; SQLite đọc lại là naive
    fs = FocusSession(started_at=utc_naive, actual_minutes=25)
    fs_id = fs.id  # đọc trước commit: sau commit instance bị detach
    with Session(db.engine) as s:
        s.add(fs)
        s.commit()
    try:
        assert db.get_today_analytics()["completed_sessions"] >= 1
    finally:
        with Session(db.engine) as s:
            s.delete(s.get(FocusSession, fs_id))
            s.commit()


def _two_conn_pool(tmp_path):
    cfg = AppConfig(data_dir=tmp_path)
    cfg.connections = [
        HermesConnection(id="a", name="A", base_url="http://127.0.0.1:1/v1", api_key="k"),
        HermesConnection(id="b", name="B", base_url="http://127.0.0.1:2/v1", api_key="k"),
    ]
    return HermesClientPool(cfg), cfg


def test_pool_drop_keeps_other_connections_and_closes_replaced_client(tmp_path):
    pool, cfg = _two_conn_pool(tmp_path)

    async def scenario():
        closed = []

        class FakeInner:
            async def close(self):
                closed.append(1)

        a, b = pool.get("a"), pool.get("b")
        a._client = FakeInner()
        cfg.upsert_connection(HermesConnection(id="a", name="A", base_url="http://127.0.0.1:9/v1", api_key="k"))
        assert pool.get("a") is not a  # thay client → đóng client cũ
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert closed == [1]
        pool.drop("a")
        assert pool.get("b") is b  # kết nối khác giữ nguyên

    asyncio.run(scenario())


def test_bubble_is_plain_text_and_reports_pending_actions():
    get_qapp()
    bubble = PetSpeechBubble()
    assert bubble._label.textFormat() == Qt.TextFormat.PlainText
    bubble.show_message("a", actions=[("OK", lambda: None)], timeout_ms=0)
    assert bubble.has_pending_actions()
    bubble.hide()
    assert not bubble.has_pending_actions()


def test_rebuild_module_tabs_only_when_engine_set_changes():
    get_qapp()
    tabs, settings_tab = QTabWidget(), QWidget()
    tabs.addTab(settings_tab, "s")
    built = []

    def make_engine(mid):
        def build():
            built.append(mid)
            return QLabel(mid)
        return SimpleNamespace(manifest=SimpleNamespace(id=mid, icon="", name=mid), build_dashboard_tab=build)

    host = SimpleNamespace(engines={"work": make_engine("work")})
    stub = SimpleNamespace(tabs=tabs, settings_tab=settings_tab, _host=host, _module_tabs=[], _built_engine_ids=())
    DashboardWindow.rebuild_module_tabs(stub)
    DashboardWindow.rebuild_module_tabs(stub)  # đổi module chính → engine không đổi → không dựng lại
    assert built == ["work"]
    host.engines["coach"] = make_engine("coach")
    DashboardWindow.rebuild_module_tabs(stub)
    assert built == ["work", "work", "coach"] and tabs.indexOf(settings_tab) == tabs.count() - 1


def _cheer_provider(state, bubble):
    manifest = SimpleNamespace(id="work", engine="work", prompt_path=lambda _k: None)
    registry = SimpleNamespace(get=lambda _i: manifest, active=lambda: manifest)
    pool = SimpleNamespace(for_module=lambda _i: object())
    focus = SimpleNamespace(state=state, current_mood="IDLE", set_mood=lambda _m: None)
    return CheerLineProvider(registry, pool, focus_engine=focus, bubble=bubble, rng=SimpleNamespace(random=lambda: 0.0, choice=lambda x: x[0])), manifest


def test_hermes_gate_blocks_paused_like_deep_work():
    provider, manifest = _cheer_provider(FocusState.PAUSED, None)
    assert provider.should_ask_hermes(manifest) is False
    provider, manifest = _cheer_provider(FocusState.IDLE, None)
    assert provider.should_ask_hermes(manifest) is True


def test_show_cheer_does_not_replace_bubble_with_actions():
    shown = []
    bubble = SimpleNamespace(has_pending_actions=lambda: True, show_message=lambda *a, **k: shown.append(a))
    provider, _ = _cheer_provider(FocusState.PAUSED, bubble)
    asyncio.run(provider.show_cheer())
    assert shown == []
