"""HTML cho khung chat Quick Chat theo Synthetic Nexus (màu lấy từ design_tokens, không hard-code).
QTextEdit chỉ hỗ trợ tập con HTML/CSS: dùng <table> + bgcolor/border-left thay cho <div>."""

from html import escape

from src.ui.theme.design_tokens import PRIMARY, PRIMARY_SOFT, SURFACE_RAISED, TERTIARY, TEXT, WARNING


def user_message_html(text: str) -> str:
    """Tin của người dùng: khối nền L2 + vạch trái cyan 2px (Conversational Elements)."""
    return (
        f"<table width='100%' cellspacing='0' cellpadding='0' style='margin-top:8px; margin-bottom:4px;'><tr>"
        f"<td width='2' bgcolor='{PRIMARY}'></td>"
        f"<td bgcolor='{SURFACE_RAISED}' style='padding:8px 10px; color:{TEXT};'>"
        f"<b style='color:{PRIMARY_SOFT};'>Bạn:</b> {escape(text)}</td></tr></table>"
    )


def assistant_open_html() -> str:
    """Mở đoạn trả lời của Ted (phẳng, không viền); token stream sẽ được chèn tiếp vào cuối đoạn này."""
    return f"<p style='color:{TEXT}; margin-top:6px;'><b style='color:{PRIMARY_SOFT};'>Ted:</b> "


def notice_html(body_html: str, tone: str = "warning") -> str:
    """Thông báo hệ thống của Ted. tone: warning = lỗi/nhắc nhở, success = xác nhận hoàn thành (lime),
    info = thông tin trung tính (chào, đã đỗ ý tưởng, đã dừng). `body_html` phải được escape sẵn bởi nơi gọi."""
    color = {"warning": WARNING, "success": TERTIARY, "info": PRIMARY_SOFT}[tone]
    return f"<p style='color:{color};'>{body_html}</p>"
