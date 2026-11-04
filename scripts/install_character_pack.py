#!/usr/bin/env python3
"""
Cài 1 Character Pack (docs/UI/characters/<pack>) vào app: copy toàn bộ characters.json + ảnh nhân vật + animation
vào assets/character_pack/ (PyInstaller tự đóng gói mọi thư mục trong assets/; khi dev app đọc thẳng từ đó).

    python scripts/install_character_pack.py --pack vietnam-chibi-pack   # cài pack theo tên (hoặc đường dẫn)
    python scripts/install_character_pack.py --pack none                 # gỡ pack → 6 con vật mặc định
    python scripts/install_character_pack.py                             # giữ pack đang cài, chỉ kiểm tra lại

Pack thiếu ảnh trạng thái (idle/focus/cheer/rest/nudge) → cảnh báo và hỏi có tiếp tục không (--yes: luôn tiếp tục).
Không truyền --pack mà pack đang cài thiếu ảnh → chỉ cảnh báo (đã đồng ý lúc cài), không hỏi lại mỗi lần chạy.
Nhân vật không có ảnh nào (kể cả avatar) → luôn dừng.
Mã thoát 0 = tiếp tục build/chạy app; 1 = dừng.
"""

import argparse
import os
import shutil
import stat
import sys
from pathlib import Path

# Đảm bảo import được các module từ src/ khi chạy độc lập
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.core.character_pack_loader import PACK_MANIFEST_NAME, load_character_pack  # noqa: E402

DEFAULT_PACKS_ROOT = ROOT_DIR.parent / "docs" / "UI" / "characters"
DEFAULT_TARGET_DIR = ROOT_DIR / "assets" / "character_pack"
NO_PACK = "none"
# File tài liệu / preview của pack, app không dùng → không đóng gói
COPY_IGNORE = shutil.ignore_patterns("*.zip", "*.html", "*.md", "*.jpg", "__pycache__")


def available_packs(packs_root: Path) -> list[str]:
    if not packs_root.is_dir():
        return []
    return sorted(d.name for d in packs_root.iterdir() if (d / PACK_MANIFEST_NAME).is_file())


def resolve_pack_dir(pack: str, packs_root: Path) -> Path:
    candidate = Path(pack)
    return candidate if candidate.is_dir() else packs_root / pack


def confirm(question: str, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    try:
        return input(f"{question} [y/N]: ").strip().lower() in ("y", "yes", "c", "co", "có")
    except EOFError:   # không có bàn phím (CI) → coi như không đồng ý
        return False


def check_complete(pack_dir: Path, assume_yes: bool, ask: bool = True) -> bool:
    """In tóm tắt pack; thiếu ảnh trạng thái thì hỏi người dùng có tiếp tục không (ask=False: chỉ cảnh báo)."""
    pack = load_character_pack(pack_dir)
    if pack is None:
        print(f"❌ {pack_dir / PACK_MANIFEST_NAME} không hợp lệ hoặc không có nhân vật nào.")
        return False
    print(f"🎭 Pack '{pack.id}': {len(pack.characters)} nhân vật, mặc định '{pack.default_character_id}'.")
    imageless = pack.imageless_characters()
    if imageless:
        print(f"❌ Nhân vật không có ảnh nào (kể cả avatar): {', '.join(imageless)}")
        return False
    missing = pack.missing_report()
    if not missing:
        return True
    print("⚠️  Pack KHÔNG đầy đủ animation (trạng thái thiếu sẽ dùng ảnh idle/avatar):")
    for cid, states in missing.items():
        print(f"   - {cid}: thiếu {', '.join(states)}")
    return confirm("Vẫn tiếp tục?", assume_yes) if ask else True


def _remove_tree(path: Path):
    def clear_readonly_and_retry(func, failed_path, _exc):   # file read-only (giải nén zip) chặn rmtree trên Windows
        os.chmod(failed_path, stat.S_IWRITE)
        func(failed_path)
    if path.exists():
        handler = {"onexc" if sys.version_info >= (3, 12) else "onerror": clear_readonly_and_retry}
        shutil.rmtree(path, **handler)


def install(pack_dir: Path, target_dir: Path):
    """Copy vào thư mục tạm rồi mới thay pack cũ → copy lỗi giữa chừng không làm mất pack đang cài."""
    staging = target_dir.with_name(target_dir.name + ".tmp")
    _remove_tree(staging)
    shutil.copytree(pack_dir, staging, ignore=COPY_IGNORE)
    _remove_tree(target_dir)
    staging.rename(target_dir)


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Cài Character Pack vào assets/character_pack của Ted Companion")
    parser.add_argument("--pack", help=f"Tên pack trong {DEFAULT_PACKS_ROOT}, đường dẫn thư mục pack, hoặc '{NO_PACK}'")
    parser.add_argument("--yes", "-y", action="store_true", help="Không hỏi, luôn tiếp tục khi pack thiếu animation")
    parser.add_argument("--packs-root", type=Path, default=DEFAULT_PACKS_ROOT, help=argparse.SUPPRESS)
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET_DIR, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    target = args.target

    if args.pack is None:
        if not (target / PACK_MANIFEST_NAME).is_file():
            print("🐱 Không có character pack → dùng 6 nhân vật mặc định.")
            return 0
        return 0 if check_complete(target, args.yes, ask=False) else 1

    if args.pack.strip().lower() == NO_PACK:
        try:
            _remove_tree(target)
        except OSError as exc:
            print(f"❌ Không xoá được {target}: {exc}")
            return 1
        print("🐱 Đã gỡ character pack → dùng 6 nhân vật mặc định.")
        return 0

    pack_dir = resolve_pack_dir(args.pack, args.packs_root)
    if not (pack_dir / PACK_MANIFEST_NAME).is_file():
        print(f"❌ Không tìm thấy pack '{args.pack}' (cần {pack_dir / PACK_MANIFEST_NAME}).")
        packs = available_packs(args.packs_root)
        if packs:
            print("   Pack hiện có: " + ", ".join(packs))
        return 1
    if not check_complete(pack_dir, args.yes):
        print("⛔ Đã dừng, giữ nguyên pack đang cài.")
        return 1
    if pack_dir.resolve() != target.resolve():
        try:
            install(pack_dir, target)
        except OSError as exc:
            print(f"❌ Không cài được pack (file đang bị khoá?): {exc}")
            return 1
    print(f"✅ Đã cài pack vào {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
