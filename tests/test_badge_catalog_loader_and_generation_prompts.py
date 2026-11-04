"""Test catalog huy hiệu (load + validate) và dựng prompt/seed sinh ảnh — không gọi mạng."""
import importlib.util
import json
from pathlib import Path

import pytest

from src.core.gamification.badge_catalog_loader import (
    BADGES_DIR, CatalogError, load_badge_catalog,
)

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "generate_badge_images.py"


@pytest.fixture(scope="module")
def gen():
    spec = importlib.util.spec_from_file_location("generate_badge_images", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def catalog():
    return load_badge_catalog(strict=True)


def test_catalog_has_53_unique_ids(catalog):
    ids = [b.id for b in catalog.badges]
    assert len(ids) == 53 and len(set(ids)) == 53


def test_every_badge_image_exists(catalog):
    missing = [b.image for b in catalog.badges if not b.image_path().exists()]
    assert not missing
    assert (BADGES_DIR / catalog.locked_image).exists()


def test_rules_and_texts_valid(catalog):
    for b in catalog.badges:
        assert b.name["vi"] and b.name["en"] and b.desc["vi"] and b.desc["en"]
        assert b.rule.window in ("day", "week", "lifetime")


def test_prompt_and_seed_deterministic(gen, catalog):
    b = catalog.badges[3]
    phrase = catalog.tier_phrases[b.tier]
    p1 = gen.build_prompt(catalog.style_prefix, phrase, b.prompt)
    assert p1 == gen.build_prompt(catalog.style_prefix, phrase, b.prompt)
    assert "{TIER}" not in p1 and phrase in p1 and p1.endswith(f"in the center: {b.prompt}")
    assert gen.seed_for(b.prompt) == gen.seed_for(b.prompt)
    assert 0 <= gen.seed_for(b.prompt) < 2**31


def test_same_subject_tiers_share_seed(gen, catalog):
    by_subject = {}
    for b in catalog.badges:
        by_subject.setdefault(b.prompt, set()).add(gen.seed_for(b.prompt))
    assert all(len(s) == 1 for s in by_subject.values())


def test_mmx_command_base64_flag(gen, tmp_path):
    out = tmp_path / "x.jpg"
    assert "--response-format" not in gen.mmx_command("p", 1, out)
    assert gen.mmx_command("p", 1, out, base64=True)[-2:] == ["--response-format", "base64"]


def _write(tmp_path, mutate):
    data = json.loads((BADGES_DIR / "badge_catalog.json").read_text(encoding="utf-8"))
    mutate(data)
    p = tmp_path / "c.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return p


def test_invalid_metric_skipped_or_raises(tmp_path):
    p = _write(tmp_path, lambda d: d["badges"][0]["rule"].update(metric="bogus"))
    assert len(load_badge_catalog(p).badges) == 52
    with pytest.raises(CatalogError):
        load_badge_catalog(p, strict=True)


def test_duplicate_id_rejected_in_strict(tmp_path):
    p = _write(tmp_path, lambda d: d["badges"][1].update(id=d["badges"][0]["id"]))
    with pytest.raises(CatalogError):
        load_badge_catalog(p, strict=True)


def test_missing_file_raises(tmp_path):
    with pytest.raises(CatalogError):
        load_badge_catalog(tmp_path / "nope.json")
