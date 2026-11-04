#!/usr/bin/env python3
"""
Bộ tạo ảnh Vector SVG Chibi Kawaii phong phú cho Ted Companion.
Tạo 30 file SVG độ nét cao cho 6 nhân vật:
  - cat (Mèo Ted)
  - owl (Cú Đêm)
  - panda (Gấu Trúc)
  - shiba (Cún Shiba)
  - bunny (Thỏ Bông)
  - penguin (Cánh Cụt)
Tương ứng với 5 biểu cảm: idle, focus, nudge, cheer, rest.
Kèm các file alias 'ted_*' trỏ tới 'cat_*'.
"""

from pathlib import Path

ANIMATIONS_DIR = Path(__file__).resolve().parent.parent / "assets" / "animations"
ANIMATIONS_DIR.mkdir(parents=True, exist_ok=True)


def get_defs():
    return """  <defs>
    <!-- Background Gradients -->
    <radialGradient id="bgIdle" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="#2D3142" stop-opacity="0.95"/>
      <stop offset="100%" stop-color="#191B24" stop-opacity="0.98"/>
    </radialGradient>
    <radialGradient id="bgFocus" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="#143628" stop-opacity="0.95"/>
      <stop offset="100%" stop-color="#081C15" stop-opacity="0.98"/>
    </radialGradient>
    <radialGradient id="bgNudge" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="#3A2352" stop-opacity="0.95"/>
      <stop offset="100%" stop-color="#1C112A" stop-opacity="0.98"/>
    </radialGradient>
    <radialGradient id="bgCheer" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="#4A2840" stop-opacity="0.95"/>
      <stop offset="100%" stop-color="#251222" stop-opacity="0.98"/>
    </radialGradient>
    <radialGradient id="bgRest" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="#1C2D44" stop-opacity="0.95"/>
      <stop offset="100%" stop-color="#0D1826" stop-opacity="0.98"/>
    </radialGradient>

    <!-- Shading Gradients -->
    <linearGradient id="blushPink" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#FF9EAA" stop-opacity="0.75"/>
      <stop offset="100%" stop-color="#FF6B8B" stop-opacity="0.45"/>
    </linearGradient>
    <linearGradient id="goldGlow" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#FFE066"/>
      <stop offset="100%" stop-color="#F77F00"/>
    </linearGradient>
    <linearGradient id="cyberGreen" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#70E000"/>
      <stop offset="100%" stop-color="#38B000"/>
    </linearGradient>
  </defs>"""


def get_badge(mood: str):
    stroke_colors = {
        "idle": ("url(#bgIdle)", "#7AA2F7"),
        "focus": ("url(#bgFocus)", "#52B788"),
        "nudge": ("url(#bgNudge)", "#BB9AF7"),
        "cheer": ("url(#bgCheer)", "#FF9E64"),
        "rest": ("url(#bgRest)", "#7DCFFF"),
    }
    bg, stroke = stroke_colors.get(mood, stroke_colors["idle"])
    return f'  <circle cx="60" cy="62" r="48" fill="{bg}" stroke="{stroke}" stroke-width="3"/>'


