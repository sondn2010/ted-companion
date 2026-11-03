"""Briefing đầu ngày (thuần, không I/O): text local luôn dùng được offline + giá trị cho prompt Hermes."""

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

# Dữ liệu ngoài (tiêu đề lịch họp do người khác gửi) có thể chứa chỉ dẫn → bỏ thẻ [TED_*], ký tự đặc biệt
_TED_TAG = re.compile(r"\[\s*TED_[^\]]*\]?", re.I)
_UNSAFE_CHARS = re.compile(r"[^\w\s.,:;!?()&'+#@/%-]", re.UNICODE)
MAX_ITEM_CHARS = 80
MAX_SPOKEN_EMAILS = 5  # bubble/đọc to chỉ nêu tối đa chừng này email quan trọng, phần còn lại là số lượng


def sanitize_untrusted_text(text: str, max_chars: int = MAX_ITEM_CHARS) -> str:
    """Bỏ thẻ điều khiển, ký tự đặc biệt ([]<>{}`...), xuống dòng; rút gọn độ dài."""
    text = _TED_TAG.sub(" ", text)
    text = _UNSAFE_CHARS.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()[:max_chars]


def _local(moment: datetime) -> datetime:
    return moment.astimezone()  # naive được hiểu là giờ local


def _hhmm(moment: datetime) -> str:
    return _local(moment).strftime("%H:%M")


@dataclass
class BriefingInput:
    tasks: list[str] = field(default_factory=list)
    events: list[tuple[datetime, str]] = field(default_factory=list)
    stale_rocks: list[tuple[str, int]] = field(default_factory=list)  # (tiêu đề, số ngày)
    slot: str = "morning"  # "morning" | "midday"
    important_emails: list[tuple[str, str, str]] = field(default_factory=list)  # (người gửi, tiêu đề, ý chính)
    low_email_count: int = 0
    email_failed: bool = False  # True: có yêu cầu đọc email nhưng Hermes không trả được

    def __post_init__(self):
        self.tasks = [t for t in (sanitize_untrusted_text(t) for t in self.tasks) if t]
        cleaned = [(start, sanitize_untrusted_text(title) or "(không tên)") for start, title in self.events]
        self.events = sorted(cleaned, key=lambda e: _local(e[0]))
        self.stale_rocks = [(sanitize_untrusted_text(t) or "(không tên)", d) for t, d in self.stale_rocks]
        # Email là dữ liệu ngoài không tin cậy: cùng bộ lọc với lịch họp
        self.important_emails = [tuple(sanitize_untrusted_text(x) for x in mail) for mail in self.important_emails]

    def apply_email_digest(self, digest, max_items: int = 8) -> None:
        """digest: EmailDigestResponse hoặc None (None = không đọc được). Quan trọng liệt kê (tối đa max_items),
        ít quan trọng chỉ đếm = max(số low Hermes trả, total_unread - số quan trọng) để không hụt khi Hermes cắt bớt."""
        if digest is None:
            self.email_failed = True
            return
        self.email_failed = False
        important = [e for e in digest.emails if e.priority == "important"]
        self.important_emails = [
            tuple(sanitize_untrusted_text(x) for x in (e.sender, e.subject, e.summary))
            for e in important[: max(0, max_items)]
        ]
        low = len(digest.emails) - len(important)
        self.low_email_count = max(low, digest.total_unread - len(important), 0)


def _email_sentence(inp: BriefingInput) -> str:
    if inp.email_failed:
        return "Em chưa đọc được email."
    if not inp.important_emails and not inp.low_email_count:
        return ""
    parts = []
    if inp.important_emails:
        shown = inp.important_emails[:MAX_SPOKEN_EMAILS]
        listed = ", ".join(f"{sender}: {subject}".strip(": ") for sender, subject, _ in shown)
        more = len(inp.important_emails) - len(shown)
        parts.append(f"Có {len(inp.important_emails)} email quan trọng: {listed}{f' và {more} email nữa' if more else ''}.")
    if inp.low_email_count:
        parts.append(f"Còn {inp.low_email_count} email ít quan trọng.")
    return " ".join(parts)


def build_local_briefing_text(inp: BriefingInput) -> str:
    midday = inp.slot == "midday"
    parts = []
    if inp.tasks:
        parts.append(f"{'Chiều nay việc quan trọng còn lại là' if midday else 'Hôm nay của anh là'} {', '.join(inp.tasks)}.")
    elif midday:
        parts.append("Chiều nay không còn việc quan trọng nào đang chờ.")
    else:
        parts.append("Hôm nay chưa có việc nào trong danh sách, anh thêm một việc để Ted theo cùng nha!")
    if inp.events:
        meetings = ", ".join(f"{_hhmm(start)} {title}" for start, title in inp.events)
        parts.append(f"Có {len(inp.events)} cuộc họp: {meetings}.")
    else:
        parts.append("Chiều nay chưa có lịch họp nào." if midday else "Hôm nay chưa có lịch họp nào.")
    if email_line := _email_sentence(inp):
        parts.append(email_line)
    parts.extend(f"Rock '{title}' đã treo {days} ngày rồi đó!" for title, days in inp.stale_rocks)
    return " ".join(parts)


def _bullets(lines: list[str]) -> str:
    return "\n".join(f"- {line}" for line in lines) if lines else "(không có)"


def _email_prompt_lines(inp: BriefingInput) -> str:
    if inp.email_failed:
        return "(không đọc được email)"
    lines = [f"[quan trọng] {sender} | {subject} | {summary}" for sender, subject, summary in inp.important_emails]
    if inp.low_email_count:
        lines.append(f"[ít quan trọng] {inp.low_email_count} email (chỉ nêu số lượng)")
    return _bullets(lines)


def briefing_prompt_values(inp: BriefingInput, now: Optional[datetime] = None) -> dict[str, str]:
    now = now or datetime.now()
    return {
        "tasks": _bullets(inp.tasks),
        "events": _bullets([f"{_hhmm(s)} {t}" for s, t in inp.events]),
        "rocks": _bullets([f"{t} (treo {d} ngày)" for t, d in inp.stale_rocks]),
        "now": now.strftime("%Y-%m-%d %H:%M"),
        "slot": inp.slot,
        "emails": _email_prompt_lines(inp),
    }
