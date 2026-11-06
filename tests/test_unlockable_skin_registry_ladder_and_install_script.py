"""Pack nhân vật mở khoá dần: bậc thang điều kiện (không ghi đè), registry/loader drop-in, script cài (dry-run, thu nhỏ, gỡ)."""

import json
import sys
from pathlib import Path

import pytest
from PIL import Image

from unlockable_skin_test_pack_helper import make_pack

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import install_unlockable_skin_packs as script  # noqa: E402

from src.core.unlockable_skin_ladder_assigner import LADDER, assign_new_skins, ladder_condition  # noqa: E402
from src.core.unlockable_skin_pack_loader import load_unlockable_collection  # noqa: E402
from src.core.unlockable_skin_registry_model import (  # noqa: E402
    METRIC_LABELS, REGISTRY_FILE_NAME, SkinCondition, UnlockableSkin, parse_condition, read_registry)


def _cands(n, pack="p"):
    return [(f"{pack}/c{i}", pack, f"C{i}", f"C{i}") for i in range(n)]


def test_ladder_has_36_valid_varied_conditions():
    assert len(LADDER) == 36
    assert all(c.type != "metric" or c.metric in METRIC_LABELS for c in LADDER)
    assert {c.type for c in LADDER} == {"badges", "metric"}
    assert len({tuple(c.to_json().items()) for c in LADDER}) == 36
    assert ladder_condition(60).type == "badges" and ladder_condition(60).count <= 50


def test_assign_never_overwrites_existing_conditions():
    hand = UnlockableSkin("p/c0", "p", "C0", "C0", SkinCondition("free"))
    result = assign_new_skins([hand], _cands(3))
    assert result[0] is hand                                   # giữ nguyên điều kiện sửa tay
    assert [s.key for s in result] == ["p/c0", "p/c1", "p/c2"]
    assert result[1].condition == LADDER[1] and result[2].condition == LADDER[2]
    assert assign_new_skins(result, _cands(3)) == result       # chạy lại: idempotent


@pytest.mark.parametrize("raw", [None, {"type": "badges"}, {"type": "metric", "metric": "nope", "value": 1},
                                 {"type": "badge", "id": " "}, {"type": "weird"}, {"type": "badges", "count": "x"}])
def test_parse_condition_rejects_malformed(raw):
    assert parse_condition(raw) is None


def test_loader_drop_in_pack_gets_ladder_and_broken_registry_entries_are_skipped(tmp_path):
    root = tmp_path / "root"
    make_pack(root / "pk", chars=("aa", "bb"))
    (root / REGISTRY_FILE_NAME).write_text(json.dumps({"skins": [
        {"key": "pk/bb", "pack": "pk", "unlock": {"type": "badges", "count": 7}},
        {"key": "pk/ghost", "pack": "pk", "unlock": {"type": "free"}},      # nhân vật không tồn tại trong pack
        {"key": "pk/aa", "unlock": {"type": "bogus"}},                      # điều kiện hỏng
    ]}), encoding="utf-8")
    col = load_unlockable_collection(root)
    assert [s.key for s in col.skins] == ["pk/bb", "pk/aa"]
    assert col.skins[0].condition.count == 7 and col.skins[1].condition.type in ("badges", "metric")
    assert set(col.characters) == {"pk/aa", "pk/bb"} and col.pack_titles == {"pk": "Pack pk"}
    assert load_unlockable_collection(tmp_path / "missing").skins == []


def test_script_dry_run_writes_nothing(tmp_path, capsys):
    src = tmp_path / "src"
    make_pack(src / "pk")
    out = tmp_path / "out"
    assert script.main(["--pack", "pk", "--source", str(src), "--target", str(out), "--dry-run", "--yes"]) == 0
    assert not out.exists() and "dry-run" in capsys.readouterr().out


def test_script_install_downscales_prunes_is_idempotent_and_keeps_hand_edits(tmp_path):
    src, out = tmp_path / "src", tmp_path / "out"
    make_pack(src / "pk", chars=("aa", "bb"))
    args = ["--pack", "pk", "--source", str(src), "--target", str(out), "--size", "64", "--yes"]
    assert script.main(args) == 0
    pngs = list((out / "pk").glob("*.png"))
    assert len(pngs) == 12 and not (out / "pk" / "unused_full_size.png").exists()   # 2 × (5 trạng thái + avatar)
    assert all(max(Image.open(p).size) <= 64 for p in pngs)
    assert Image.open(out / "pk" / "aa_idle.png").mode == "RGBA"
    reg = out / REGISTRY_FILE_NAME
    data = json.loads(reg.read_text(encoding="utf-8"))
    data["skins"][0]["unlock"] = {"type": "badge", "id": "focus_day_gold"}
    reg.write_text(json.dumps(data), encoding="utf-8")
    assert script.main(args) == 0                                   # cài lại
    skins = read_registry(reg)
    assert skins[0].condition.badge_id == "focus_day_gold" and len(skins) == 2
    assert not list(out.glob("*.tmp")) and not list(out.glob("*.old"))
    assert load_unlockable_collection(out).skins[0].key == "pk/aa"