# ---------------------------------------------------------------------------
# CHIBI EYES BUILDER
# ---------------------------------------------------------------------------
def make_eyes(mood: str, left_cx=43, right_cx=77, cy=63, r=6.5, iris_color="#22223B"):
    """Tạo mắt anime chibi lấp lánh hoặc nhắm mắt theo mood."""
    if mood == "cheer":
        # Mắt cười híp tít chữ U ngược
        return f"""    <path d="M {left_cx-6} {cy+1} Q {left_cx} {cy-7} {left_cx+6} {cy+1}" fill="none" stroke="{iris_color}" stroke-width="3" stroke-linecap="round"/>
    <path d="M {right_cx-6} {cy+1} Q {right_cx} {cy-7} {right_cx+6} {cy+1}" fill="none" stroke="{iris_color}" stroke-width="3" stroke-linecap="round"/>"""
    elif mood == "rest":
        # Mắt nhắm ngủ thanh bình
        return f"""    <path d="M {left_cx-6} {cy+2} Q {left_cx} {cy+7} {left_cx+6} {cy+2}" fill="none" stroke="{iris_color}" stroke-width="2.8" stroke-linecap="round"/>
    <path d="M {right_cx-6} {cy+2} Q {right_cx} {cy+7} {right_cx+6} {cy+2}" fill="none" stroke="{iris_color}" stroke-width="2.8" stroke-linecap="round"/>"""
    elif mood == "nudge":
        # Mắt to tròn nhìn hơi liếc tò mò
        return f"""    <circle cx="{left_cx+1}" cy="{cy}" r="{r+0.5}" fill="{iris_color}"/>
    <circle cx="{right_cx+1}" cy="{cy}" r="{r+0.5}" fill="{iris_color}"/>
    <!-- Điểm sáng mắt Anime -->
    <circle cx="{left_cx+3}" cy="{cy-2}" r="2.8" fill="#FFFFFF"/>
    <circle cx="{right_cx+3}" cy="{cy-2}" r="2.8" fill="#FFFFFF"/>
    <circle cx="{left_cx}" cy="{cy+2.5}" r="1.3" fill="#FFFFFF"/>
    <circle cx="{right_cx}" cy="{cy+2.5}" r="1.3" fill="#FFFFFF"/>"""
    else:
        # Mắt to tròn lấp lánh Anime chuẩn (idle / focus)
        return f"""    <ellipse cx="{left_cx}" cy="{cy}" rx="{r}" ry="{r*1.1}" fill="{iris_color}"/>
    <ellipse cx="{right_cx}" cy="{cy}" rx="{r}" ry="{r*1.1}" fill="{iris_color}"/>
    <!-- Lấp lánh lớn -->
    <circle cx="{left_cx-1.5}" cy="{cy-2.5}" r="2.6" fill="#FFFFFF"/>
    <circle cx="{right_cx-1.5}" cy="{cy-2.5}" r="2.6" fill="#FFFFFF"/>
    <!-- Lấp lánh nhỏ -->
    <circle cx="{left_cx+2}" cy="{cy+2.5}" r="1.3" fill="#FFFFFF"/>
    <circle cx="{right_cx+2}" cy="{cy+2.5}" r="1.3" fill="#FFFFFF"/>"""


def make_blush(left_cx=31, right_cx=89, cy=73, rx=6.5, ry=4):
    return f"""    <ellipse cx="{left_cx}" cy="{cy}" rx="{rx}" ry="{ry}" fill="url(#blushPink)"/>
    <ellipse cx="{right_cx}" cy="{cy}" rx="{rx}" ry="{ry}" fill="url(#blushPink)"/>"""


# ---------------------------------------------------------------------------
# PHỤ KIỆN THEO MOOD
# ---------------------------------------------------------------------------
def make_mood_props(mood: str, char_type: str):
    if mood == "focus":
        # Tai nghe gaming chụp tai siêu ngầu có đèn LED
        headphone_color = "#52B788" if char_type != "owl" else "#7AA2F7"
        return f"""    <!-- Focus Gaming Headphones -->
    <path d="M 22 58 A 40 38 0 0 1 98 58" fill="none" stroke="{headphone_color}" stroke-width="5" stroke-linecap="round"/>
    <!-- Đệm tai nghe trái/phải -->
    <rect x="15" y="48" width="10" height="24" rx="5" fill="#1E293B" stroke="{headphone_color}" stroke-width="2"/>
    <rect x="95" y="48" width="10" height="24" rx="5" fill="#1E293B" stroke="{headphone_color}" stroke-width="2"/>
    <!-- Đèn LED tai nghe -->
    <circle cx="20" cy="60" r="3" fill="#00F5D4"/>
    <circle cx="100" cy="60" r="3" fill="#00F5D4"/>
    <!-- Kính cận tập trung nhỏ -->
    <circle cx="43" cy="63" r="11" fill="none" stroke="#64748B" stroke-width="1.8"/>
    <circle cx="77" cy="63" r="11" fill="none" stroke="#64748B" stroke-width="1.8"/>
    <line x1="54" y1="63" x2="66" y2="63" stroke="#64748B" stroke-width="1.8"/>"""
    elif mood == "nudge":
        # Dấu chấm hỏi lấp lánh và giọt mồ hôi tò mò
        return """    <!-- Nudge Question mark -->
    <g transform="translate(86, 18) scale(0.75)">
      <circle cx="12" cy="12" r="13" fill="#F72585"/>
      <text x="12" y="18" font-family="Arial, sans-serif" font-size="18" font-weight="bold" fill="#FFFFFF" text-anchor="middle">?</text>
    </g>"""
    elif mood == "cheer":
        # Ngôi sao vàng & hoa giấy ăn mừng
        return """    <!-- Cheer Stars & Sparkles -->
    <polygon points="20,25 22,18 28,19 23,23 25,29 20,25" fill="#FFD166"/>
    <polygon points="100,28 102,21 108,22 103,26 105,32 100,28" fill="#FFD166"/>
    <circle cx="18" cy="45" r="2.5" fill="#EF476F"/>
    <circle cx="104" cy="48" r="2.5" fill="#06D6A0"/>
    <path d="M 28 36 Q 32 30 36 36" fill="none" stroke="#118AB2" stroke-width="2" stroke-linecap="round"/>
    <path d="M 84 36 Q 88 30 92 36" fill="none" stroke="#FFD166" stroke-width="2" stroke-linecap="round"/>"""
    elif mood == "rest":
        # Cốc trà sữa/cà phê ấm hoặc chữ Zzz ngủ
        return """    <!-- Sleepy Zzz -->
    <g fill="#A0C4FF" font-family="'Segoe UI', sans-serif" font-weight="bold">
      <text x="88" y="24" font-size="14" opacity="0.95">Z</text>
      <text x="98" y="16" font-size="10" opacity="0.75">z</text>
      <text x="105" y="10" font-size="8" opacity="0.55">z</text>
    </g>"""
    return ""


