"""
Kiểm thử bộ quản lý phiên hội thoại (ChatSessionManager) và dịch vụ TTS/STT:
1. Session bền vững qua SQLite (KeyValueStore), không mất khi khởi động lại app.
2. Nút Reset Session tạo mới session ID và xoá sạch ngữ cảnh LLM.
3. TTSService nhận diện đúng tiếng Việt / tiếng Anh và chọn giọng nói chuẩn.
4. Tổng hợp âm thanh qua server TTS (OpenAI-compatible) với mock transport.
5. Kiểm tra kiến trúc tách rời (Engine Provider Pattern) cho cả TTS và STT.
6. STT Service chuyển đổi âm thanh thành văn bản qua OpenAI-compatible API.
7. Bong bóng chat mở rộng và QuickChatPopup có nút Reset Session.
"""

from datetime import datetime
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from PySide6.QtTest import QTest

from tests.qt_offscreen_app_helper import get_qapp

from src.core.app_state_key_value_store import KeyValueStore
from src.core.chat_session_manager import ChatSessionManager
from src.core.tts_service import (
    BaseTTSEngine,
    clean_text_for_speech,
    detect_language,
    is_embedded_tts_available,
    LocalEmbeddedTTSEngine,
    RemoteOpenAITTSEngine,
    TTSService,
)
from src.core.stt_service import (
    BaseSTTEngine,
    is_embedded_stt_available,
    LocalEmbeddedSTTEngine,
    RemoteOpenAISTTEngine,
    STTService,
)
from src.ui.pet_speech_bubble_widget import CHAT_BUBBLE_HEIGHT, CHAT_BUBBLE_WIDTH, PetSpeechBubble
from src.ui.quick_chat_popup import QuickChatPopup


@pytest.fixture
def memory_kv(tmp_path):
    from sqlmodel import create_engine
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    return KeyValueStore(engine)


def test_session_manager_persistence_and_follow(memory_kv):
    manager = ChatSessionManager(kv=memory_kv)

    # Lần đầu tạo session
    s1 = manager.get_session("work")
    assert "session_id" in s1
    assert s1["messages"] == []

    # Ghi nhận lượt nói chuyện
    manager.record_turn("work", "Hôm nay tôi cần làm gì?", "Bạn có 2 việc cần hoàn thành nhé!")

    # Giả lập tắt app và bật lại (tạo instance mới với cùng DB)
    manager_restart = ChatSessionManager(kv=memory_kv)
    s2 = manager_restart.get_session("work")

    assert s2["session_id"] == s1["session_id"]
    assert len(s2["messages"]) == 2
    assert s2["messages"][0]["role"] == "user"
    assert s2["messages"][0]["text"] == "Hôm nay tôi cần làm gì?"
    assert s2["messages"][1]["role"] == "assistant"
    assert s2["messages"][1]["text"] == "Bạn có 2 việc cần hoàn thành nhé!"
    assert len(s2["history"]) == 2


def test_session_manager_reset_session(memory_kv):
    manager = ChatSessionManager(kv=memory_kv)
    manager.record_turn("work", "Câu hỏi 1", "Trả lời 1")

    mock_client = SimpleNamespace(
        history=[
            {"role": "system", "content": "You are Ted"},
            {"role": "user", "content": "Câu hỏi 1"},
            {"role": "assistant", "content": "Trả lời 1"},
        ]
    )
    mock_pool = SimpleNamespace(for_module=lambda mid: mock_client)
    manager.set_client_pool(mock_pool)

    # Bấm Reset Session
    new_session = manager.reset_session("work")

    assert new_session["messages"] == []
    assert new_session["history"] == []
    # Client LLM được reset sạch, chỉ giữ lại system prompt
    assert len(mock_client.history) == 1
    assert mock_client.history[0]["role"] == "system"


def test_tts_language_detection_and_cleaning():
    # Tiếng Việt
    assert detect_language("Xin chào Ted, hôm nay thời tiết thế nào?") == "vi"
    assert detect_language("Cần tập trung 25 phút nhé.") == "vi"

    # Tiếng Anh
    assert detect_language("Hello Ted, can you help me focus today?") == "en"
    assert detect_language("Start pomodoro timer please.") == "en"

    # Lọc bỏ thẻ giao thức và markdown
    raw = "[MOOD:FOCUS] 🐾 Chào bạn! Cố gắng **tập trung** nhé <json>{'a': 1}</json>"
    clean = clean_text_for_speech(raw)
    assert "[MOOD:" not in clean
    assert "<json>" not in clean
    assert "**" not in clean
    assert "Chào bạn! Cố gắng tập trung nhé" in clean


@pytest.mark.asyncio
async def test_tts_service_remote_synthesize():
    get_qapp()

    def mock_handler(request: httpx.Request) -> httpx.Response:
        data = json.loads(request.content)
        assert data["input"] == "Xin chào."  # normalizer thêm dấu kết câu để giọng đọc hạ giọng tự nhiên
        assert data["voice"] == "vi-VN-Standard-A"
        return httpx.Response(200, content=b"MOCK_MP3_BYTES", headers={"content-type": "audio/mpeg"})

    service = TTSService()
    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))

    audio = await service.synthesize(
        "Xin chào", lang="vi", voice="vi-VN-Standard-A", server_url="http://tts.local/v1", http_client=mock_client
    )
    assert audio == b"MOCK_MP3_BYTES"


