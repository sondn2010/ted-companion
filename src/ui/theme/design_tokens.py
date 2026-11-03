"""
Design tokens "Synthetic Nexus" (docs/UI/DESIGN.md, docs/UI/style-guideline.md) — nguồn màu/cỡ chữ/bo góc duy nhất.

QSS (src/ui/theme/qss/*.qss) viết `@TÊN_TOKEN` thay cho hex, app_theme_loader thay giá trị lúc nạp;
code Python (QPainter, HTML transcript) PHẢI import từ đây thay vì viết hex cứng.
"""

# ── Surfaces (tonal layering, tối → sáng) ────────────────────────────────────
CANVAS = "#0E1012"            # Level 0: nền sâu dưới vùng cuộn
SURFACE = "#121416"           # Nền cửa sổ / trang nội dung
SURFACE_LOW = "#1A1C1E"       # Level 1: sidebar, khung chat, composer dock
SURFACE_ALT = "#1E2124"       # Level 1: dòng xen kẽ trong bảng
SURFACE_RAISED = "#212428"    # Level 2: card, bubble người dùng, code block, input
SURFACE_OVERLAY = "#282B30"   # Level 3: menu, dropdown, tooltip, popup nổi
SURFACE_REASONING = "#15181C" # Khối "suy nghĩ" / disclosure

# ── Text ─────────────────────────────────────────────────────────────────────
TEXT = "#F0F4F8"              # chữ chính
TEXT_MUTED = "#94A3B8"        # telemetry, timestamp, gợi ý
TEXT_DISABLED = "#5B6573"

# ── Accents ──────────────────────────────────────────────────────────────────
PRIMARY = "#00ADEF"           # electric cyan: hành động chính, focus, nav đang chọn
PRIMARY_HOVER = "#33BEF2"
PRIMARY_SOFT = "#83CFFF"      # chữ cyan trên nền tối (link, tiêu đề phụ)
ON_PRIMARY = "#0E1012"
SECONDARY = "#3F51B5"         # deep indigo: viền cấu trúc, badge model/mode
SECONDARY_SOFT = "#BAC3FF"
TERTIARY = "#A2D149"          # lime: CHỈ cho trạng thái hợp lệ/hoàn thành/online
ERROR = "#FFB4AB"
ERROR_CONTAINER = "#93000A"
ERROR_TINT = "rgba(255, 180, 171, 0.08)"            # nền nút Danger
ERROR_BORDER = "rgba(255, 180, 171, 0.4)"
ERROR_CONTAINER_HOVER = "rgba(147, 0, 10, 0.55)"    # hover nút Danger
ON_ERROR_HOVER = "#FFDAD6"
WARNING = "#E8B45A"           # ngữ nghĩa: CHỈ banner/nhãn cảnh báo, viền bubble nhắc nhở — không dùng cho nút
WARNING_TINT = "rgba(232, 180, 90, 0.08)"
WARNING_BORDER = "rgba(232, 180, 90, 0.45)"
TERTIARY_TINT = "rgba(162, 209, 73, 0.12)"          # nền StatusPill

# ── Outlines (rgba để chồng lên mọi surface) ────────────────────────────────
OUTLINE_SUBTLE = "rgba(255, 255, 255, 0.06)"   # Level 1
OUTLINE = "rgba(255, 255, 255, 0.08)"          # Level 2
OUTLINE_HOVER = "rgba(255, 255, 255, 0.16)"    # hover input
OUTLINE_STRONG = "#3E4850"
OUTLINE_SECONDARY = "rgba(63, 81, 181, 0.35)"  # nút secondary / menu / tooltip
OUTLINE_SECONDARY_HOVER = "rgba(63, 81, 181, 0.6)"
OUTLINE_SECONDARY_SUBTLE = "rgba(63, 81, 181, 0.25)"  # InfoPanel
FOCUS_RING = "rgba(0, 173, 239, 0.4)"
HOVER_TINT = "rgba(255, 255, 255, 0.05)"
PRIMARY_TINT = "rgba(0, 173, 239, 0.12)"       # nền "đang bật": nav, segment, nút checkable
SELECTED_TINT = "rgba(0, 173, 239, 0.16)"      # nền item đang chọn: list, menu, combo
SELECTION = "rgba(0, 173, 239, 0.35)"          # bôi đen chữ
PRIMARY_DISABLED = "rgba(0, 173, 239, 0.25)"
ON_PRIMARY_DISABLED = "rgba(14, 16, 18, 0.7)"
SCROLL_HANDLE = "rgba(255, 255, 255, 0.12)"
SCROLL_HANDLE_HOVER = "rgba(255, 255, 255, 0.22)"

# ── Ma trận Eisenhower: màu phẳng riêng, CHỈ dùng trong ma trận ─────────────
QUADRANT_Q1 = "#E85D6C"       # Làm ngay
QUADRANT_Q2 = "#E9B949"       # Lên lịch
QUADRANT_Q3 = "#8C7B6B"       # Giao việc
QUADRANT_Q4 = "#4FB386"       # Loại bỏ
MATRIX_CARD = "rgba(255, 255, 255, 0.92)"   # thẻ task trên ô màu
MATRIX_CARD_HOVER = "#FFFFFF"
MATRIX_CARD_TEXT = "#1F2328"
MATRIX_AXIS = "#F4F5F7"
MATRIX_DROPZONE = "rgba(255, 255, 255, 0.45)"

# ── Shape (px) ───────────────────────────────────────────────────────────────
RADIUS_SM = 4
RADIUS_CONTROL = 8   # nút, input, chip
RADIUS_CARD = 16     # card, code block, bubble
RADIUS_DIALOG = 24
RADIUS_PILL = 999

# ── Spacing (px) ─────────────────────────────────────────────────────────────
SPACE_XS = 4
SPACE_SM = 8
SPACE_MD = 16
SPACE_LG = 24
SPACE_XL = 32

# ── Typography ───────────────────────────────────────────────────────────────
FONT_FAMILY = "Be Vietnam Pro"  # thiết kế cho tiếng Việt, đóng gói trong assets/fonts
FONT_STACK = '"Be Vietnam Pro", "Segoe UI", "SF Pro Text", "Helvetica Neue", Arial, sans-serif'
MONO_STACK = 'ui-monospace, "SFMono-Regular", "Cascadia Mono", Consolas, monospace'
# (px, weight) theo thang DESIGN.md
HEADLINE_LG = (28, 600)
HEADLINE_MD = (20, 500)
TITLE_SM = (16, 600)
BODY_LG = (16, 400)
BODY_MD = (14, 400)
BODY_SM = (12, 400)
LABEL_MD = (13, 500)
LABEL_SM = (11, 600)

# ── Layout ───────────────────────────────────────────────────────────────────
SIDEBAR_WIDTH = 256
SIDEBAR_RAIL_WIDTH = 64