# ===========================================================================
# 1. MÈO TED (CAT)
# ===========================================================================
def render_cat(mood: str) -> str:
    mouth = """<path d="M 54 75 Q 57 78 60 75 Q 63 78 66 75" fill="none" stroke="#333333" stroke-width="2.2" stroke-linecap="round"/>"""
    if mood == "cheer":
        mouth = """<path d="M 53 73 Q 60 84 67 73 Z" fill="#FF6B6B" stroke="#333333" stroke-width="1.8"/>"""
    elif mood == "focus":
        mouth = """<path d="M 55 76 Q 60 78 65 76" fill="none" stroke="#333333" stroke-width="2" stroke-linecap="round"/>"""

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120" width="120" height="120">
{get_defs()}
{get_badge(mood)}
  <g id="cat_character">
    <!-- Tai mèo mềm mại -->
    <path d="M 24 50 L 16 16 Q 34 26 44 34 Z" fill="#FFE8D6" stroke="#4A4E69" stroke-width="2.5" stroke-linejoin="round"/>
    <path d="M 96 50 L 104 16 Q 86 26 76 34 Z" fill="#FFE8D6" stroke="#4A4E69" stroke-width="2.5" stroke-linejoin="round"/>
    <!-- Lòng tai hồng đào -->
    <path d="M 26 45 L 21 23 Q 32 30 38 35 Z" fill="#FFB5A7"/>
    <path d="M 94 45 L 99 23 Q 88 30 82 35 Z" fill="#FFB5A7"/>

    <!-- Đầu & Thân mèo Chibi tròn xoe -->
    <ellipse cx="60" cy="65" rx="39" ry="34" fill="#FFFDF9" stroke="#4A4E69" stroke-width="2.5"/>

    <!-- Vết lông cam chibi trên trán -->
    <path d="M 52 32 Q 60 40 68 32 Q 65 42 60 45 Q 55 42 52 32 Z" fill="#F4A261" opacity="0.85"/>

    <!-- Má hồng -->
{make_blush(31, 89, 72, 7, 4)}

    <!-- Râu mèo siêu đáng yêu -->
    <path d="M 20 68 L 32 70 M 20 74 L 32 73" stroke="#9A8C98" stroke-width="1.8" stroke-linecap="round"/>
    <path d="M 100 68 L 88 70 M 100 74 L 88 73" stroke="#9A8C98" stroke-width="1.8" stroke-linecap="round"/>

    <!-- Mắt Anime Chibi -->
{make_eyes(mood, left_cx=43, right_cx=77, cy=62, r=6.2, iris_color="#1D3557")}

    <!-- Mũi tam giác hồng nhỏ -->
    <polygon points="57.5,69 62.5,69 60,72" fill="#E76F51"/>

    <!-- Miệng mèo hình chữ w -->
    {mouth}

    <!-- 2 chân trước giơ lên múp míp -->
    <ellipse cx="44" cy="94" rx="8" ry="6" fill="#FFFDF9" stroke="#4A4E69" stroke-width="2"/>
    <ellipse cx="76" cy="94" rx="8" ry="6" fill="#FFFDF9" stroke="#4A4E69" stroke-width="2"/>

