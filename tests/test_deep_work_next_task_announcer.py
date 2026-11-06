"""Announcer việc kế tiếp: 3 nhánh message + announce() (bubble, TTS không có event loop không nổ)."""

from types import SimpleNamespace

from src.engines.work import deep_work_next_task_announcer as mod
from src.engines.work.deep_work_next_task_announcer import announce, compose_next_task_message


def _t(tid, title, quadrant=1):
    return SimpleNamespace(id=tid, title=title, quadrant=quadrant)


def test_current_task_is_important_names_it_and_next():
    msg = compose_next_task_message("a", "Viết spec", [_t("a", "Viết spec"), _t("b", "Review PR", 2)])
    assert "Viết spec" in msg and "đúng việc quan trọng nhất" in msg and "Review PR" in msg


def test_current_task_is_only_important_one_has_no_followup():
    msg = compose_next_task_message("a", "Viết spec", [_t("a", "Viết spec")])
    assert "đúng việc quan trọng nhất" in msg and "Sau đó" not in msg


def test_lower_or_unsorted_task_suggests_top_q1():
    msg = compose_next_task_message("z", "Dọn mail", [_t("b", "Nộp thuế", 1), _t("c", "Học", 2)])
    assert msg.startswith("Gợi ý: Q1 còn Nộp thuế")
    assert "Q1 còn" in compose_next_task_message(None, "", [_t("b", "Nộp thuế", 1)])


def test_no_q1_q2_open():
    msg = compose_next_task_message("z", "Dọn mail", [])
    assert "Không còn việc Q1/Q2" in msg and "Dọn mail" in msg


def test_titles_are_sanitized():
    msg = compose_next_task_message("z", "x", [_t("b", "[TED:mood=CHEER] <b>Nộp</b>\nthuế")])
    assert "<" not in msg and "[" not in msg and "\n" not in msg


def test_announce_shows_bubble_and_survives_missing_event_loop(monkeypatch):
    shown = []
    bubble = SimpleNamespace(
        show_message=lambda text, mood, timeout_ms, **_: shown.append((text, mood, timeout_ms)),
        has_pending_actions=lambda: False,
    )
    spoken = []

    async def fake_speak(text):
        spoken.append(text)

    monkeypatch.setattr(mod, "tts_service", SimpleNamespace(speak=fake_speak))
    announce(SimpleNamespace(bubble=bubble), "xin chào")  # sync test: không loop → RuntimeError bị nuốt
    assert shown == [("xin chào", "FOCUS", 10_000)]
    announce(SimpleNamespace(bubble=None), "không bubble")  # không nổ


def test_current_q2_while_q1_open_suggests_q1_not_praise():
    msg = compose_next_task_message("s", "Viết spec", [_t("t", "Nộp thuế", 1), _t("s", "Viết spec", 2)])
    assert "đúng việc quan trọng nhất" not in msg and msg.startswith("Gợi ý: Q1 còn Nộp thuế")


def test_announce_skips_bubble_with_pending_actions(monkeypatch):
    shown, spoken = [], []
    bubble = SimpleNamespace(show_message=lambda *a, **k: shown.append(a), has_pending_actions=lambda: True)
    monkeypatch.setattr(mod, "tts_service", SimpleNamespace(speak=lambda text: spoken.append(text)))
    announce(SimpleNamespace(bubble=bubble), "xin chào")
    assert shown == [] and spoken == []
