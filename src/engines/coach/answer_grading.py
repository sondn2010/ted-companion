"""Chấm câu trả lời: mcq theo chữ cái, short theo so khớp chuẩn hoá, step do người học tự đánh giá."""

import json
import re
import unicodedata

from src.engines.coach.coach_data_models import QuizItem
from src.engines.coach.coach_quiz_writing_report_schemas import extract_choice_letter

SELF_ASSESS_PASS = "lam duoc"
SELF_ASSESS_FAIL = "chua duoc"


def normalize_text(text: str) -> str:
    """casefold, bỏ dấu (NFD; đ→d), gộp khoảng trắng."""
    decomposed = unicodedata.normalize("NFD", text.casefold().replace("đ", "d"))
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", stripped).strip()


def _choice_text(choice: str) -> str:
    return re.sub(r"^\s*[A-Za-z][\.\):]\s*", "", choice)


def grade_mcq(item: QuizItem, user_answer: str) -> bool:
    key = extract_choice_letter(item.answer)
    letter = extract_choice_letter(user_answer)
    if letter is not None:
        return letter == key
    # Gõ nội dung phương án thay vì chữ cái: so với text của phương án đúng
    choices = json.loads(item.choices_json or "[]")
    if key is None or ord(key) - ord("A") >= len(choices):
        return False
    return normalize_text(user_answer) == normalize_text(_choice_text(choices[ord(key) - ord("A")]))


def grade_short(item: QuizItem, user_answer: str) -> bool:
    return normalize_text(user_answer) == normalize_text(item.answer)


def grade_step(self_assessment: str) -> bool:
    """'Làm được' → True, 'Chưa được' → False; giá trị khác là lỗi lập trình ở UI."""
    value = normalize_text(self_assessment)
    if value == SELF_ASSESS_PASS:
        return True
    if value == SELF_ASSESS_FAIL:
        return False
    raise ValueError(f"Tự đánh giá không hợp lệ: {self_assessment!r}")


def grade_answer(item: QuizItem, user_answer: str) -> bool:
    if item.type == "mcq":
        return grade_mcq(item, user_answer)
    if item.type == "step":
        return grade_step(user_answer)
    return grade_short(item, user_answer)