{make_mood_props(mood, "cat")}
  </g>
</svg>"""


# ===========================================================================
# 2. CÚ ĐÊM (OWL)
# ===========================================================================
def render_owl(mood: str) -> str:
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120" width="120" height="120">
{get_defs()}
{get_badge(mood)}
  <g id="owl_character">
    <!-- Tai lông nhọn nhỏ -->
    <polygon points="26,36 30,18 44,30" fill="#BC6C25" stroke="#283618" stroke-width="2" stroke-linejoin="round"/>
    <polygon points="94,36 90,18 76,30" fill="#BC6C25" stroke="#283618" stroke-width="2" stroke-linejoin="round"/>

    <!-- Thân cú tròn vo múp míp -->
    <ellipse cx="60" cy="64" rx="40" ry="36" fill="#DDA15E" stroke="#283618" stroke-width="2.5"/>

    <!-- Bụng lông kem mịn -->
    <ellipse cx="60" cy="74" rx="26" ry="22" fill="#FEFAE0"/>
    <!-- Họa tiết lông bụng chữ v -->
    <path d="M 52 70 Q 56 74 60 70 M 60 70 Q 64 74 68 70 M 56 78 Q 60 82 64 78" fill="none" stroke="#DDA15E" stroke-width="2" stroke-linecap="round"/>

    <!-- 2 vòng mắt to tròn biểu tượng của Cú -->
    <circle cx="43" cy="56" r="15" fill="#FFFFFF" stroke="#BC6C25" stroke-width="2"/>
    <circle cx="77" cy="56" r="15" fill="#FFFFFF" stroke="#BC6C25" stroke-width="2"/>

    <!-- Mắt Anime Chibi -->
{make_eyes(mood, left_cx=43, right_cx=77, cy=56, r=7, iris_color="#606C38")}

    <!-- Má hồng -->
{make_blush(25, 95, 68, 6, 4)}

    <!-- Mỏ cú cam xinh xắn -->
    <polygon points="56,64 64,64 60,72" fill="#E76F51"/>

    <!-- Cánh cú 2 bên ôm bụng -->
    <ellipse cx="23" cy="68" rx="6" ry="16" fill="#BC6C25" transform="rotate(-15 23 68)"/>
    <ellipse cx="97" cy="68" rx="6" ry="16" fill="#BC6C25" transform="rotate(15 97 68)"/>

    <!-- 2 chân cam nhỏ -->
    <ellipse cx="48" cy="98" rx="6" ry="3.5" fill="#E76F51"/>
    <ellipse cx="72" cy="98" rx="6" ry="3.5" fill="#E76F51"/>

{make_mood_props(mood, "owl")}
  </g>
</svg>"""


