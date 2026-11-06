"""Chat & ôn tập hiển thị công thức / bảng / hình vẽ cho học sinh cấp 2:
1. Nhận diện markup (không nhầm tiền tệ "50$"), escape an toàn (thẻ HTML của AI hiện nguyên văn).
2. Công thức → ảnh (mathtext) kể cả hệ phương trình / ma trận; thiếu/lỗi → chữ Unicode dễ đọc.
3. Bảng markdown, danh sách ô tích, hình SVG (hỏng thì báo nhẹ nhàng).
4. TTS đọc công thức thành lời, bỏ qua hình vẽ.
5. Quick Chat dựng lại câu trả lời sau stream; câu hỏi trắc nghiệm có công thức vẫn bấm được.
"""

import asyncio
import json
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QLabel, QTextEdit
from qt_offscreen_app_helper import flush_qt_garbage, get_qapp

from src.core.background_task_spawner import _running_tasks
from src.core.tts_service import clean_text_for_speech
from src.engines.coach.coach_data_models import QuizItem
from src.ui.rich_content.latex_math_image_renderer import math_html
from src.ui.rich_content.latex_to_speakable_text import speakable_text_from_rich_reply
from src.ui.rich_content.latex_unicode_fallback import latex_to_unicode
from src.ui.rich_content.rich_reply_html_renderer import reply_body_html, rich_reply_html
from src.ui.rich_content.rich_reply_segment_patterns import has_rich_markup
from src.ui.rich_content.rich_text_view_helpers import replace_trailing_plain_text_with_html


@pytest.fixture(autouse=True)
def _flush_widgets_after_test():
    yield
    flush_qt_garbage()

TRIANGLE_SVG = ('<svg width="200" height="120"><polygon points="10,110 190,110 10,10" fill="none" stroke="#000"/>'
                '<text x="2" y="10">A</text></svg>')


def test_markup_detection_ignores_currency_and_plain_chat():
    assert not has_rich_markup("Chào em! Hôm nay học gì nào?")
    assert not has_rich_markup("Quyển sách giá 50$ và cây bút giá 10$.")
    assert has_rich_markup("Giải $x^2 = 4$ nhé")
    assert has_rich_markup("$$\\frac{1}{2}$$")
    assert has_rich_markup("| a | b |\n|---|---|\n| 1 | 2 |")
    assert has_rich_markup(f"Hình:\n```svg\n{TRIANGLE_SVG}\n```")


def test_ai_html_is_escaped_never_rendered():
    html = rich_reply_html("**Chú ý** <img src=x onerror=alert(1)> <b>x</b> $a+b$")
    assert "&lt;img src=x" in html and "&lt;b&gt;x&lt;/b&gt;" in html
    assert "<b>Chú ý</b>" in html


def test_math_renders_to_inline_and_display_images():
    get_qapp()
    inline = math_html("x^2 + \\sqrt{x}", display=False)
    assert inline.startswith("<img src='data:image/png;base64,") and "vertical-align: middle" in inline
    display = math_html("x = \\dfrac{-b \\pm \\sqrt{\\Delta}}{2a}", display=True)
    assert display.startswith("<p align='center'><img")


def test_system_of_equations_and_matrix_become_bracketed_tables():
    get_qapp()
    cases = math_html("\\begin{cases} 2x + y = 5 \\\\ x - y = 1 \\end{cases}", display=True)
    assert "{" in cases and cases.count("<img") == 2 and "<table" in cases
    matrix = math_html("A = \\begin{pmatrix} 1 & 2 \\\\ 3 & 4 \\end{pmatrix}", display=True)
    assert matrix.count("<img") == 5 and "(" in matrix and ")" in matrix


def test_unsupported_latex_falls_back_to_readable_unicode():
    get_qapp()
    html = math_html("\\unknowncommand{x}^2", display=False)
    assert "<img" not in html and "unknowncommand" in html
    assert latex_to_unicode("\\frac{a+1}{2} \\le \\sqrt{x^2} \\cdot \\pi") == "(a+1)/2 ≤ √x² · π"
    assert latex_to_unicode("x_1 + x_2 = 90^\\circ") == "x₁ + x₂ = 90°"


def test_markdown_table_checklist_heading_and_svg():
    get_qapp()
    text = (f"## Bảng\n| Bước | Kết quả |\n|---|---|\n| 1 | $x=2$ |\n\n- [x] Đã hiểu\n- [ ] Bài về nhà\n"
            f"```svg\n{TRIANGLE_SVG}\n```")
    html = rich_reply_html(text)
    assert "<table border='1'" in html and "<th" in html and html.count("<img") == 2
    assert "☑ Đã hiểu" in html and "☐ Bài về nhà" in html and "font-size:16px" in html
    assert "Không hiển thị được hình vẽ" in rich_reply_html("```svg\n<svg><polygon\n```")


