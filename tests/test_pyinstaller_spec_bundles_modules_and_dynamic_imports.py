"""Kiểm tra cấu hình build (không chạy PyInstaller): modules/, tzdata (Red Team #6), hiddenimports lazy (Red Team #14)."""
from pathlib import Path
from skill_sample_extraction_helper import REPO_ROOT

COMPANION_DIR = Path(__file__).resolve().parent.parent
SPEC_FILE = COMPANION_DIR / "TedCompanion.spec"
if not SPEC_FILE.is_file():
    SPEC_FILE = REPO_ROOT / "ted-companion" / "TedCompanion.spec"
SPEC = SPEC_FILE.read_text(encoding="utf-8")


def test_spec_bundles_modules_dir_and_tzdata_once():
    assert SPEC.count('project_dir / "modules"') == 1
    assert SPEC.count('collect_data_files("tzdata")') == 1 and SPEC.count('"tzdata",') == 1


def test_spec_declares_yaml_engines_and_table_modules_as_hidden_imports():
    assert '"yaml"' in SPEC
    assert 'collect_submodules("src.engines")' in SPEC   # work_module_engine + coach_module_engine
    assert "register_all_table_models.py" in SPEC        # TABLE_MODULES được rút từ chính file đăng ký
    assert (COMPANION_DIR / "modules" / "work" / "module.yaml").is_file() or (REPO_ROOT / "modules" / "work" / "module.yaml").is_file()


def test_spec_compiles_as_python():
    compile(SPEC, "TedCompanion.spec", "exec")
