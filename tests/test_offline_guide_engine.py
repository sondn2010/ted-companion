"""Kiểm thử bộ tri thức ngoại tuyến (Offline Guide Engine) dành cho người mới."""

import pytest

from src.core.offline_guide_engine import (
    OFFLINE_TOPICS,
    get_offline_starter_menu,
    match_offline_guide,
)


def test_offline_topics_have_required_fields():
    assert len(OFFLINE_TOPICS) >= 8
    for topic in OFFLINE_TOPICS:
        assert topic.id
        assert topic.title_vi and topic.title_en
        assert len(topic.keywords) > 0
        assert topic.answer_vi and topic.answer_en


def test_match_offline_guide_exact_keywords():
    # Pomodoro
    res = match_offline_guide("pomodoro", lang="vi")
    assert res is not None
    topic, answer = res
    assert topic.id == "pomodoro"
    assert "25 phút" in answer

    # Parking lot / Bai do
    res_parking = match_offline_guide("bãi đỗ xao nhãng", lang="vi")
    assert res_parking is not None
    topic, answer = res_parking
    assert topic.id == "parking_lot"
    assert "Cất nhanh ý tưởng" in answer


def test_match_offline_guide_accent_insensitive():
    # Không dấu tiếng Việt
    res = match_offline_guide("bai do", lang="vi")
    assert res is not None
    assert res[0].id == "parking_lot"

    res2 = match_offline_guide("deep work la gi", lang="vi")
    assert res2 is not None
    assert res2[0].id == "deep_work"

    res3 = match_offline_guide("thao tac chuot", lang="vi")
    assert res3 is not None
    assert res3[0].id == "mouse_shortcuts"


def test_match_offline_guide_english():
    res = match_offline_guide("who is ted", lang="en")
    assert res is not None
    topic, answer = res
    assert topic.id == "ted_intro"
    assert "desktop buddy" in answer.lower()

    res_pom = match_offline_guide("pomodoro timer", lang="en")
    assert res_pom is not None
    assert "25-min" in res_pom[1]


def test_match_offline_guide_unknown_returns_none():
    assert match_offline_guide("hom nay an com voi gi") is None
    assert match_offline_guide("") is None
    assert match_offline_guide("   ") is None


def test_get_offline_starter_menu():
    menu_vi = get_offline_starter_menu("vi")
    assert "chế độ Ngoại tuyến" in menu_vi
    assert "pomodoro" in menu_vi

    menu_en = get_offline_starter_menu("en")
    assert "Offline Mode" in menu_en
    assert "pomodoro" in menu_en
