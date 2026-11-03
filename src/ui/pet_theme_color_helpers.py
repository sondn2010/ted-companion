"""Tiện ích màu cho UI vẽ tay của pet (QPainter): đổi design token (hex hoặc rgba CSS) sang QColor."""

from typing import Optional

from PySide6.QtGui import QColor


def qcolor(token: str, alpha: Optional[float] = None) -> QColor:
    """Token '#RRGGBB' hoặc 'rgba(r, g, b, a)' → QColor; `alpha` (0..1) ghi đè độ trong suốt nếu có."""
    if token.startswith("rgba"):
        r, g, b, a = (p.strip() for p in token[token.index("(") + 1:token.rindex(")")].split(","))
        color = QColor(int(r), int(g), int(b))
        color.setAlphaF(float(a))
    else:
        color = QColor(token)
    if alpha is not None:
        color.setAlphaF(alpha)
    return color
