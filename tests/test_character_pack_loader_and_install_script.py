"""Character Pack: chuẩn hoá ảnh trạng thái từ characters.json, script cài pack (--pack / none / hỏi khi thiếu),
persona (tên, giọng, câu thoại) lấy từ pack và câu click trộn expressions theo mood."""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.config import settings
from src.core import character_persona_profiles as personas
from src.core.character_pack_loader import STATE_IDS, load_character_pack
from src.modules_runtime.cheer_line_provider import CheerLineProvider

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import install_character_pack  # noqa: E402

REAL_PACKS = Path(__file__).resolve().parents[2] / "docs" / "UI" / "characters"


def _png(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG fake")


def _make_pack(root: Path, complete=True) -> Path:
    """4 kiểu khai báo ảnh: mood_images (linh), assets.animations (an), quy ước {id}_{state} (khoa),
    quy ước theo tên file avatar (mai: id "mai" nhưng ảnh "char_04_mai_*.png")."""
    root.mkdir(parents=True, exist_ok=True)
    for state in STATE_IDS:
        _png(root / "animations" / f"linh_{state}.png")
        _png(root / "anim2" / f"an_{state}.png")
        if complete or state != "rest":
            _png(root / f"khoa_{state}.png")
        _png(root / "animations" / f"char_04_mai_{state}.png")
    _png(root / "khoa.png")
    (root / "bundle.zip").write_bytes(b"zip")
    (root / "preview.html").write_text("x", encoding="utf-8")
    data = {
        "pack_id": "test-pack",
        "default_character_id": "an",
        "characters": [
            {"id": "linh", "display_name": "Linh", "personality_key": "sweet",
             "voice_config": {"voice_vi": "vi-VN-HoaiMyNeural", "local_voice_vi": "piper-vi", "speed": 9},
             "catchphrases": ["Linh đây!"], "expressions": {"focus": ["Tập trung nào."], "idle": []},
             "mood_images": {s: f"animations/linh_{s}.png" for s in STATE_IDS}},
            {"id": "an", "name": "An (Áo dài)", "personality_key": "unknown",
             "assets": {"animations": {s: f"anim2/an_{s}.png" for s in STATE_IDS}}},
            {"id": "khoa", "avatar_file": "khoa.png"},
            {"id": "mai", "avatar_file": "char_04_mai.png"},
            {"id": ""},
        ],
    }
    (root / "characters.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return root


def test_loader_resolves_all_image_conventions_and_defaults(tmp_path):
    pack = load_character_pack(_make_pack(tmp_path / "p"))
    assert pack.id == "test-pack" and pack.default_character_id == "an"
    assert list(pack.characters) == ["linh", "an", "khoa", "mai"]
    assert pack.missing_report() == {}
    assert pack.characters["an"].display_name == "An (Áo dài)"
    assert pack.characters["linh"].expressions == {"focus": ["Tập trung nào."]}
    assert pack.characters["khoa"].image_for("cheer").name == "khoa_cheer.png"
    assert pack.characters["mai"].image_for("rest").name == "char_04_mai_rest.png"


def test_loader_reports_missing_state_and_falls_back_to_idle(tmp_path):
    pack = load_character_pack(_make_pack(tmp_path / "p", complete=False))
    assert pack.missing_report() == {"khoa": ["rest"]}
    assert pack.characters["khoa"].image_for("rest").name == "khoa_idle.png"


def test_loader_rejects_missing_or_broken_manifest(tmp_path):
    assert load_character_pack(tmp_path) is None
    (tmp_path / "characters.json").write_text("{broken", encoding="utf-8")
    assert load_character_pack(tmp_path) is None
    (tmp_path / "characters.json").write_text('{"characters": []}', encoding="utf-8")
    assert load_character_pack(tmp_path) is None


@pytest.mark.parametrize("name", ["00_cute_animals", "vietnam-chibi-pack", "25_chibi_vietnam_students_actions"])
def test_shipped_animated_packs_are_complete(name):
    if not (REAL_PACKS / name).is_dir():
        pytest.skip("không có docs/UI/characters")
    pack = load_character_pack(REAL_PACKS / name)
    assert pack is not None and pack.missing_report() == {}


def test_install_copies_whole_pack_without_zip(tmp_path):
    src, target = _make_pack(tmp_path / "src"), tmp_path / "assets" / "character_pack"
    _png(target / "old.png")
    assert install_character_pack.main(["--pack", str(src), "--target", str(target)]) == 0
    assert (target / "characters.json").is_file() and (target / "animations" / "linh_idle.png").is_file()
    assert not (target / "bundle.zip").exists() and not (target / "preview.html").exists()
    assert not (target / "old.png").exists() and not target.with_name("character_pack.tmp").exists()


def test_install_by_name_and_unknown_pack(tmp_path):
    _make_pack(tmp_path / "packs" / "demo")
    target = tmp_path / "out"
    args = ["--packs-root", str(tmp_path / "packs"), "--target", str(target)]
    assert install_character_pack.main(["--pack", "nope", *args]) == 1
    assert install_character_pack.main(["--pack", "demo", *args]) == 0
    assert (target / "characters.json").is_file()


def test_incomplete_pack_asks_and_keeps_old_pack_when_declined(tmp_path, monkeypatch):
    src, target = _make_pack(tmp_path / "src", complete=False), tmp_path / "out"
    _png(target / "keep.png")
    monkeypatch.setattr("builtins.input", lambda _q: "n")
    assert install_character_pack.main(["--pack", str(src), "--target", str(target)]) == 1
    assert (target / "keep.png").is_file()
    monkeypatch.setattr("builtins.input", lambda _q: "y")
    assert install_character_pack.main(["--pack", str(src), "--target", str(target)]) == 0
    monkeypatch.setattr("builtins.input", lambda _q: pytest.fail("không --pack thì không hỏi lại"))
    assert install_character_pack.main(["--target", str(target)]) == 0   # pack đang cài thiếu ảnh: chỉ cảnh báo


def test_character_without_any_image_blocks_install_even_with_yes(tmp_path):
    src = _make_pack(tmp_path / "src")
    data = json.loads((src / "characters.json").read_text(encoding="utf-8"))
    data["characters"].append({"id": "ghost"})
    (src / "characters.json").write_text(json.dumps(data), encoding="utf-8")
    assert install_character_pack.main(["--pack", str(src), "--target", str(tmp_path / "out"), "--yes"]) == 1
    assert not (tmp_path / "out").exists()


def test_none_removes_installed_pack(tmp_path):
    target = _make_pack(tmp_path / "out")
    assert install_character_pack.main(["--pack", "none", "--target", str(target)]) == 0
    assert not target.exists()
    assert install_character_pack.main(["--target", str(target)]) == 0


@pytest.fixture
def pack_personas(tmp_path, monkeypatch):
    monkeypatch.setattr(personas, "PACK_CHARACTERS", load_character_pack(_make_pack(tmp_path / "p")).characters)
    monkeypatch.setattr(settings, "character_personas", {})
    monkeypatch.setattr(settings, "character_skin", "linh")


def test_pack_persona_applies_without_saving_and_saved_values_win(pack_personas, monkeypatch):
    persona = personas.saved_persona()
    assert (persona.name, persona.personality, persona.voice_vi, persona.local_voice_vi, persona.speed) == \
        ("Linh", "sweet", "", "piper-vi", 2.0)   # giọng máy chủ để trống = theo Cài đặt chung
    assert persona.catchphrases() == ["Linh đây!"] and persona.mood_lines("focus") == ["Tập trung nào."]
    assert personas.active_voice_override() is not None
    assert personas.saved_persona("an").personality == "cheerful"           # key lạ → tính cách mặc định
    assert personas.saved_persona("an").catchphrases()                      # không có câu riêng → câu của tính cách
    monkeypatch.setattr(settings, "character_personas", {"linh": {"name": "Linh Nhỏ", "speed": 1.1, "voice_vi": "v1"}})
    saved = personas.saved_persona()
    assert (saved.name, saved.speed, saved.voice_vi, saved.local_voice_vi) == ("Linh Nhỏ", 1.1, "v1", "piper-vi")
    assert saved.catchphrases() == ["Linh đây!"]   # lưu đè vẫn giữ câu thoại của pack


def test_click_line_mixes_pack_expressions_for_current_mood(pack_personas):
    focus = SimpleNamespace(current_mood="FOCUS")
    seen = []
    rng = SimpleNamespace(random=lambda: 0.0, choice=lambda lines: seen.append(lines) or lines[0])
    provider = CheerLineProvider(SimpleNamespace(get=lambda i: None), None, focus_engine=focus, rng=rng)
    provider.pick_local(None)
    assert seen == [["Linh đây!", "Tập trung nào."]]


def test_pack_pixmap_is_decoded_once_and_scaled(tmp_path):
    from PySide6.QtGui import QImage
    from qt_offscreen_app_helper import get_qapp
    from src.ui.companion_widget import PACK_PIXMAP_PX, TedCompanionWidget
    get_qapp()
    image = tmp_path / "big.png"
    QImage(400, 800, QImage.Format.Format_ARGB32).save(str(image))
    fake = SimpleNamespace(_pack_pixmap_cache={})
    first = TedCompanionWidget._pack_pixmap(fake, image)
    assert TedCompanionWidget._pack_pixmap(fake, image) is first     # lần 2 lấy từ cache, không decode lại
    assert (first.width(), first.height()) == (PACK_PIXMAP_PX // 2, PACK_PIXMAP_PX)
    assert TedCompanionWidget._pack_pixmap(fake, None) is None
