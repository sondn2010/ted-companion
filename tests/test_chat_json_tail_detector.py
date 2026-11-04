"""ChatJsonTailDetector: ẩn khối <json> cuối câu trả lời streaming, trả JSON; không cắt nhầm lời giải thích."""

from src.bridge.chat_json_tail_detector import ChatJsonTailDetector


def _run(pieces: list[str]):
    detector, shown = ChatJsonTailDetector(), []
    for piece in pieces:
        shown.append(detector.feed(piece))
    leftover, data = detector.finish()
    return "".join(shown) + leftover, data


def test_block_split_across_tokens_is_hidden_and_parsed():
    text, data = _run(["Xong rồi! <js", "on>{\"onboarding\":", "\"done\",\"learner\":\"con\"}</", "json>"])
    assert text == "Xong rồi! " and data == {"onboarding": "done", "learner": "con"}


def test_no_block_passes_everything_through_including_partial_tag_lookalike():
    text, data = _run(["a < b và ", "<j", "ust text"])
    assert text == "a < b và <just text" and data is None


def test_trailing_partial_tag_is_flushed_at_finish():
    assert _run(["hết <js"]) == ("hết <js", None)


def test_text_after_block_means_mid_reply_json_so_everything_shown_and_no_data():
    # Review M1: khối không nằm ở cuối câu trả lời → không ẩn, không kích hoạt handler
    reply = 'Trước <json>{"onboarding":"done"}</json> sau đó nói thêm'
    assert _run([reply]) == (reply, None)


def test_malformed_json_is_hidden_and_returns_none():
    text, data = _run(["ok <json>{not json}</json>"])
    assert text == "ok " and data is None


def test_json_array_is_not_a_trigger():
    assert _run(["<json>[1,2]</json>"]) == ("", None)


def test_open_tag_inside_code_fence_written_by_model_is_plain_text():
    pieces = ["Ví dụ:\n```\n", "<json>", '{"onboarding":"done"}', "</json>\n```\nHết"]
    text, data = _run(pieces)
    assert "<json>" in text and "Hết" in text and data is None


def test_unclosed_prose_tag_is_returned_but_unclosed_json_is_dropped():
    prose, data = _run(["Bạn dùng thẻ <json> để bọc kết quả nhé"])
    assert prose == "Bạn dùng thẻ <json> để bọc kết quả nhé" and data is None
    cut, data = _run(['Tóm tắt <json>{"onboarding":"do'])
    assert cut == "Tóm tắt " and data is None


def test_detector_is_reusable_state_resets_after_finish():
    detector = ChatJsonTailDetector()
    detector.feed('x <json>{"a":1}')
    assert detector.finish()[1] is None
    assert detector.feed("lượt mới") == "lượt mới"