def test_plain_reply_body_keeps_line_breaks_and_escaping():
    assert reply_body_html("Dòng 1\n<i>Dòng 2</i>") == "Dòng 1<br>&lt;i&gt;Dòng 2&lt;/i&gt;"


def test_short_latex_relations_render_as_images_not_fallback():
    # mathtext chỉ biết \leq/\geq/\neq → \le, \ge, \ne phải được đổi, không rơi về chữ Unicode
    get_qapp()
    for expr in ("|x-3| \\le 2", "x \\ge 0", "a \\ne b"):
        assert math_html(expr, display=False).startswith("<img"), expr


def test_display_fraction_is_full_size():
    get_qapp()
    small = math_html("\\frac{1}{2}", display=False)
    big = math_html("\\frac{1}{2}", display=True)
    height = lambda html: int(html.split("height='")[1].split("'")[0])
    assert height(big) > height(small) * 1.5


def test_unicode_math_symbols_use_math_font():
    # Font app vẽ sai √ / ∞ / ∫ → ký hiệu toán phải được bọc bằng font toán học (cả chữ thuần lẫn markdown)
    plain = reply_body_html("√16 = 4, x → ∞")
    assert "Cambria Math" in plain and ">√<" in plain and ">∞<" in plain
    rich = reply_body_html("**Kết quả:** ∫ x dx")
    assert "<b>Kết quả:</b>" in rich and ">∫<" in rich
    assert "Cambria Math" not in reply_body_html("Chào em, 1 + 1 = 2")


def test_tts_reads_math_as_words_and_skips_figures():
    spoken = speakable_text_from_rich_reply(f"Ta có $x^2 + \\frac{{1}}{{2}} = 0$.\n```svg\n{TRIANGLE_SVG}\n```")
    assert "x bình phương cộng 1 phần 2 bằng 0" in spoken and "(hình vẽ)" in spoken and "<svg" not in spoken
    assert "squared" in speakable_text_from_rich_reply("We know $a^2$ is positive")
    assert "polygon" not in clean_text_for_speech(f"Hình:\n{TRIANGLE_SVG}")


def test_trailing_streamed_text_is_replaced_only_when_it_matches():
    get_qapp()
    view = QTextEdit()
    view.setHtml("<p>Ted: </p>")
    raw = "Nghiệm là $x = 2$ 😀\ndòng 2"
    cursor = view.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    cursor.insertText(raw)
    assert replace_trailing_plain_text_with_html(view, raw) is True
    assert "data:image/png" in view.toHtml() and "$x = 2$" not in view.toPlainText()
    assert replace_trailing_plain_text_with_html(view, "không khớp $y$") is False


class _Focus(QObject):
    character_changed = Signal(str)
    current_mood = "IDLE"

    def get_context_snapshot(self):
        return {}

    def set_mood(self, mood):
        pass


async def test_quick_chat_renders_math_after_stream_finishes():
    get_qapp()
    from src.ui.quick_chat_popup import QuickChatPopup

    async def stream(user_message, current_context, on_mood_change, on_token, **_kw):
        for token in ["Ta có ", "$\\Delta = b^2", " - 4ac$", "\n| a | b |\n|---|---|\n| 1 | 2 |"]:
            on_token(token)
        return ""

    client = SimpleNamespace(connection=SimpleNamespace(name="T"), stream_chat=stream)
    popup = QuickChatPopup(_Focus(), SimpleNamespace(for_module=lambda _m: client), SimpleNamespace(active=lambda: None))
    popup.input_chat.setText("Công thức delta?")
    popup.input_chat.returnPressed.emit()
    await asyncio.gather(*list(_running_tasks))
    html = popup.chat_view.toHtml()
    assert "data:image/png;base64" in html and "$\\Delta" not in popup.chat_view.toPlainText()
    assert "Công thức delta?" in popup.chat_view.toPlainText()


def test_mcq_with_formula_choices_uses_rich_button_and_still_answers():
    get_qapp()
    from src.ui.quiz.quiz_question_renderers import McqQuestionWidget
    item = QuizItem(module_id="thcs", type="mcq", question="Nghiệm của $x^2 = 4$ là?", content_hash="h",
                    choices_json=json.dumps(["A. $x = 2$", "B. $x = \\pm 2$", "C. Vô nghiệm", "D. $x=4$"]), answer="B")
    widget = McqQuestionWidget(item)
    answers = []
    widget.answered.connect(answers.append)
    rich = widget.choice_buttons[1].findChild(QLabel)
    assert rich is not None and "data:image/png" in rich.text()
    assert widget.choice_buttons[2].text() == "C. Vô nghiệm"      # chữ thường giữ nút chuẩn
    widget.choice_buttons[1].click()
    assert answers == ["B"]
