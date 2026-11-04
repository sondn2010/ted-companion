"""Cá tính nhân vật (tên / tính cách / giọng riêng) + cử chỉ ẩn click 5 lần lên pet.
Persona chỉ là cấu hình phía app: chưa lưu thì mọi thứ giữ như cũ; không đụng prompt Hermes."""

import random

import pytest
from PySide6.QtTest import QTest

from qt_offscreen_app_helper import flush_qt_garbage, get_qapp

from src.config import settings
from src.core import character_persona_profiles as personas
from src.core.tts_service import TTSService
from src.ui.pet_click_controller import PetClickController



@pytest.fixture(autouse=True)
def _flush_widgets_after_test():
    yield
    flush_qt_garbage()

@pytest.fixture
def clean_personas(monkeypatch):
    monkeypatch.setattr(settings, "character_personas", {})
    monkeypatch.setattr(settings, "character_skin", "owl")
    monkeypatch.setattr(settings, "tts_mode", "server")
    monkeypatch.setattr(settings, "save", lambda: None)


def _controller(events):
    get_qapp()
    return PetClickController(lambda: events.append("single"), lambda: events.append("double"),
                              interval_ms=lambda: 30, on_multi=lambda: events.append("multi"))


def test_five_quick_clicks_open_persona_without_single_or_double():
    events = []
    ctl = _controller(events)
    ctl.on_release(False)
    ctl.on_double_click()
    ctl.on_release(False)      # release của cú đúp: bỏ qua
    ctl.on_release(False)
    ctl.on_double_click()
    ctl.on_release(False)
    ctl.on_release(False)      # click thứ 5
    QTest.qWait(80)
    assert events == ["multi"]


def test_double_click_still_opens_chat_after_short_wait_and_single_still_cheers():
    events = []
    ctl = _controller(events)
    ctl.on_release(False)
    ctl.on_double_click()
    ctl.on_release(False)
    assert events == []         # chờ xem có click tiếp không
    QTest.qWait(80)
    assert events == ["double"]
    events.clear()
    ctl.on_release(False)
    QTest.qWait(80)
    assert events == ["single"]


def test_no_persona_saved_keeps_default_name_and_voice(clean_personas):
    assert personas.saved_persona() is None
    assert settings.character_display_name.startswith("🦉")
    assert TTSService().pick_voice("vi") == settings.tts_voice_vi


def test_saved_persona_changes_name_voice_and_speed(clean_personas, monkeypatch):
    persona = personas.persona_for_editing("owl")
    assert persona.name == "Cú Thông Thái" and persona.personality == "calm_wise"
    persona.name, persona.voice_vi, persona.speed = "Cú Mèo", "vi-VN-NamMinhNeural", 0.85
    personas.save_persona(persona)
    assert settings.character_display_name == "🦉 Cú Mèo"
    service = TTSService()
    assert service.pick_voice("vi") == "vi-VN-NamMinhNeural"
    assert service.pick_voice("en") == settings.tts_voice_en   # giọng máy chủ để trống = theo cấu hình chung
    assert personas.active_voice_override().speed == 0.85
    persona.use_own_voice = False
    personas.save_persona(persona)
    assert service.pick_voice("vi") == settings.tts_voice_vi     # tắt giọng riêng → dùng cấu hình chung
    personas.reset_persona("owl")
    assert personas.saved_persona() is None


def test_personality_catchphrases_mix_into_single_click_cheers(clean_personas):
    from types import SimpleNamespace
    from src.modules_runtime.cheer_line_provider import CheerLineProvider
    personas.save_persona(personas.persona_for_editing("owl"))
    rng = random.Random()
    rng.random = lambda: 0.0      # luôn chọn câu cửa miệng
    provider = CheerLineProvider(SimpleNamespace(get=lambda _m: None), None, rng=rng)
    assert provider.pick_local(None) in personas.saved_persona().catchphrases()


def test_persona_dialog_loads_defaults_and_saves(clean_personas):
    get_qapp()
    from src.ui.character_persona_dialog import CharacterPersonaDialog
    dialog = CharacterPersonaDialog("shiba")
    assert dialog.txt_name.text() == "Shiba Lửa" and dialog.combo_personality.currentData() == "energetic"
    assert "Shiba Lửa" in dialog.lbl_preview.text()
    dialog.txt_name.setText("Lucky")
    dialog.combo_personality.setCurrentIndex(dialog.combo_personality.findData("funny"))
    assert dialog.spin_speed.value() == pytest.approx(1.1)     # gợi ý tốc độ theo tính cách
    saved = []
    dialog.persona_saved.connect(saved.append)
    dialog.btn_save.click()
    assert saved == ["shiba"]
    stored = settings.character_personas["shiba"]
    assert stored["name"] == "Lucky" and stored["personality"] == "funny"


def test_bubble_voice_toggle_hidden_until_tts_configured_and_mutes(monkeypatch):
    get_qapp()
    from src.core import tts_service as tts_mod
    from src.ui.pet_speech_bubble_widget import PetSpeechBubble
    for key, value in (("tts_enabled", False), ("tts_configured", False), ("tts_mode", "auto")):
        monkeypatch.setattr(settings, key, value)
    monkeypatch.setattr(settings, "save", lambda: None)
    monkeypatch.setattr(tts_mod, "is_embedded_tts_available", lambda: False)
    stopped = []
    monkeypatch.setattr(tts_mod.tts_service, "stop", lambda: stopped.append(1))
    bubble = PetSpeechBubble()
    assert bubble.btn_toggle_voice.isHidden()                 # chưa cấu hình giọng nói → ẩn

    monkeypatch.setattr(settings, "tts_enabled", True)
    bubble.refresh_voice_toggle()
    assert not bubble.btn_toggle_voice.isHidden() and bubble.btn_toggle_voice.isChecked()
    bubble.btn_toggle_voice.click()                            # tắt tiếng
    assert settings.tts_enabled is False and stopped == [1] and "🔇" in bubble.btn_toggle_voice.text()
    bubble.refresh_voice_toggle()
    assert not bubble.btn_toggle_voice.isHidden()             # đã từng cấu hình → vẫn hiện để bật lại
    bubble.btn_toggle_voice.click()
    assert settings.tts_enabled is True and "🔊" in bubble.btn_toggle_voice.text()
