import math

from PySide6.QtCore import QRect, QRectF, Qt
from PySide6.QtGui import QFont, QFontMetrics, QPainter, QPainterPath, QPen
from src.core.focus_engine import FocusState
from src.ui.pet_level_chip import paint_level_chip
from src.ui.pet_theme_color_helpers import qcolor
from src.ui.theme import design_tokens as tk


def _elide_two_lines(text: str, fm: QFontMetrics, width: int) -> str:
    """Rút gọn `text` (thêm "…") cho vừa 2 dòng word-wrap trong bề rộng `width`."""
    max_h = fm.lineSpacing() * 2

    def fits(s: str) -> bool:
        return fm.boundingRect(QRect(0, 0, width, 1000), Qt.TextFlag.TextWordWrap, s).height() <= max_h

    if fits(text):
        return text
    cut = len(text)
    while cut > 1 and not fits(text[:cut].rstrip() + "…"):
        cut -= 1
    return text[:cut].rstrip() + "…"


def countdown_text(remaining_seconds: int) -> str:
    mins, secs = divmod(max(0, remaining_seconds), 60)
    return f"{mins:02d}:{secs:02d}"


def meeting_elapsed_text(elapsed_seconds: int) -> str:
    """Đồng hồ đếm lên của buổi họp: mm:ss, từ 1 giờ trở lên h:mm:ss."""
    hours, rest = divmod(max(0, elapsed_seconds), 3600)
    mins, secs = divmod(rest, 60)
    return f"{hours}:{mins:02d}:{secs:02d}" if hours else f"{mins:02d}:{secs:02d}"


def paint_companion(painter: QPainter, widget) -> None:
    """Vẽ pill đồng hồ + nhân vật Chibi lên `widget` (TedCompanionWidget): đọc focus_engine, pixmap/svg, pha thở, bounce."""
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    engine = widget.focus_engine

    pill_rect = QRectF(88, 22, 200, 106)
    path = QPainterPath()
    path.addRoundedRect(pill_rect, 18, 18)

    painter.fillPath(path, qcolor(tk.SURFACE_OVERLAY, 0.92))
    # Đang tập trung: viền tertiary (trạng thái hoạt động); còn lại: viền secondary mờ
    in_meeting = engine.state == FocusState.MEETING_RUNNING
    border_color = (qcolor(tk.TERTIARY, 0.8) if in_meeting or engine.state == FocusState.DEEP_WORK_RUNNING
                    else qcolor(tk.OUTLINE_SECONDARY))
    painter.setPen(QPen(border_color, 1.5))
    painter.drawPath(path)

    painter.setPen(qcolor(tk.TEXT))
    painter.setFont(QFont(tk.FONT_FAMILY, 18, QFont.Weight.DemiBold))
    painter.drawText(QRectF(90, 25, 196, 28), Qt.AlignmentFlag.AlignCenter,
                     meeting_elapsed_text(engine.elapsed_seconds) if in_meeting else countdown_text(engine.remaining_seconds))
    if in_meeting:   # chế độ Họp: dùng chung hình FOCUS + dấu 👥 nhỏ ở góc pill (đồng hồ đếm lên)
        painter.setFont(QFont(tk.FONT_FAMILY, 12))
        painter.drawText(QRectF(94, 27, 24, 24), Qt.AlignmentFlag.AlignCenter, "👥")

    # Tên task: tối đa 2 dòng (xuống dòng theo từ), quá dài thì cắt "…" ở cuối dòng 2
    painter.setPen(qcolor(tk.TEXT_MUTED))
    font = QFont(tk.FONT_FAMILY, 9)
    painter.setFont(font)
    title_rect = QRectF(96, 54, 184, 34)
    painter.drawText(title_rect, Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                     _elide_two_lines(engine.active_task_title, QFontMetrics(font), int(title_rect.width())))


    phase = widget._breath_phase
    dy = math.sin(phase) * 2.6
    breath_sx = 1.0 + math.cos(phase) * 0.022
    breath_sy = 1.0 - math.cos(phase) * 0.022
    tilt_angle = math.sin(phase * 0.5) * 2.0

    painter.save()
    painter.translate(54.0, 60.0 + dy)
    painter.scale(breath_sx * widget._bounce_scale, breath_sy * widget._bounce_scale)
    painter.rotate(tilt_angle)

    avatar_rect = QRectF(-48, -48, 96, 96)
    if widget._current_pixmap and not widget._current_pixmap.isNull():
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        # Giữ tỉ lệ ảnh (ảnh Character Pack có thể là 1024x1536), căn giữa trong ô avatar
        size = widget._current_pixmap.size().scaled(avatar_rect.size().toSize(), Qt.AspectRatioMode.KeepAspectRatio)
        target = QRectF(0, 0, size.width(), size.height())
        target.moveCenter(avatar_rect.center())
        painter.drawPixmap(target.toRect(), widget._current_pixmap)
    elif widget.svg_renderer.isValid():
        widget.svg_renderer.render(painter, avatar_rect)
    painter.restore()
    paint_level_chip(painter, widget.level_chip())   # chip "Lv6" (None = chưa có Hub → không vẽ)