# ===========================================================================
# 3. GẤU TRÚC (PANDA MOCHI)
# ===========================================================================
def render_panda(mood: str) -> str:
    mouth = """<path d="M 55 76 Q 60 79 65 76" fill="none" stroke="#1F2937" stroke-width="2" stroke-linecap="round"/>"""
    if mood == "cheer":
        mouth = """<path d="M 53 74 Q 60 84 67 74 Z" fill="#FF8FA3" stroke="#1F2937" stroke-width="1.8"/>"""

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120" width="120" height="120">
{get_defs()}
{get_badge(mood)}
  <g id="panda_character">
    <!-- Tai gấu tròn đen -->
    <circle cx="28" cy="34" r="14" fill="#2B2D42"/>
    <circle cx="92" cy="34" r="14" fill="#2B2D42"/>
    <circle cx="28" cy="34" r="8" fill="#4A4E69"/>
    <circle cx="92" cy="34" r="8" fill="#4A4E69"/>

    <!-- Đầu & thân Panda tròn xoe như Mochi -->
    <ellipse cx="60" cy="65" rx="40" ry="35" fill="#FFFFFF" stroke="#2B2D42" stroke-width="2.5"/>

    <!-- Quầng mắt đen đặc trưng của Panda -->
    <ellipse cx="43" cy="60" rx="12" ry="10" fill="#2B2D42" transform="rotate(-15 43 60)"/>
    <ellipse cx="77" cy="60" rx="12" ry="10" fill="#2B2D42" transform="rotate(15 77 60)"/>

    <!-- Mắt Anime Chibi lấp lánh bên trong -->
{make_eyes(mood, left_cx=43, right_cx=77, cy=60, r=5.2, iris_color="#FFFFFF" if mood in ["cheer", "rest"] else "#FFFFFF")}

    <!-- Má hồng phúng phính -->
{make_blush(29, 91, 72, 7, 4)}

    <!-- Mũi gấu tròn nhỏ -->
    <ellipse cx="60" cy="70" rx="4" ry="2.8" fill="#2B2D42"/>

    <!-- Miệng nhỏ -->
    {mouth}

    <!-- Nhánh lá trúc xanh nhỏ kẹp bên má (đặc trưng Panda) -->
    <path d="M 88 78 Q 96 74 102 78 Q 96 82 88 78 Z" fill="#52B788"/>
    <path d="M 88 78 Q 94 85 98 90 Q 92 88 88 78 Z" fill="#40916C"/>

    <!-- 2 tay đen múp míp ôm ngực -->
    <ellipse cx="38" cy="92" rx="10" ry="7" fill="#2B2D42"/>
    <ellipse cx="82" cy="92" rx="10" ry="7" fill="#2B2D42"/>

{make_mood_props(mood, "panda")}
  </g>
</svg>"""


# ===========================================================================
# 4. CÚN SHIBA (SHIBA INU)
# ===========================================================================
def render_shiba(mood: str) -> str:
    tongue = ""
    mouth = """<path d="M 54 75 Q 57 78 60 75 Q 63 78 66 75" fill="none" stroke="#283618" stroke-width="2.2" stroke-linecap="round"/>"""
    if mood == "cheer":
        mouth = """<path d="M 54 73 Q 60 84 66 73 Z" fill="#E63946" stroke="#283618" stroke-width="1.8"/>"""
        tongue = """<ellipse cx="60" cy="80" rx="4" ry="3.5" fill="#FF8FA3"/>"""

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120" width="120" height="120">
{get_defs()}
{get_badge(mood)}
  <g id="shiba_character">
    <!-- Tai Shiba đứng vểnh -->
    <polygon points="23,48 18,17 44,30" fill="#E07A5F" stroke="#3D2619" stroke-width="2.5" stroke-linejoin="round"/>
    <polygon points="97,48 102,17 76,30" fill="#E07A5F" stroke="#3D2619" stroke-width="2.5" stroke-linejoin="round"/>
    <!-- Lòng tai trắng kem -->
    <polygon points="26,43 23,24 40,32" fill="#FFF3B0"/>
    <polygon points="94,43 97,24 80,32" fill="#FFF3B0"/>

    <!-- Đầu Shiba vàng bánh mì -->
    <ellipse cx="60" cy="65" rx="40" ry="34" fill="#F4A261" stroke="#3D2619" stroke-width="2.5"/>

    <!-- Má trắng bánh bao (Urajiro) phúng phính -->
    <ellipse cx="42" cy="74" rx="16" ry="14" fill="#FFFDF9"/>
    <ellipse cx="78" cy="74" rx="16" ry="14" fill="#FFFDF9"/>
    <ellipse cx="60" cy="74" rx="18" ry="13" fill="#FFFDF9"/>

    <!-- Vệt lông mày tròn trắng đặc trưng Shiba -->
    <ellipse cx="44" cy="48" rx="4" ry="3.2" fill="#FFFDF9"/>
    <ellipse cx="76" cy="48" rx="4" ry="3.2" fill="#FFFDF9"/>

    <!-- Má hồng -->
{make_blush(30, 90, 75, 7, 4.5)}

    <!-- Mắt Anime Chibi -->
{make_eyes(mood, left_cx=43, right_cx=77, cy=61, r=6.2, iris_color="#3D2619")}

    <!-- Mũi cún đen tròn bóng -->
    <ellipse cx="60" cy="69" rx="4.5" ry="3.5" fill="#1F2421"/>
    <circle cx="58.5" cy="68" r="1.2" fill="#FFFFFF"/>

    <!-- Miệng cún -->
    {mouth}
    {tongue}

    <!-- Khăn quàng bandana đỏ thắt nơ kiểu Nhật -->
    <path d="M 38 90 Q 60 98 82 90 L 74 100 Q 60 104 46 100 Z" fill="#E63946" stroke="#3D2619" stroke-width="2"/>
    <circle cx="60" cy="98" r="3" fill="#FFE3E0"/>

{make_mood_props(mood, "shiba")}
  </g>
</svg>"""


