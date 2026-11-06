"""Dựng pack nhân vật giả (PNG thật bằng Pillow) cho test skin mở khoá dần."""

import json
from pathlib import Path

from PIL import Image

STATES = ("idle", "focus", "cheer", "rest", "nudge")


def make_pack(root: Path, chars=("aa", "bb"), size=(600, 900), complete=True) -> Path:
    """Pack kiểu '25_*': ảnh nằm cùng thư mục, mood_images khai báo đủ; thêm 1 ảnh thừa để thử cắt bớt."""
    root.mkdir(parents=True, exist_ok=True)
    characters = []
    for cid in chars:
        Image.new("RGBA", size, (200, 80, 80, 255)).save(root / f"{cid}.png")
        moods = {}
        for state in STATES:
            if complete or state != "rest":
                Image.new("RGBA", size, (80, 80, 200, 255)).save(root / f"{cid}_{state}.png")
                moods[state] = f"{cid}_{state}.png"
        characters.append({"id": cid, "display_name": cid.upper(), "avatar_file": f"{cid}.png", "mood_images": moods})
    Image.new("RGBA", size, (0, 0, 0, 255)).save(root / "unused_full_size.png")
    (root / "characters.json").write_text(json.dumps({"id": root.name, "title": f"Pack {root.name}",
                                                      "characters": characters}), encoding="utf-8")
    return root
