"""Manifest đóng gói trong modules/ hợp lệ; prompt path an toàn (Red Team #14)."""
import os
from pathlib import Path

from skill_sample_extraction_helper import REPO_ROOT

from src.modules_runtime.module_manifest_schema import ModuleManifest
from src.modules_runtime.module_registry_loader import load_manifests

LEARNERS = {"thcs": "con", "duhoc": "con", "caohoc": "bo"}


def _manifests():
    manifests, errors = load_manifests([REPO_ROOT / "modules"])
    assert errors == []
    return manifests


def test_all_four_shipped_manifests_load_without_errors():
    assert set(_manifests()) == {"work", "thcs", "duhoc", "caohoc"}


def test_coach_manifests_have_learner_ids_and_no_prompts_or_settings():
    manifests = _manifests()
    for module_id, learner in LEARNERS.items():
        m = manifests[module_id]
        assert m.engine == "coach" and m.learner_id == learner and not m.enabled
        assert not m.prompts and not m.settings


def test_work_manifest_enabled_and_prompt_files_exist():
    work = _manifests()["work"]
    assert work.enabled and work.engine == "work" and work.settings["calendar_days_ahead"] == 7
    assert work.prompts
    for key in work.prompts:
        path = work.prompt_path(key)
        assert path is not None and path.is_file(), key


def test_prompt_path_rejects_traversal_and_returns_normalized_path(tmp_path):
    module_dir = tmp_path / "Mod"
    (module_dir / "prompts").mkdir(parents=True)
    (module_dir / "prompts" / "a.md").write_text("x", encoding="utf-8")
    m = ModuleManifest(id="w", name="W", engine="work", connection="c", module_dir=module_dir,
                       prompts={"ok": "prompts/a.md", "evil": "../../outside.md"})
    assert m.prompt_path("ok") == Path(os.path.normcase(os.path.realpath(module_dir / "prompts" / "a.md")))
    assert m.prompt_path("evil") is None
    assert m.prompt_path("missing") is None