# ===========================================================================
# 5. THỎ BÔNG TAI CỤP (BUNNY)
# ===========================================================================
def render_bunny(mood: str) -> str:
    mouth = """<path d="M 55 77 Q 58 79 60 77 Q 62 79 65 77" fill="none" stroke="#4A4E69" stroke-width="2" stroke-linecap="round"/>"""
    if mood == "cheer":
        mouth = """<path d="M 54 75 Q 60 84 66 75 Z" fill="#FF8FA3" stroke="#4A4E69" stroke-width="1.8"/>"""

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120" width="120" height="120">
{get_defs()}
{get_badge(mood)}
  <g id="bunny_character">
    <!-- Tai thỏ dài rủ cụp 2 bên má mềm mại -->
    <path d="M 34 35 C 15 28 8 55 16 78 C 22 84 29 80 28 66 C 26 50 38 42 36 36 Z" fill="#FFF8F0" stroke="#4A4E69" stroke-width="2.5"/>
    <path d="M 22 45 C 16 56 16 72 22 75 C 24 72 25 60 25 50 Z" fill="#FFCCD5"/>

    <path d="M 86 35 C 105 28 112 55 104 78 C 98 84 91 80 92 66 C 94 50 82 42 84 36 Z" fill="#FFF8F0" stroke="#4A4E69" stroke-width="2.5"/>
    <path d="M 98 45 C 104 56 104 72 98 75 C 96 72 95 60 95 50 Z" fill="#FFCCD5"/>

    <!-- Đầu thỏ trắng tròn xoe -->
    <ellipse cx="60" cy="65" rx="38" ry="34" fill="#FFFDF9" stroke="#4A4E69" stroke-width="2.5"/>

    <!-- Bông hoa anh đào cài trên đầu -->
    <g transform="translate(74, 25) scale(0.65)">
      <circle cx="10" cy="5" r="5" fill="#FFB5A7"/>
      <circle cx="15" cy="10" r="5" fill="#FFB5A7"/>
      <circle cx="13" cy="16" r="5" fill="#FFB5A7"/>
      <circle cx="7" cy="16" r="5" fill="#FFB5A7"/>
      <circle cx="5" cy="10" r="5" fill="#FFB5A7"/>
      <circle cx="10" cy="11" r="3" fill="#FFE66D"/>
    </g>

    <!-- Má hồng thỏ ngây thơ -->
{make_blush(32, 88, 73, 7.5, 4.5)}

    <!-- Mắt Anime Chibi hồng ngọc / tím ngọt ngào -->
{make_eyes(mood, left_cx=43, right_cx=77, cy=63, r=6.5, iris_color="#E76F51" if mood not in ["cheer", "rest"] else "#E76F51")}

    <!-- Mũi hồng hạt đậu -->
    <polygon points="58,71 62,71 60,74" fill="#FF8FA3"/>

    <!-- Miệng nhỏ -->
    {mouth}

    <!-- Củ cà rốt nhỏ thỏ ôm trước ngực -->
    <g transform="translate(62, 82) rotate(25) scale(0.6)">
      <path d="M 10 10 L 16 35 Q 12 37 8 35 Z" fill="#F77F00"/>
      <path d="M 8 9 Q 10 2 12 8 Q 14 0 16 9 Z" fill="#52B788"/>
    </g>
    <!-- Tay thỏ ôm cà rốt -->
    <circle cx="46" cy="92" r="6" fill="#FFFDF9" stroke="#4A4E69" stroke-width="1.8"/>
    <circle cx="74" cy="92" r="6" fill="#FFFDF9" stroke="#4A4E69" stroke-width="1.8"/>

