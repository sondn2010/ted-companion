"""Cắt văn bản dài thành khúc ngắn cho VieNeu (suy luận CPU chậm) và ghép nhiều WAV PCM thành một file.

split_text_for_tts: nhóm câu (tách ở . ! ? ; …), câu quá dài tách tiếp ở dấu phẩy, vẫn quá dài thì cắt cứng ở khoảng trắng.
concat_wav_bytes: đọc RIFF đúng chuẩn (duyệt chunk, bỏ chunk phụ, chịu kích thước placeholder của WAV stream),
yêu cầu mọi khúc cùng định dạng rồi nối phần PCM. append_silence: nối khoảng lặng (ngắt nghỉ) vào cuối một khúc.
"""

import re
import struct

MAX_CHUNK_CHARS = 350

_SENTENCE_END = re.compile(r"(?<=[.!?;…])\s+|\n+")
_COMMA = re.compile(r"(?<=[,，])\s+")


def _pack(pieces: list[str], limit: int) -> list[str]:
    """Gộp các mẩu liên tiếp thành nhóm ≤ limit ký tự."""
    groups: list[str] = []
    current = ""
    for piece in pieces:
        if current and len(current) + 1 + len(piece) > limit:
            groups.append(current)
            current = piece
        else:
            current = f"{current} {piece}" if current else piece
    if current:
        groups.append(current)
    return groups


def _hard_split(text: str, limit: int) -> list[str]:
    out = []
    while len(text) > limit:
        cut = text.rfind(" ", 0, limit + 1)
        cut = cut if cut > 0 else limit
        out.append(text[:cut].strip())
        text = text[cut:].strip()
    if text:
        out.append(text)
    return out


def _split_pieces(text: str, limit: int) -> list[str]:
    """Câu ≤ limit giữ nguyên; câu dài tách ở dấu phẩy, vẫn dài thì cắt cứng."""
    sentences = [s.strip() for s in _SENTENCE_END.split(text.strip()) if s.strip()]
    pieces: list[str] = []
    for sentence in sentences:
        if len(sentence) <= limit:
            pieces.append(sentence)
            continue
        for part in _pack([p.strip() for p in _COMMA.split(sentence) if p.strip()], limit):
            pieces.extend(_hard_split(part, limit) if len(part) > limit else [part])
    return pieces


def split_text_for_tts(text: str, limit: int = MAX_CHUNK_CHARS, first_limit: int = 0) -> list[str]:
    """`first_limit` > 0: khúc đầu ngắn (≈1 câu) để có tiếng sớm khi phát theo khúc; các khúc sau gộp tới `limit`."""
    if not first_limit or first_limit >= limit:
        return _pack(_split_pieces(text, limit), limit)
    pieces = _split_pieces(text, first_limit)
    head = _pack(pieces, first_limit)[:1]
    rest = " ".join(pieces)[len(head[0]):].strip() if head else ""
    return head + (_pack(_split_pieces(rest, limit), limit) if rest else [])


def parse_wav(data: bytes) -> tuple[bytes, bytes]:
    """Trả (fmt_chunk_payload, pcm). Raise ValueError nếu không phải WAV PCM hợp lệ."""
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValueError("Không phải file WAV (RIFF/WAVE).")
    fmt, pos = None, 12
    while pos + 8 <= len(data):
        chunk_id, size = data[pos:pos + 4], struct.unpack("<I", data[pos + 4:pos + 8])[0]
        body = pos + 8
        if chunk_id == b"fmt ":
            fmt = data[body:body + size]
        elif chunk_id == b"data":
            if fmt is None:
                raise ValueError("WAV thiếu chunk fmt trước data.")
            return fmt, data[body:body + size] if body + size <= len(data) else data[body:]   # placeholder 0xFFFFFFFF: lấy hết phần còn lại
        pos = body + size + (size & 1)   # chunk căn chẵn byte
    raise ValueError("WAV thiếu chunk data.")


def _build_wav(fmt: bytes, pcm: bytes) -> bytes:
    return (b"RIFF" + struct.pack("<I", 4 + 8 + len(fmt) + 8 + len(pcm)) + b"WAVE"
            + b"fmt " + struct.pack("<I", len(fmt)) + fmt + b"data" + struct.pack("<I", len(pcm)) + pcm)


def concat_wav_bytes(wavs: list[bytes]) -> bytes:
    if not wavs:
        raise ValueError("Không có đoạn WAV nào để ghép.")
    if len(wavs) == 1:
        return wavs[0]
    parsed = [parse_wav(w) for w in wavs]
    fmt = parsed[0][0]
    if any(f != fmt for f, _ in parsed):
        raise ValueError("Các đoạn WAV khác định dạng (tần số/kênh/độ sâu bit) — không ghép được.")
    return _build_wav(fmt, b"".join(p for _, p in parsed))


def append_silence(wav: bytes, seconds: float) -> bytes:
    """Nối khoảng lặng vào cuối WAV PCM — ngắt nghỉ do Ted chèn vì VieNeu không hiểu thẻ [giây]."""
    fmt, pcm = parse_wav(wav)
    rate = struct.unpack("<I", fmt[4:8])[0]
    block_align = struct.unpack("<H", fmt[12:14])[0]
    return _build_wav(fmt, pcm + b"\x00" * (round(seconds * rate) * block_align))
