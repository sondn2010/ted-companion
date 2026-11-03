"""Chạy bộ tiền xử lý cho 1 file hoặc cả thư mục .md/.txt, và nhập / xuất từ điển phát âm.

    python -m src.core.vieneu_story_preprocessor.cli chuong01.md [-o out/] [--format studio|json|both]
    python -m src.core.vieneu_story_preprocessor.cli --export-lexicon tu_dien.json
    python -m src.core.vieneu_story_preprocessor.cli --import-lexicon tu_dien.json

Đầu ra: <tên>.studio.txt (kịch bản gắn thẻ) và/hoặc <tên>.json (JSON chunks) trong thư mục -o (mặc định cạnh file gốc).
"""

import argparse
import json
import sys
import time
from pathlib import Path

from src.core.vieneu_story_preprocessor import preprocess
from src.core.vieneu_story_preprocessor.core.lexicon_mapper import export_lexicon, import_lexicon
from src.core.vieneu_story_preprocessor.exporters.sdk_json_exporter import to_json_chunks
from src.core.vieneu_story_preprocessor.exporters.studio_txt_exporter import to_studio_script

INPUT_SUFFIXES = (".md", ".txt")


def _inputs(paths: list[str]) -> list[Path]:
    files: list[Path] = []
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            files += sorted(p for p in path.iterdir() if p.suffix.lower() in INPUT_SUFFIXES and ".studio" not in p.suffixes)
        elif path.is_file():
            files.append(path)
        else:
            raise SystemExit(f"Không tìm thấy: {path}")
    return files


def process_file(src: Path, out_dir: Path | None, fmt: str) -> list[Path]:
    started = time.perf_counter()
    segments = preprocess(src.read_text(encoding="utf-8"))
    target = out_dir or src.parent
    target.mkdir(parents=True, exist_ok=True)
    written = []
    if fmt in ("studio", "both"):
        written.append(target / f"{src.stem}.studio.txt")
        written[-1].write_text(to_studio_script(segments), encoding="utf-8")
    if fmt in ("json", "both"):
        written.append(target / f"{src.stem}.json")
        chunks = to_json_chunks(segments, prefix=f"{src.stem}_")
        written[-1].write_text(json.dumps(chunks, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{src.name}: {len(segments)} khúc, {(time.perf_counter() - started) * 1000:.1f} ms")
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Tiền xử lý văn bản truyện cho VieNeu-TTS")
    parser.add_argument("inputs", nargs="*", help="file hoặc thư mục .md/.txt")
    parser.add_argument("-o", "--out-dir", type=Path, default=None)
    parser.add_argument("--format", choices=("studio", "json", "both"), default="both")
    parser.add_argument("--import-lexicon", type=Path, help="gộp file JSON {từ: cách đọc} vào từ điển người dùng")
    parser.add_argument("--export-lexicon", type=Path, help="xuất toàn bộ từ điển đang dùng ra file JSON")
    args = parser.parse_args(argv)
    if not (args.inputs or args.import_lexicon or args.export_lexicon):
        parser.error("cần ít nhất một file/thư mục, --import-lexicon hoặc --export-lexicon")
    if args.import_lexicon:
        print(f"Đã nhập {import_lexicon(args.import_lexicon)} mục từ điển.")
    if args.export_lexicon:
        print(f"Đã xuất {export_lexicon(args.export_lexicon)} mục từ điển → {args.export_lexicon}")
    for src in _inputs(args.inputs):
        process_file(src, args.out_dir, args.format)
    return 0


if __name__ == "__main__":
    sys.exit(main())
