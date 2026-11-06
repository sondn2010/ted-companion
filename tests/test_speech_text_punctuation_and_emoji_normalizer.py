"""Chuẩn hoá văn bản cho TTS: không đọc icon, mỗi dòng là một câu, dấu câu gọn để ngắt nghỉ đúng."""

import pytest

from src.core.speech_text_punctuation_and_emoji_normalizer import normalize_text_for_speech, strip_icons
from src.core.tts_service import clean_text_for_speech


@pytest.mark.parametrize(
    "icon",
    ["📅", "✅", "💼", "⚠️", "🎯", "🔴", "🅿️", "👍🏽", "👨‍💻", "🇻🇳", "☕", "⭐", "✨", "🔔", "❤️"],
)
def test_every_emoji_and_icon_is_removed(icon):
    out = normalize_text_for_speech(f"{icon} Họp team lúc 09:00")
    assert out == "Họp team lúc 09:00."


def test_keycap_number_is_read_as_plain_digit():
    assert normalize_text_for_speech("1️⃣ Nộp thuế") == "1 Nộp thuế."


def test_keeps_vietnamese_letters_numbers_and_readable_symbols():
    assert strip_icons("Nhiệt độ 30°, tăng 5%") == "Nhiệt độ 30°, tăng 5%"


def test_each_line_becomes_a_sentence_so_tts_pauses():
    text = "Việc hôm nay:\n- Nộp báo cáo thuế\n- Viết spec\n📅 2 cuộc họp"
    assert normalize_text_for_speech(text) == "Việc hôm nay: Nộp báo cáo thuế. Viết spec. 2 cuộc họp."


def test_dashes_arrows_and_ellipsis_become_pauses():
    out = normalize_text_for_speech("Đang làm X – đúng việc rồi → tiếp theo là Y… cố lên")
    assert out == "Đang làm X, đúng việc rồi, tiếp theo là Y. cố lên."


def test_repeated_and_stacked_punctuation_is_collapsed():
    assert normalize_text_for_speech("Tuyệt vời!!! Xong chưa?! Ừ ,, làm tiếp .") == "Tuyệt vời! Xong chưa? Ừ, làm tiếp."


def test_adds_missing_space_after_punctuation_but_not_inside_numbers():
    out = normalize_text_for_speech("Họp lúc 10:30,phòng A.Sau đó 3.5 giờ,1,000 việc")
    assert out == "Họp lúc 10:30, phòng A. Sau đó 3.5 giờ, 1,000 việc."


def test_parentheses_and_quotes_are_spoken_as_pauses():
    out = normalize_text_for_speech('Rock "Hợp đồng" (treo 5 ngày) cần gỡ')
    assert out == "Rock Hợp đồng, treo 5 ngày, cần gỡ."


def test_hyphen_inside_word_is_kept():
    assert normalize_text_for_speech("Ưu tiên Q1-Q2 trước") == "Ưu tiên Q1-Q2 trước."


def test_icon_only_or_empty_text_gives_nothing_to_speak():
    assert normalize_text_for_speech("🎉✨🚀") == ""
    assert normalize_text_for_speech("") == ""


def test_clean_text_for_speech_on_real_briefing_reply():
    raw = (
        "[MOOD:CHEER] Chào buổi sáng boss! ☀️\n"
        "**Việc hôm nay:**\n"
        "1. 🔴 Nộp thuế\n"
        "2. Viết spec\n"
        "📧 3 email quan trọng — 5 email khác"
    )
    assert clean_text_for_speech(raw) == (
        "Chào buổi sáng boss! Việc hôm nay: 1. Nộp thuế. 2. Viết spec. 3 email quan trọng, 5 email khác."
    )
