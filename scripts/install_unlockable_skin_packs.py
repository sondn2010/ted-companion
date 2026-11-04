#!/usr/bin/env python3
"""
Cài / gỡ các pack nhân vật MỞ KHOÁ DẦN (mỗi nhân vật có điều kiện riêng) vào assets/unlockable_skin_packs/.
Ảnh được thu nhỏ (mặc định 256px) + tối ưu PNG, chỉ giữ ảnh app dùng → nhẹ (xem assets/unlockable_skin_packs/README.md).

    python scripts/install_unlockable_skin_packs.py --pack 01_chibi_adult_mature --pack vietnam-chibi-pack
    python scripts/install_unlockable_skin_packs.py --list
    python scripts/install_unlockable_skin_packs.py --remove vietnam-chibi-pack
    python scripts/install_unlockable_skin_packs.py --pack <tên|đường dẫn> --dry-run   # chỉ kiểm tra, không ghi gì

Idempotent: chạy lại cùng lệnh → cùng kết quả. Điều kiện mở khoá của nhân vật ĐÃ có trong registry không bao giờ bị
ghi đè; nhân vật mới được nối đuôi với bậc thang điều kiện tự động. Mã thoát 0 = OK, 1 = lỗi/dừng.
"""

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import shutil  # noqa: E402
import time  # noqa: E402

from PIL import Image  # noqa: E402

from install_character_pack import (  # noqa: E402  (tái dùng quy tắc copy/kiểm tra của --pack đơn)
    COPY_IGNORE, DEFAULT_PACKS_ROOT, _remove_tree, available_packs, check_complete, resolve_pack_dir)
from src.core.character_pack_loader import PACK_MANIFEST_NAME, load_character_pack  # noqa: E402
from src.core.unlockable_skin_ladder_assigner import assign_new_skins  # noqa: E402
from src.core.unlockable_skin_registry_model import (  # noqa: E402
    REGISTRY_FILE_NAME, read_registry, skin_key, write_registry)

DEFAULT_TARGET_DIR = ROOT_DIR / "assets" / "unlockable_skin_packs"
DEFAULT_SIZE = 256


def downscale_png(path: Path, size: int) -> None:
    """Thu nhỏ cạnh dài về `size` (giữ tỉ lệ + alpha, LANCZOS), nén tối ưu; ảnh đã nhỏ hơn vẫn được nén lại."""
    with Image.open(path) as img:
        img.load()
        image = img.convert("RGBA") if img.mode not in ("RGBA", "LA", "P") else img
        if max(image.size) > size:
            image.thumbnail((size, size), Image.Resampling.LANCZOS)
        image.save(path, format="PNG", optimize=True)


def prune_unused_files(pack_dir: Path) -> None:
    """Xoá PNG mà loader không dùng (ảnh dư/bản gốc trùng) để pack nhẹ hơn; manifest + ảnh dùng được giữ lại."""
    pack = load_character_pack(pack_dir)
    used = {p.resolve() for c in pack.characters.values() for p in (*c.state_images.values(), c.avatar) if p}
    for png in pack_dir.rglob("*.png"):
        if png.resolve() not in used:
            png.unlink()
    for folder in sorted((d for d in pack_dir.rglob("*") if d.is_dir()), reverse=True):
        if not any(folder.iterdir()):
            folder.rmdir()


def _rename_with_retry(src: Path, dst: Path, attempts: int = 8) -> None:
    """Windows: antivirus/indexer có thể giữ thư mục vừa ghi vài trăm ms → thử lại thay vì thất bại ngay."""
    for attempt in range(attempts):
        try:
            src.rename(dst)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(0.4)


def install_pack(source_dir: Path, dest_dir: Path, size: int) -> None:
    """Copy → thu nhỏ → cắt ảnh dư trong thư mục tạm; thay pack cũ bằng 'đổi tên cũ → đổi tên mới', lỗi thì khôi phục."""
    staging = dest_dir.with_name(dest_dir.name + ".tmp")
    backup = dest_dir.with_name(dest_dir.name + ".old")
    _remove_tree(staging)
    _remove_tree(backup)
    try:
        shutil.copytree(source_dir, staging, ignore=COPY_IGNORE)
        prune_unused_files(staging)
        for png in staging.rglob("*.png"):
            downscale_png(png, size)
        if dest_dir.exists():
            _rename_with_retry(dest_dir, backup)
        try:
            _rename_with_retry(staging, dest_dir)
        except OSError:
            if backup.exists() and not dest_dir.exists():
                backup.rename(dest_dir)   # giữ lại pack cũ
            raise
    finally:
        _remove_tree(staging)
        if dest_dir.exists():   # chỉ xoá bản cũ khi pack đích còn nguyên
            _remove_tree(backup)


def candidates_of(pack_name: str, pack_dir: Path) -> list[tuple[str, str, str, str]]:
    pack = load_character_pack(pack_dir)
    return [(skin_key(pack_name, c.id), pack_name, c.display_name, c.display_name) for c in pack.characters.values()]


