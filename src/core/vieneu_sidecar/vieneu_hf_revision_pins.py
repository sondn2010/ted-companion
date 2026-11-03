"""Ghim revision (commit sha) Hugging Face cho các repo model mà SDK vieneu tải — chỉ stdlib.

SDK vieneu 3.8.3 không có tham số `revision`, mà mọi nơi đều gọi `huggingface_hub.hf_hub_download(repo, file)` (nhánh `main`).
Nên ta bọc hàm đó: repo nằm trong PINS và caller không nêu revision → ép dùng sha đã ghim.
Hệ quả: lúc cài (online) tải đúng snapshot đã kiểm duyệt; lúc chạy (HF_HUB_OFFLINE=1) đọc đúng snapshot đó từ cache.
Phải gọi `apply_revision_pins()` TRƯỚC `import vieneu` (một số module của SDK import tên hàm ngay lúc nạp).
Đổi sha = kiểm tra lại model rồi tăng phiên bản marker để người dùng cài lại.
"""

from __future__ import annotations

PINS: dict[str, str] = {
    "pnnbao-ump/VieNeu-TTS-v3-Turbo": "61b85e3d937fbbacb387714180e8182823512523",   # head 2026-09-23
    "pnnbao-ump/VieNeu-TTS-v3-Nano": "aba295eb96a6fa6003ebe417cc1f2802a7adc1dc",    # head 2026-09-05
    "OpenMOSS-Team/MOSS-Audio-Tokenizer-Nano-ONNX": "ceff0d0749bfb3fa2d61149794ec6feef0d1e1ae",   # codec ONNX của Turbo
}


def pinned_kwargs(args: tuple, kwargs: dict, pins: dict[str, str] = PINS) -> dict:
    """Trả kwargs mới có `revision` ghim nếu repo (đối số đầu / repo_id=) nằm trong pins và chưa có revision."""
    repo = kwargs.get("repo_id") or (args[0] if args else None)
    if kwargs.get("revision") is None and repo in pins:   # revision là keyword-only trong hf_hub_download
        return {**kwargs, "revision": pins[repo]}
    return kwargs


def apply_revision_pins(pins: dict[str, str] = PINS) -> None:
    import huggingface_hub
    import huggingface_hub.file_download as file_download

    original = getattr(huggingface_hub.hf_hub_download, "_ted_original", huggingface_hub.hf_hub_download)

    def pinned_download(*args, **kwargs):
        return original(*args, **pinned_kwargs(args, kwargs, pins))

    pinned_download._ted_original = original   # gọi lại apply không bọc chồng
    huggingface_hub.hf_hub_download = pinned_download
    file_download.hf_hub_download = pinned_download
