"""Nạp các pack nhân vật bundle sẵn trong assets/unlockable_skin_packs/<pack>/ + registry điều kiện mở khoá.

Khác character_pack_loader (1 pack THAY THẾ 6 con vật): ở đây nhiều pack được THÊM vào, mỗi nhân vật có key
`pack/character` và điều kiện riêng. Thả thêm thư mục pack mà chưa có trong registry → vẫn xuất hiện với điều
kiện tự gán (bậc thang) — không bao giờ miễn phí do quên khai báo. Module thuần Python (không Qt, không config).
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path

from src.core.character_pack_loader import PACK_MANIFEST_NAME, CharacterPack, PackCharacter, load_character_pack
from src.core.unlockable_skin_ladder_assigner import assign_new_skins
from src.core.unlockable_skin_registry_model import REGISTRY_FILE_NAME, UnlockableSkin, read_registry, skin_key

logger = logging.getLogger("ted")


@dataclass(frozen=True)
class UnlockableCollection:
    skins: list[UnlockableSkin] = field(default_factory=list)            # đúng thứ tự registry
    characters: dict[str, PackCharacter] = field(default_factory=dict)   # key `pack/char` → nhân vật
    pack_titles: dict[str, str] = field(default_factory=dict)            # pack id (tên thư mục) → tiêu đề


def load_installed_packs(root: Path) -> dict[str, CharacterPack]:
    """{tên thư mục: pack} — bỏ qua pack hỏng; nhân vật không có ảnh nào bị loại khỏi pack."""
    root = Path(root)
    packs: dict[str, CharacterPack] = {}
    if not root.is_dir():
        return packs
    # Bỏ thư mục tạm/sao lưu của script cài (".tmp"/".old" sót lại khi bị ngắt) → không nhân đôi nhân vật
    for pack_dir in sorted(d for d in root.iterdir()
                           if (d / PACK_MANIFEST_NAME).is_file() and d.suffix not in (".tmp", ".old")):
        pack = load_character_pack(pack_dir)
        if pack is None:
            continue
        for cid in pack.imageless_characters():
            logger.warning("Bỏ nhân vật không có ảnh: %s/%s", pack_dir.name, cid)
            del pack.characters[cid]
        if pack.characters:
            packs[pack_dir.name] = pack
    return packs


def load_unlockable_collection(root: Path) -> UnlockableCollection:
    root = Path(root)
    packs = load_installed_packs(root)
    if not packs:
        return UnlockableCollection()
    present = {skin_key(pid, cid): (pid, c) for pid, p in packs.items() for cid, c in p.characters.items()}
    registered = [s for s in read_registry(root / REGISTRY_FILE_NAME) if s.key in present]
    # Nhân vật có trong pack nhưng chưa có trong registry → gán bậc thang trong bộ nhớ (thứ tự thư mục)
    candidates = [(key, pid, c.display_name, c.display_name) for key, (pid, c) in present.items()]
    skins = assign_new_skins(registered, candidates)
    return UnlockableCollection(
        skins=skins,
        characters={s.key: present[s.key][1] for s in skins},
        pack_titles={pid: p.title or pid for pid, p in packs.items()},
    )
