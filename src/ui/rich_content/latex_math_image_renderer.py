"""Vẽ công thức LaTeX thành ảnh PNG (matplotlib mathtext) nhúng data-URI vào HTML của QTextEdit / QLabel.

- Ảnh vẽ ở 2x rồi khai báo width/height 1x → nét chữ sắc trên màn hình Retina/HiDPI.
- Môi trường nhiều dòng mathtext không hỗ trợ (cases / aligned / matrix …) được ráp bằng bảng HTML,
  mỗi ô là 1 ảnh công thức: hệ phương trình có dấu ngoặc nhọn, ma trận có ngoặc tròn/vuông.
- Lỗi cú pháp / thiếu matplotlib → hiện chữ Unicode dễ đọc (latex_unicode_fallback), KHÔNG làm vỡ khung chat.
- import matplotlib rất chậm (~5s lần đầu) → `warm_up_in_background()` khi khởi động app.
"""

import base64
from functools import lru_cache
from html import escape
import io
import logging
import re
import struct
import threading
from typing import Optional

from src.config import get_resource_path
from src.ui.rich_content.latex_unicode_fallback import latex_to_unicode, wrap_math_glyphs
from src.ui.theme import design_tokens as tk

logger = logging.getLogger("ted")

_LOCK = threading.Lock()   # mathtext không thread-safe; warm-up chạy ở luồng nền
_WARMING = threading.Event()   # đang nạp matplotlib ở nền → không chặn UI, tạm hiện chữ Unicode
MAX_LATEX_CHARS = 400          # công thức dài / lồng sâu bất thường → chữ Unicode (tránh treo UI)
MAX_BRACE_DEPTH = 12
_ENV_RE = re.compile(r"\\begin\{(cases|aligned|align\*?|gathered|split|array|matrix|[pbvB]matrix)\}(\{[^}]*\})?(.*?)\\end\{\1\}", re.S)
_BRACKETS = {"cases": ("{", ""), "pmatrix": ("(", ")"), "bmatrix": ("[", "]"), "vmatrix": ("|", "|"), "Bmatrix": ("{", "}")}
# Lệnh LaTeX phổ biến mathtext chưa biết → đổi sang tương đương
_REWRITES = (
    (re.compile(r"\\(?:displaystyle|textstyle|limits|nolimits)\b"), ""),
    (re.compile(r"\\left\s*\."), ""), (re.compile(r"\\right\s*\."), ""),
    (re.compile(r"\\(?:le|leq)slant\b"), r"\\leq"), (re.compile(r"\\(?:ge|geq)slant\b"), r"\\geq"),
    (re.compile(r"\\le\b"), r"\\leq"), (re.compile(r"\\ge\b"), r"\\geq"), (re.compile(r"\\ne\b"), r"\\neq"),
    (re.compile(r"\\degree\b"), r"^{\\circ}"), (re.compile(r"\\tfrac\b"), r"\\frac"),
    (re.compile(r"\\iff\b"), r"\\Leftrightarrow"), (re.compile(r"\\implies\b"), r"\\Rightarrow"),
    (re.compile(r"\\text(?:bf|it|rm)?\b"), r"\\text"), (re.compile(r"\\operatorname\b"), r"\\mathrm"),
)


def _math_rc() -> dict:
    """Chữ số / chữ cái dùng font của app (Be Vietnam Pro) → rõ nét, đồng bộ với chữ trong khung chat.
    Ký hiệu font app không có (∑, ngoặc lớn…) lấy từ bộ STIX Sans của matplotlib."""
    from matplotlib import font_manager

    fonts_dir = get_resource_path("assets/fonts")
    files = [fonts_dir / f"BeVietnamPro-{w}.ttf" for w in ("Regular", "Italic", "SemiBold")]
    if not all(f.exists() for f in files):
        return {}
    for f in files:
        font_manager.fontManager.addfont(str(f))
    return {
        "mathtext.fontset": "custom",
        "mathtext.rm": "Be Vietnam Pro",
        "mathtext.it": "Be Vietnam Pro:italic",
        "mathtext.bf": "Be Vietnam Pro:semibold",
        "mathtext.fallback": "stixsans",
    }


_RC: Optional[dict] = None


def _draw_png(expr: str, size_pt: float, color: str) -> bytes:
    """Như matplotlib.mathtext.math_to_image nhưng nền TRONG SUỐT (hợp giao diện tối)."""
    # import muộn: chỉ tốn thời gian khi thật sự có công thức
    import matplotlib
    from matplotlib.figure import Figure
    from matplotlib.font_manager import FontProperties

    global _RC
    if _RC is None:
        _RC = _math_rc()
    with matplotlib.rc_context(_RC):
        fig = Figure(figsize=(0.1, 0.1))
        fig.text(0, 0, expr, fontproperties=FontProperties(size=size_pt), color=color)
        buf = io.BytesIO()
        # bbox "tight" + lề nhỏ: không cắt mất gạch ngang của dấu căn / mũ / gạch trên
        fig.savefig(buf, dpi=96, format="png", transparent=True, bbox_inches="tight", pad_inches=size_pt / 96 * 0.12)
    return buf.getvalue()