@pytest.mark.asyncio
async def test_decoupled_tts_engines():
    """Kiểm tra các Engine TTS triển khai đúng BaseTTSEngine và có thể chạy độc lập."""
    remote_engine = RemoteOpenAITTSEngine(server_url="http://mock-tts:8000/v1")
    assert isinstance(remote_engine, BaseTTSEngine)

    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"ENGINE_WAV_BYTES", headers={"content-type": "audio/wav"})

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))
    res = await remote_engine.synthesize("Test Engine", voice="alloy", speed=1.0, http_client=mock_client)
    assert res == b"ENGINE_WAV_BYTES"

    local_engine = LocalEmbeddedTTSEngine()
    assert isinstance(local_engine, BaseTTSEngine)


@pytest.mark.asyncio
async def test_decoupled_stt_engines_and_service():
    """Kiểm tra kiến trúc tách rời cho STT (BaseSTTEngine, RemoteOpenAISTTEngine, STTService)."""
    def mock_stt_handler(request: httpx.Request) -> httpx.Response:
        # Kiểm tra endpoint và multipart
        assert "/audio/transcriptions" in str(request.url)
        return httpx.Response(200, json={"text": "Xin chào, đây là giọng nói của tôi"})

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_stt_handler))

    remote_stt = RemoteOpenAISTTEngine(server_url="http://mock-stt:8881/v1")
    assert isinstance(remote_stt, BaseSTTEngine)

    text = await remote_stt.transcribe(b"FAKE_AUDIO_DATA", filename="voice.wav", http_client=mock_client)
    assert text == "Xin chào, đây là giọng nói của tôi"

    local_stt = LocalEmbeddedSTTEngine()
    assert isinstance(local_stt, BaseSTTEngine)

    # Test STTService test_connection helper
    stt_svc = STTService()
    ok, msg = await stt_svc.test_connection(
        server_url="http://mock-stt:8881/v1",
        http_client=mock_client,
    )
    assert ok is True
    assert "thành công" in msg


def test_pet_speech_bubble_chat_mode_size_and_scroll():
    get_qapp()
    bubble = PetSpeechBubble()

    # Chế độ tin nhắn ngắn (cheer / thông báo): kích thước nhỏ gọn
    bubble.show_message("Đừng lo, cứ từ từ nhé.")
    assert not bubble._chat_mode
    assert bubble._chat_view.isHidden()
    assert bubble._label.isVisible()
    assert bubble.width() <= 255

    # Chế độ chat: mở rộng khung chat, hiển thị scroll view
    bubble.open_chat("work")
    assert bubble._chat_mode
    assert bubble._chat_view.isVisible()
    assert bubble._label.isHidden()
    assert bubble._chat_header.isVisible()
    assert bubble.width() == CHAT_BUBBLE_WIDTH
    assert bubble.height() == CHAT_BUBBLE_HEIGHT

    # Nút Reset session sẵn sàng trên header
    assert hasattr(bubble, "btn_reset_session")
    assert bubble.btn_reset_session.isVisible()


def test_quick_chat_popup_has_reset_session_button():
    get_qapp()
    focus = SimpleNamespace(
        character_changed=SimpleNamespace(connect=lambda f: None),
        state_changed=SimpleNamespace(connect=lambda f: None),
    )
    pool = SimpleNamespace(for_module=lambda m: None)
    registry = SimpleNamespace(active=lambda: None)

    popup = QuickChatPopup(focus_engine=focus, client_pool=pool, registry=registry)
    popup.show()
    assert hasattr(popup, "btn_reset")
    assert popup.btn_reset.isVisible()   # trang Chat trong Dashboard: kích thước theo cửa sổ app, không cố định


def test_voice_profile_dialog_prefills_and_applies():
    """Kiểm tra VoiceProfileDialog tự động điền các tham số theo preset và phát tín hiệu applied."""
    get_qapp()
    from src.ui.dashboard_tabs.voice_profile_dialog import VoiceProfileDialog, VOICE_PRESETS

    dlg = VoiceProfileDialog()
    assert dlg.combo_presets.count() == len(VOICE_PRESETS)

    # Thử chọn preset "Nam Trầm ấm, Già dặn (~40-50 tuổi)"
    dlg.combo_presets.setCurrentIndex(0)
    assert dlg.txt_model.text() == "tts-1"
    assert dlg.combo_voice_vi.currentText() == "vi-VN-NamMinhNeural"
    assert dlg.combo_voice_en.currentText() == "onyx"
    assert dlg.spin_speed.value() == 0.85

    # Thử chọn preset "Nữ Trẻ trung, Ngọt ngào (~18-20 tuổi)"
    young_idx = dlg.combo_presets.findData("female_young_sweet_18s")
    assert young_idx >= 0
    dlg.combo_presets.setCurrentIndex(young_idx)
    assert dlg.combo_voice_vi.currentText() == "vi-VN-Standard-A"
    assert dlg.combo_voice_en.currentText() == "nova"
    assert dlg.spin_speed.value() == 1.1

    # Kiểm tra tín hiệu profile_applied
    applied_events = []
    dlg.profile_applied.connect(lambda d: applied_events.append(d))
    dlg._on_apply_clicked()

    assert len(applied_events) == 1
    applied = applied_events[0]
    assert applied["model"] == "tts-1"
    assert applied["voice_vi"] == "vi-VN-Standard-A"
    assert applied["voice_en"] == "nova"
    assert applied["speed"] == 1.1
