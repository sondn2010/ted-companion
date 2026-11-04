#!/usr/bin/env python3
"""Sinh ảnh huy hiệu (dev-time, 1 lần) bằng MiniMax `mmx image generate` -> assets/badges/<id>.png (256x256 RGBA).

  uv run python scripts/generate_badge_images.py                      # sinh ảnh còn thiếu
  uv run python scripts/generate_badge_images.py --only focus_day_gold --force
  uv run python scripts/generate_badge_images.py --dry-run            # chỉ in lệnh mmx
Pipeline: mmx (nền trắng, jpg) -> clean_cutout (tách nền) -> trim -> pad vuông -> 256x256. Raw ở build/badges_raw/.
"""
import argparse
import html
import shutil
import subprocess
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from src.core.gamification.badge_catalog_loader import BADGES_DIR, load_badge_catalog  # noqa: E402

RAW_DIR = ROOT / "build" / "badges_raw"
SIZE = 256
LOCKED_SUBJECT = "a grey question mark silhouette"


def build_prompt(style_prefix: str, tier_phrase: str, subject: str) -> str:
    return f"{style_prefix.replace('{TIER}', tier_phrase)}, in the center: {subject}"


def seed_for(subject: str) -> int:
    """Seed theo chủ thể -> các tier cùng họ có bố cục giống nhau, chỉ khác viền."""
    return zlib.crc32(subject.encode("utf-8")) % 2**31


def mmx_command(prompt: str, seed: int, out: Path, base64: bool = False) -> list:
    cmd = [shutil.which("mmx") or "mmx", "image", "generate", "--prompt", prompt, "--width", "512", "--height", "512",
           "--seed", str(seed), "--out", str(out), "--non-interactive", "--quiet"]
    return cmd + ["--response-format", "base64"] if base64 else cmd


def run_mmx(prompt: str, seed: int, raw: Path) -> bool:
    """Chạy mmx; lỗi tải ảnh (CDN) -> thử lại 1 lần với base64."""
    for base64 in (False, True):
        raw.unlink(missing_ok=True)
        try:
            res = subprocess.run(mmx_command(prompt, seed, raw, base64), capture_output=True, text=True,
                                 timeout=300, shell=False)
        except subprocess.TimeoutExpired:
            print("   timeout")
            continue
        if res.returncode == 0 and raw.exists() and raw.stat().st_size > 0:
            return True
        print(f"   mmx lỗi (base64={base64}): {(res.stderr or res.stdout).strip()[:200]}")
    return False


def finalize(raw: Path, dest: Path, grey: bool = False) -> None:
    """raw jpg -> cutout -> trim bbox -> pad vuông -> 256x256 RGBA PNG."""
    from PIL import Image
    from process_chibi_pngs import clean_cutout
    tmp = raw.with_suffix(".cut.png")
    clean_cutout(str(raw), str(tmp))
    img = Image.open(tmp).convert("RGBA")
    img = img.crop(img.getchannel("A").getbbox() or (0, 0, *img.size))
    side = max(img.size) + 8
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(img, ((side - img.width) // 2, (side - img.height) // 2))
    canvas = canvas.resize((SIZE, SIZE), Image.LANCZOS)
    if grey:  # _locked: bỏ màu, giữ alpha
        g = canvas.convert("L").point(lambda v: int(v * 0.7))
        canvas = Image.merge("RGBA", (g, g, g, canvas.getchannel("A")))
    canvas.save(dest, "PNG", optimize=True)


def write_preview(entries: list) -> None:
    cells = "".join(f'<figure><img src="{html.escape(p.resolve().as_uri())}" width="128">'
                    f'<figcaption>{html.escape(n)}</figcaption></figure>' for n, p in entries if p.exists())
    (RAW_DIR / "preview.html").write_text(
        '<meta charset="utf-8"><style>body{background:#ccc;display:flex;flex-wrap:wrap;gap:8px;font:11px sans-serif}'
        f'figure{{margin:0;text-align:center}}</style>{cells}', encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--only", default="", help="id, ngăn cách bằng dấu phẩy (gồm cả _locked)")
    ap.add_argument("--force", action="store_true", help="sinh lại dù PNG đã tồn tại")
    ap.add_argument("--seed-bump", type=int, default=0, help="cộng vào seed để ra bố cục khác khi sinh lại outlier")
    ap.add_argument("--dry-run", action="store_true", help="chỉ in lệnh mmx")
    args = ap.parse_args()
    catalog = load_badge_catalog(strict=True)
    jobs = [(b.id, b.image, catalog.tier_phrases[b.tier], b.prompt, False) for b in catalog.badges]
    jobs.append(("_locked", catalog.locked_image, catalog.tier_phrases["silver"], LOCKED_SUBJECT, True))
    only = {s.strip() for s in args.only.split(",") if s.strip()}
    unknown = only - {j[0] for j in jobs}
    if unknown:
        print(f"id không có trong catalog: {sorted(unknown)}")
        return 2
    if not args.dry_run and not shutil.which("mmx"):
        print("Thiếu `mmx` - cài: npm i -g mmx-cli rồi `mmx auth login`")
        return 1
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    failed, done = [], 0
    for bid, image, tier_phrase, subject, grey in jobs:
        if only and bid not in only:
            continue
        dest, raw = BADGES_DIR / image, RAW_DIR / f"{bid}.jpg"
        if dest.exists() and not args.force:
            continue
        prompt, seed = build_prompt(catalog.style_prefix, tier_phrase, subject), seed_for(subject) + args.seed_bump
        print(f"[{bid}] seed={seed}")
        if args.dry_run:
            print("  ", subprocess.list2cmdline(mmx_command(prompt, seed, raw)))
            continue
        try:
            if not run_mmx(prompt, seed, raw):
                raise RuntimeError("mmx thất bại")
            finalize(raw, dest, grey)
            done += 1
        except Exception as exc:  # noqa: BLE001 - 1 badge lỗi không chặn cả batch
            print(f"   FAIL {bid}: {exc!r}")
            failed.append(bid)
    if not args.dry_run:
        write_preview([(j[0], BADGES_DIR / j[1]) for j in jobs])
        print(f"ok={done} failed={len(failed)} {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