{make_mood_props(mood, "bunny")}
  </g>
</svg>"""


# ===========================================================================
# 6. CÁNH CỤT MINI (PENGUIN)
# ===========================================================================
def render_penguin(mood: str) -> str:
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120" width="120" height="120">
{get_defs()}
{get_badge(mood)}
  <g id="penguin_character">
    <!-- Thân cánh cụt hình quả lê múp míp xanh navy -->
    <path d="M 32 45 C 32 20 88 20 88 45 C 98 62 100 88 88 98 C 76 104 44 104 32 98 C 20 88 22 62 32 45 Z" fill="#1D3557" stroke="#0D1B2A" stroke-width="2.5"/>

    <!-- Bụng tuyết trắng tròn mềm mại -->
    <ellipse cx="60" cy="74" rx="26" ry="24" fill="#FFFFFF"/>

    <!-- 2 cánh tay vẫy lạch bạch -->
    <path d="M 24 58 C 14 66 12 80 20 86 C 24 82 28 72 26 62 Z" fill="#1D3557" stroke="#0D1B2A" stroke-width="2"/>
    <path d="M 96 58 C 106 66 108 80 100 86 C 96 82 92 72 94 62 Z" fill="#1D3557" stroke="#0D1B2A" stroke-width="2"/>

    <!-- Má hồng cánh cụt -->
{make_blush(34, 86, 68, 6.5, 4)}

    <!-- Mắt Anime Chibi to tròn -->
{make_eyes(mood, left_cx=44, right_cx=76, cy=55, r=6.2, iris_color="#0D1B2A")}

    <!-- Mỏ vàng cam nhỏ xinh hình thoi -->
    <polygon points="54,63 66,63 60,71" fill="#F4A261"/>
    <polygon points="56,63 64,63 60,60" fill="#E76F51"/>

    <!-- Khăn len ấm áp quàng cổ sọc đỏ - vàng -->
    <path d="M 33 76 Q 60 84 87 76 L 86 84 Q 60 92 34 84 Z" fill="#E63946"/>
    <!-- Tua rua khăn len rủ xuống -->
    <path d="M 40 82 L 42 98 L 50 96 L 47 84 Z" fill="#E63946" stroke="#0D1B2A" stroke-width="1.5"/>

    <!-- 2 chân cam ngắn cũn cỡn -->
    <ellipse cx="46" cy="101" rx="8" ry="4.5" fill="#F4A261" stroke="#0D1B2A" stroke-width="1.8"/>
    <ellipse cx="74" cy="101" rx="8" ry="4.5" fill="#F4A261" stroke="#0D1B2A" stroke-width="1.8"/>

{make_mood_props(mood, "penguin")}
  </g>
</svg>"""


# ===========================================================================
# BỘ TỔNG HỢP VÀ GHI FILE
# ===========================================================================
CHARACTERS = {
    "cat": render_cat,
    "owl": render_owl,
    "panda": render_panda,
    "shiba": render_shiba,
    "bunny": render_bunny,
    "penguin": render_penguin,
}

MOODS = ["idle", "focus", "nudge", "cheer", "rest"]


def main():
    print(f"Bắt đầu tạo các biểu cảm SVG Chibi tại: {ANIMATIONS_DIR}")
    count = 0
    for char_key, renderer in CHARACTERS.items():
        for mood in MOODS:
            svg_content = renderer(mood)
            target_path = ANIMATIONS_DIR / f"{char_key}_{mood}.svg"
            target_path.write_text(svg_content, encoding="utf-8")
            count += 1
            print(f"  [+] Đã tạo: {target_path.name}")

            # Tạo thêm alias ted_* nếu là cat_*
            if char_key == "cat":
                ted_alias_path = ANIMATIONS_DIR / f"ted_{mood}.svg"
                ted_alias_path.write_text(svg_content, encoding="utf-8")
                count += 1
                print(f"  [+] Đã tạo alias: {ted_alias_path.name}")

    print(f"\n[HOÀN TẤT] Tổng cộng đã tạo thành công {count} tệp SVG Chibi chất lượng cao!")


if __name__ == "__main__":
    main()
