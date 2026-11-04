#!/usr/bin/env python3
"""
Tự động sinh toàn bộ ảnh biểu cảm bằng mmx CLI và xử lý tách nền PNG chuẩn xác.
"""

import subprocess
import sys
from pathlib import Path

# Thêm thư mục scripts vào path
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from process_chibi_pngs import clean_cutout, TARGET_DIR

TEMP_DIR = SCRIPT_DIR.parent / "temp_raw_images"
TEMP_DIR.mkdir(parents=True, exist_ok=True)

PROMPTS = {
    # 1. MÈO TED (CAT)
    "cat_idle": "Cute chubby ginger chibi kitten character sticker, round face, perky ears with pink inside, wearing red collar with golden bell, sitting happily smiling, white background, bold white die-cut sticker outline contour, 2D vector illustration",
    "cat_focus": "Cute chubby ginger chibi kitten sticker in deep focus, wearing high-tech gaming headset with glowing earcups and cute round study glasses, working intently, white background, bold white die-cut sticker outline contour, 2D vector illustration",
    "cat_cheer": "Cute chubby ginger chibi kitten sticker celebrating joyfully, jumping with paws raised in victory, wide happy open mouth smile, surrounded by colorful confetti and golden stars, white background, bold white die-cut sticker outline contour, 2D vector illustration",
    "cat_rest": "Cute chubby ginger chibi kitten sticker curled up fast asleep peacefully on a tiny cushion, curved sleeping eyelashes, sweet smile, floating Zzz bubbles, white background, bold white die-cut sticker outline contour, 2D vector illustration",
    "cat_nudge": "Cute chubby ginger chibi kitten sticker doing a gentle reminder nudge, tilting head curiously, raising one little paw waving forward with pink pads, floating pink question mark bubble, white background, bold white die-cut sticker outline contour, 2D vector illustration",

    # 2. CÚ ĐÊM (OWL)
    "owl_idle": "Cute round chubby chibi baby barn owl sticker, fluffy golden brown feathers, creamy belly, huge sparkling round amber eyes, tiny orange beak, sitting proudly, white background, bold white die-cut sticker outline contour, 2D vector illustration",
    "owl_focus": "Cute round chubby chibi owl sticker in deep focus, wearing glowing neon blue gaming headphones and smart round reading glasses, studying intently, white background, bold white die-cut sticker outline contour, 2D vector illustration",
    "owl_cheer": "Cute round chubby chibi owl sticker celebrating joyfully, flapping wings high in victory, joyful open beak, flying golden sparkles and confetti, white background, bold white die-cut sticker outline contour, 2D vector illustration",
    "owl_rest": "Cute round chubby chibi owl sticker sleeping peacefully, cozy nightcap on head, resting on a soft crescent moon pillow, eyes gently closed, floating Zzz, white background, bold white die-cut sticker outline contour, 2D vector illustration",
    "owl_nudge": "Cute round chubby chibi owl sticker tilting head inquisitively, one wing raised tapping gently, curious wide eyes, floating question mark bubble, white background, bold white die-cut sticker outline contour, 2D vector illustration",

    # 3. GẤU TRÚC (PANDA)
    "panda_idle": "Cute round plump chibi baby giant panda sticker, soft mochi dumpling shape, velvety black ears and eye patches, holding a fresh green bamboo stalk, sparkling dark eyes, blush cheeks, white background, bold white die-cut sticker outline contour, 2D vector illustration",
    "panda_focus": "Cute round chibi baby panda sticker in deep focus, wearing glowing neon green gaming headset and round study glasses, sitting working upright, white background, bold white die-cut sticker outline contour, 2D vector illustration",
    "panda_cheer": "Cute round chibi baby panda sticker celebrating joyfully, jumping with chubby black arms raised in celebration, happy open mouth smile, confetti and green bamboo leaves around, white background, bold white die-cut sticker outline contour, 2D vector illustration",
    "panda_rest": "Cute round chibi baby panda sticker fast asleep peacefully, curled up like a snowball hugging a soft bamboo pillow, eyes serenely closed, floating Zzz bubbles, white background, bold white die-cut sticker outline contour, 2D vector illustration",
    "panda_nudge": "Cute round chibi baby panda sticker doing a gentle reminder poke, tilting head curiously to one side, raising one chubby black paw waving forward, floating question mark bubble, white background, bold white die-cut sticker outline contour, 2D vector illustration",
}


def run_mmx_generate(key: str, prompt: str) -> Path:
    raw_path = TEMP_DIR / f"{key}_raw.jpg"
    if raw_path.exists():
        print(f"  [-] Đã có raw: {raw_path.name}")
        return raw_path

    print(f"  [>] Đang sinh bằng MMX: {key} ...")
    cmd = [
        "powershell", "-ExecutionPolicy", "Bypass", "-Command",
        f'mmx image generate --prompt "{prompt}" --aspect-ratio 1:1 --out "{raw_path}" --quiet'
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"  [!] Lỗi khi sinh {key}: {res.stderr}")
    else:
        print(f"  [+] Thành công: {raw_path.name}")
    return raw_path


def main():
    print("=== BẮT ĐẦU SINH VÀ XỬ LÝ ẢNH CHIBI CHO CAT, OWL, PANDA ===")
    for key, prompt in PROMPTS.items():
        raw_file = run_mmx_generate(key, prompt)
        if raw_file.exists():
            out_png = TARGET_DIR / f"{key}.png"
            clean_cutout(str(raw_file), str(out_png), thresh=45)

    print("\n=== HOÀN TẤT SINH ẢNH ===")


if __name__ == "__main__":
    main()
