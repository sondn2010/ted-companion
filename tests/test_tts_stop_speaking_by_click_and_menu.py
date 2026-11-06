"""Ted đang nói → click Ted hoặc menu "Dừng đọc" để im ngay câu đó (giọng đọc vẫn bật cho câu sau)."""

import asyncio
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QMenu, QWidget

from src.config import settings
from src.core import tts_service as tts_module
from src.core.focus_engine import FocusState
from src.core.i18n import tr
from src.ui.button_text_escape import btn_text
from src.ui.companion_context_menu_builder import build_companion_context_menu
from src.ui.companion_widget import TedCompanionWidget
from tests.qt_offscreen_app_helper import get_qapp


class _FakeTTS:
    def __init__(self, speaking: bool):
        self.speaking = speaking
        self.stopped = 0

    def is_speaking(self) -> bool:
        return self.speaking

    def stop(self) -> None:
        self.stopped += 1
        self.speaking = False


def _menu_texts(monkeypatch, speaking: bool):
    get_qapp()
    fake = _FakeTTS(speaking)
    monkeypatch.setattr(tts_module, "tts_service", fake)
    focus = SimpleNamespace(
        state=FocusState.IDLE, pause_or_resume=lambda: None, stop_session=lambda completed=False: None,
        start_break=lambda: None, set_character=lambda k: None,
    )
    ctx = SimpleNamespace(
        focus_engine=focus, registry=SimpleNamespace(active=lambda: None, enabled=lambda: []),
        audio=SimpleNamespace(is_ambient_playing=False, toggle_ambient=lambda: None),
        engine_host=SimpleNamespace(dispatch=lambda m, a: None), dashboard=SimpleNamespace(open_settings=lambda: None),
    )
    host = QWidget()
    menu = build_companion_context_menu(QMenu(host), ctx, SimpleNamespace(open_dashboard=lambda: None, hide=lambda: None))
    return host, menu, fake


def test_menu_shows_stop_speaking_first_only_while_ted_speaks(monkeypatch):
    _host, menu, fake = _menu_texts(monkeypatch, speaking=True)
    first = menu.actions()[0]
    assert first.text() == btn_text(tr("menu_stop_speaking"))
    first.trigger()
    assert fake.stopped == 1

    _host2, idle_menu, _ = _menu_texts(monkeypatch, speaking=False)
    assert btn_text(tr("menu_stop_speaking")) not in [a.text() for a in idle_menu.actions()]


def test_click_on_ted_while_speaking_stops_instead_of_cheering(monkeypatch):
    fake = _FakeTTS(speaking=True)
    monkeypatch.setattr(tts_module, "tts_service", fake)
    clicked_engine = []
    fake_self = SimpleNamespace(ctx=SimpleNamespace(engine_host=SimpleNamespace(
        active_engine=lambda: clicked_engine.append(1))))
    TedCompanionWidget._on_single_click(fake_self)
    assert fake.stopped == 1
    assert clicked_engine == []  # không briefing/cổ vũ khi bấm để im


class _SlowTTS(tts_module.TTSService):
    def __init__(self):
        super().__init__()
        self.gate = asyncio.Event()

    async def synthesize(self, text, lang=None, voice=None, **_kw):
        await self.gate.wait()
        return b"RIFFfake"

    def _play_bytes(self, data: bytes) -> None:
        self.played = data


@pytest.mark.asyncio
async def test_is_speaking_covers_synthesis_and_clears_after_stop(monkeypatch):
    get_qapp()
    monkeypatch.setattr(settings, "tts_enabled", True, raising=False)
    tts = _SlowTTS()
    assert tts.is_speaking() is False
    task = asyncio.create_task(tts.speak("Xin chào"))
    await asyncio.sleep(0)
    assert tts.is_speaking() is True  # đang tổng hợp: click lúc này cũng phải dừng được
    tts.stop()
    assert tts.is_speaking() is False
    tts.gate.set()
    await task
    assert not hasattr(tts, "played")  # câu đã bị dừng không phát ra
