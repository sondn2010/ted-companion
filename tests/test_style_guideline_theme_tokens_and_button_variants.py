"""Chuẩn style (docs/UI/style-guideline.md): QSS chỉ dùng @TOKEN (không hex), mọi token resolve được,
biến thể nút cũ đã bỏ, và cùng một hành động (🅿️ Bãi đỗ, 💬 Chat) cùng một biến thể ở mọi nơi."""

import re
from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import QObject, Signal

from tests.qt_offscreen_app_helper import get_qapp

from src.ui.pet_speech_bubble_widget import PetSpeechBubble
from src.ui.quick_chat_popup import QuickChatPopup
from src.ui.theme.app_theme_loader import build_stylesheet, resolve_tokens

SRC = Path(__file__).resolve().parents[1] / "src"
QSS_DIR = SRC / "ui" / "theme" / "qss"
REMOVED_VARIANTS = ("SuccessBtn", "WarnBtn", "BubbleChatBtn", "BubbleParkBtn", "BubbleActionBtn",
                    "BubbleResetBtn", "LangBtn", "ViewToggleBtn", "AddTaskBtn", "ParkingInput")


class _Focus(QObject):
    character_changed = Signal(str)

    def get_context_snapshot(self):
        return {}


def _strip_comments(qss: str) -> str:
    return re.sub(r"/\*.*?\*/", "", qss, flags=re.S)


def test_qss_rules_use_tokens_not_raw_colors():
    for path in QSS_DIR.glob("*.qss"):
        rules = _strip_comments(path.read_text(encoding="utf-8"))
        assert not re.search(r"#[0-9A-Fa-f]{3,8}\b|rgba?\(", rules), f"{path.name} còn màu viết cứng"


def test_every_token_resolves():
    qss = _strip_comments(build_stylesheet())
    assert not re.findall(r"@[A-Z]\w*", qss)
    assert "#00ADEF" in qss and "background-color: #212428" in qss


def test_unknown_token_is_left_untouched():
    assert resolve_tokens("color: @PRIMARY; x: @NOT_A_TOKEN;") == "color: #00ADEF; x: @NOT_A_TOKEN;"


def test_removed_variants_are_not_used_anymore():
    for path in list(SRC.rglob("*.py")) + list(QSS_DIR.glob("*.qss")):
        text = path.read_text(encoding="utf-8")
        used = [name for name in REMOVED_VARIANTS if f'"{name}"' in text or f"#{name}" in text]
        assert not used, f"{path.name} còn dùng {used}"


def test_no_inline_stylesheet_in_widgets():
    offenders = [p.name for p in (SRC / "ui").rglob("*.py")
                 if "setStyleSheet(" in p.read_text(encoding="utf-8") and p.name != "app_theme_loader.py"]
    assert offenders == []


def test_parking_and_chat_buttons_share_one_variant_everywhere():
    get_qapp()
    bubble = PetSpeechBubble()
    popup = QuickChatPopup(_Focus(), SimpleNamespace(for_module=lambda _m: None),
                           SimpleNamespace(active=lambda: None, get=lambda _m: None))
    # 🅿️ Bãi đỗ = Secondary (không objectName) ở bong bóng lẫn Quick Chat; bong bóng chỉ thêm compact
    assert bubble.btn_park.objectName() == popup.btn_park.objectName() == ""
    assert bubble.btn_park.property("compact") is True and popup.btn_park.property("compact") is None
    assert bubble.btn_park.text().startswith("🅿️") and popup.btn_park.text().startswith("🅿️")
    # 💬 Chat / Gửi = Primary
    assert bubble.btn_chat.objectName() == popup.btn_send.objectName() == "PrimaryBtn"