def dir_size_mb(path: Path) -> float:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) / (1024 * 1024)


def print_listing(source: Path, target: Path) -> None:
    registry = read_registry(target / REGISTRY_FILE_NAME)
    print(f"📦 Đã cài ({target}): {len(registry)} nhân vật, {dir_size_mb(target) if target.is_dir() else 0:.1f} MB")
    for skin in registry:
        print(f"   {skin.key:60s} {skin.condition.to_json()}")
    print("🗂  Pack có sẵn ở nguồn: " + (", ".join(available_packs(source)) or "(không có)"))


def remove_pack(name: str, target: Path, dry_run: bool) -> int:
    pack_dir = target / name
    # Chỉ nhận tên thư mục pack trực tiếp trong target ('.', '..', đường dẫn → từ chối, không bao giờ xoá ngoài target)
    if Path(name).name != name or name in (".", "..") or not (pack_dir / PACK_MANIFEST_NAME).is_file():
        print(f"❌ '{name}' không phải pack đã cài trong {target}.")
        return 1
    if not pack_dir.is_dir():
        print(f"❌ Pack '{name}' chưa được cài trong {target}.")
        return 1
    print(f"🗑  {'[dry-run] sẽ gỡ' if dry_run else 'Gỡ'} pack {name}")
    if not dry_run:
        _remove_tree(pack_dir)
        registry = [s for s in read_registry(target / REGISTRY_FILE_NAME) if s.pack != name]
        write_registry(target / REGISTRY_FILE_NAME, registry)
    return 0


def install_packs(args, target: Path) -> int:
    planned = []
    for pack in args.pack:
        pack_dir = resolve_pack_dir(pack, args.source)
        if not (pack_dir / PACK_MANIFEST_NAME).is_file():
            print(f"❌ Không tìm thấy pack '{pack}' (cần {pack_dir / PACK_MANIFEST_NAME}).")
            print("   Pack hiện có: " + (", ".join(available_packs(args.source)) or "(không có)"))
            return 1
        if not check_complete(pack_dir, args.yes):
            print(f"⛔ Dừng: pack '{pack}' không hợp lệ.")
            return 1
        planned.append((pack_dir.name, pack_dir))
    registry = read_registry(target / REGISTRY_FILE_NAME)
    for name, pack_dir in planned:
        print(f"{'[dry-run] sẽ cài' if args.dry_run else '⬇️  Cài'} {name} → {target / name} (≤{args.size}px)")
        if not args.dry_run:
            try:
                target.mkdir(parents=True, exist_ok=True)
                install_pack(pack_dir, target / name, args.size)
            except OSError as exc:
                print(f"❌ Không cài được '{name}' (file đang bị khoá?): {exc}")
                return 1
        registry = assign_new_skins(registry, candidates_of(name, pack_dir))
    if args.dry_run:
        print(f"[dry-run] registry sẽ có {len(registry)} nhân vật, không ghi gì.")
        return 0
    # Chỉ giữ entry của nhân vật còn tồn tại trong pack đã cài (pack cài lại có thể đổi tập nhân vật)
    alive = {c[0] for p in target.iterdir() if (p / PACK_MANIFEST_NAME).is_file() for c in candidates_of(p.name, p)}
    write_registry(target / REGISTRY_FILE_NAME, [s for s in registry if s.key in alive])
    print(f"✅ Xong: {len(alive)} nhân vật, {dir_size_mb(target):.1f} MB tại {target}")
    return 0


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Cài pack nhân vật mở khoá dần vào assets/unlockable_skin_packs")
    parser.add_argument("--pack", action="append", default=[], help="Tên pack trong --source hoặc đường dẫn (lặp lại được)")
    parser.add_argument("--source", type=Path, default=DEFAULT_PACKS_ROOT, help=f"Thư mục chứa các pack (mặc định {DEFAULT_PACKS_ROOT})")
    parser.add_argument("--size", type=int, default=DEFAULT_SIZE, help="Cạnh dài tối đa của ảnh (px), mặc định 256")
    parser.add_argument("--remove", action="append", default=[], help="Gỡ pack đã cài (lặp lại được)")
    parser.add_argument("--list", action="store_true", help="Liệt kê pack đã cài + điều kiện, rồi thoát")
    parser.add_argument("--dry-run", action="store_true", help="Chỉ kiểm tra + in kế hoạch, không ghi/xoá gì")
    parser.add_argument("--yes", "-y", action="store_true", help="Không hỏi khi pack thiếu ảnh trạng thái")
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET_DIR, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.size < 32:
        parser.error("--size tối thiểu 32")

    if args.list or not (args.pack or args.remove):
        print_listing(args.source, args.target)
        return 0
    for name in args.remove:
        if remove_pack(name, args.target, args.dry_run) != 0:
            return 1
    return install_packs(args, args.target) if args.pack else 0


if __name__ == "__main__":
    sys.exit(main())