def warm_up_in_background() -> None:
    """Nạp matplotlib + dựng cache font ở luồng nền để công thức đầu tiên trong chat hiện ngay."""
    def _run():
        try:
            render_math_png("x^2", 12, tk.TEXT)
        except Exception as exc:   # thiếu matplotlib vẫn chạy được (fallback Unicode)
            logger.info("Bỏ qua warm-up công thức toán: %s", exc)
        finally:
            _WARMING.clear()
    _WARMING.set()
    threading.Thread(target=_run, name="math-warmup", daemon=True).start()


def _png_size(data: bytes) -> tuple[int, int]:
    return struct.unpack(">II", data[16:24])


def _prepare(latex: str) -> str:
    s = latex.strip()
    for pattern, repl in _REWRITES:
        s = pattern.sub(repl, s)
    return s


@lru_cache(maxsize=512)
def render_math_png(latex: str, font_px: int, color: str) -> Optional[bytes]:
    """PNG 2x của 1 công thức 1 dòng; None nếu mathtext không dựng được."""
    import matplotlib   # noqa: F401  (ImportError → nơi gọi chuyển sang chữ Unicode)
    with _LOCK:
        try:
            return _draw_png(f"${_prepare(latex)}$", font_px * 0.75 * 2, color)   # px→pt ở dpi 96, vẽ 2x
        except Exception as exc:
            logger.debug("mathtext không dựng được %r: %s", latex, exc)
            return None


def _img_tag(png: bytes, max_width: int, inline: bool) -> str:
    width, height = _png_size(png)
    width, height = max(1, width // 2), max(1, height // 2)
    if width > max_width:   # công thức quá dài: thu nhỏ vừa khung chat
        height, width = max(1, height * max_width // width), max_width
    valign = " style='vertical-align: middle;'" if inline else ""
    uri = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
    return f"<img src='{uri}' width='{width}' height='{height}'{valign}>"


def _fallback(latex: str) -> str:
    return f"<span style='font-style:italic; color:{tk.PRIMARY_SOFT};'>{wrap_math_glyphs(escape(latex_to_unicode(latex)))}</span>"


def _too_complex(latex: str) -> bool:
    depth = deepest = 0
    for ch in latex:
        depth += (ch == "{") - (ch == "}")
        deepest = max(deepest, depth)
    return len(latex) > MAX_LATEX_CHARS or deepest > MAX_BRACE_DEPTH


def _single(latex: str, font_px: int, color: str, max_width: int, inline: bool) -> str:
    if not latex.strip():
        return ""
    if _WARMING.is_set() or _too_complex(latex):
        return _fallback(latex)
    try:
        png = render_math_png(latex.strip(), font_px, color)
    except Exception:   # ImportError: chưa cài matplotlib
        png = None
    return _img_tag(png, max_width, inline) if png else _fallback(latex)


def _environment_table(env: str, body: str, font_px: int, color: str, max_width: int) -> str:
    rows = [r for r in re.split(r"\\\\(?:\[[^\]]*\])?", body) if r.strip()]
    cells = [[c for c in r.split("&")] for r in rows]
    left, right = _BRACKETS.get(env, ("", ""))
    align_pair = env in ("aligned", "align", "align*", "split")
    html_rows = []
    for row in cells:
        tds = []
        for idx, cell in enumerate(row):
            align = ("right" if idx % 2 == 0 else "left") if align_pair else ("left" if env == "cases" else "center")
            tds.append(f"<td align='{align}' style='padding:2px 6px;'>{_single(cell, font_px, color, max_width, False)}</td>")
        html_rows.append(f"<tr>{''.join(tds)}</tr>")
    inner = f"<table cellspacing='0' cellpadding='0'>{''.join(html_rows)}</table>"
    if not (left or right):
        return inner
    size = max(2, len(rows)) * font_px * 1.25

    def bracket(ch: str) -> str:
        return (f"<td valign='middle' style='font-size:{size:.0f}px; color:{color}; padding:0 2px;'>{escape(ch)}</td>"
                if ch else "")
    return (f"<table cellspacing='0' cellpadding='0'><tr>{bracket(left)}"
            f"<td valign='middle'>{inner}</td>{bracket(right)}</tr></table>")


def math_html(latex: str, *, display: bool, color: str = tk.TEXT, font_px: int = 14, max_width: int = 360) -> str:
    """HTML cho 1 công thức. display=True → khối riêng căn giữa; False → ảnh nằm trong dòng chữ."""
    size = font_px + 3 if display else font_px
    if display:   # công thức riêng dòng: phân số cỡ đầy đủ thay vì thu nhỏ như trong dòng chữ
        latex = re.sub(r"\\frac\b", r"\\dfrac", latex)
    if not _ENV_RE.search(latex):
        img = _single(latex, size, color, max_width, inline=not display)
        return f"<p align='center'>{img}</p>" if display else img
    parts, last = [], 0
    for m in _ENV_RE.finditer(latex):   # "A = \begin{pmatrix}…\end{pmatrix}" → [ảnh "A ="][bảng ma trận][…]
        parts.append(_single(latex[last:m.start()], size, color, max_width, False))
        parts.append(_environment_table(m.group(1), m.group(3), size, color, max_width))
        last = m.end()
    parts.append(_single(latex[last:], size, color, max_width, False))
    tds = "".join(f"<td valign='middle'>{p}</td>" for p in parts if p)
    return f"<table align='center' cellspacing='0' cellpadding='0' style='margin:4px 0;'><tr>{tds}</tr></table>"