def test_script_remove_and_list_and_missing_pack(tmp_path, capsys):
    src, out = tmp_path / "src", tmp_path / "out"
    make_pack(src / "pk")
    make_pack(src / "pj", chars=("zz",))
    assert script.main(["--pack", "pk", "--pack", "pj", "--source", str(src), "--target", str(out), "--yes"]) == 0
    assert script.main(["--remove", "pk", "--target", str(out)]) == 0
    assert not (out / "pk").exists() and [s.key for s in read_registry(out / REGISTRY_FILE_NAME)] == ["pj/zz"]
    assert script.main(["--list", "--source", str(src), "--target", str(out)]) == 0
    assert "pj/zz" in capsys.readouterr().out
    assert script.main(["--remove", "nope", "--target", str(out)]) == 1
    assert script.main(["--pack", "nope", "--source", str(src), "--target", str(out)]) == 1


def test_script_incomplete_pack_requires_confirmation(tmp_path, monkeypatch):
    src, out = tmp_path / "src", tmp_path / "out"
    make_pack(src / "pk", complete=False)
    monkeypatch.setattr("builtins.input", lambda _="": "n")
    assert script.main(["--pack", "pk", "--source", str(src), "--target", str(out)]) == 1
    assert script.main(["--pack", "pk", "--source", str(src), "--target", str(out), "--yes"]) == 0


def test_script_remove_refuses_paths_outside_target(tmp_path):
    out = tmp_path / "assets" / "out"
    make_pack(out / "pk")
    (tmp_path / "assets" / "keep.txt").write_text("x", encoding="utf-8")
    for bad in ("..", ".", "../out", str(tmp_path)):
        assert script.main(["--remove", bad, "--target", str(out)]) == 1
    assert (tmp_path / "assets" / "keep.txt").is_file() and (out / "pk").is_dir()


def test_loader_ignores_leftover_staging_and_backup_dirs(tmp_path):
    make_pack(tmp_path / "pk", chars=("aa",))
    make_pack(tmp_path / "pk.tmp", chars=("aa",))
    make_pack(tmp_path / "pk.old", chars=("aa",))
    assert [s.key for s in load_unlockable_collection(tmp_path).skins] == ["pk/aa"]


def test_uppercase_pack_and_character_ids_yield_lowercase_selectable_keys(tmp_path):
    from src.core.unlockable_skin_registry_model import skin_key
    assert skin_key("PK", "Aa") == "pk/aa"
    make_pack(tmp_path / "PK", chars=("Aa",))
    keys = [s.key for s in load_unlockable_collection(tmp_path).skins]
    assert keys == ["pk/aa"]                                   # FocusEngine.set_character hạ chữ thường → khớp
    reg = tmp_path / REGISTRY_FILE_NAME
    reg.write_text(json.dumps({"version": 1, "skins": [{"key": "PK/Aa", "unlock": {"type": "free"}}]}), encoding="utf-8")
    assert [s.key for s in read_registry(reg)] == ["pk/aa"]    # registry cũ chữ hoa vẫn khớp


def test_badge_condition_shows_badge_name_not_raw_id():
    from src.core.i18n import i18n
    from src.core.unlockable_skin_condition_evaluator import describe_condition
    from src.core.unlockable_skin_registry_model import SkinCondition
    previous = i18n.current_language
    try:
        i18n.set_language("en", emit_signal=False)
        text = describe_condition(SkinCondition("badge", badge_id="focus_first_session"))
        assert "First Dive" in text and "focus_first_session" not in text
        i18n.set_language("vi", emit_signal=False)
        assert "Lặn sâu lần đầu" in describe_condition(SkinCondition("badge", badge_id="focus_first_session"))
        assert "id_la" in describe_condition(SkinCondition("badge", badge_id="id_la"))   # id không có trong catalog → giữ id
    finally:
        i18n.set_language(previous, emit_signal=False)
