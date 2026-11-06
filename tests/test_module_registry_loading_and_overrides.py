"""Registry: nạp manifest work/coach, từ chối schema sai, user dir ghi đè built-in, override enabled/connection, KV, engine host."""

import importlib
from pathlib import Path

import pytest
from sqlmodel import create_engine

from src.config import AppConfig
from src.core.app_state_key_value_store import KeyValueStore
from src.modules_runtime import module_engine_base_and_factory as factory
from src.modules_runtime.app_runtime_context import AppRuntimeContext
from src.modules_runtime.engine_fixed_menus import ENGINE_MENUS
from src.modules_runtime.module_engine_base_and_factory import ENGINE_CLASSES, ModuleEngineBase, ModuleEngineHost
from src.modules_runtime.module_manifest_schema import ModuleManifest
from src.modules_runtime.module_registry_loader import ModuleRegistry, default_module_dirs, load_manifests

COACH = "id: {id}\nname: Học\nengine: coach\nconnection: {id}\nlearner_id: con\n"
WORK = "id: work\nname: Việc\nengine: work\nconnection: work\nenabled: true\norder: 10\n"


def _write(base: Path, mod_id: str, text: str):
    (base / mod_id).mkdir(parents=True, exist_ok=True)
    (base / mod_id / "module.yaml").write_text(text, encoding="utf-8")


def _registry(tmp_path, dirs):
    return ModuleRegistry(AppConfig(data_dir=tmp_path / "home"), dirs=dirs)


def test_builtin_work_manifest_is_valid_and_prompts_resolve():
    manifests, errors = load_manifests(default_module_dirs()[:1])
    assert errors == []
    work = manifests["work"]
    assert work.engine == "work" and work.enabled and work.settings["calendar_days_ahead"] == 7
    assert work.prompt_path("cheers").is_file() and work.prompt_path("cheer").is_file()


def test_valid_work_and_coach_load(tmp_path):
    _write(tmp_path, "work", WORK)
    _write(tmp_path, "ly", COACH.format(id="ly"))
    manifests, errors = load_manifests([tmp_path])
    assert errors == [] and set(manifests) == {"work", "ly"}
    assert manifests["ly"].module_dir == tmp_path / "ly"


@pytest.mark.parametrize("text", [
    "id: x\nname: X\nengine: coach\nconnection: x\n",  # thiếu learner_id
    COACH.format(id="x") + "settings: {a: 1}\n",
    COACH.format(id="x") + "prompts: {a: b.md}\n",
    WORK + "menu: []\n",  # khoá lạ
    "id: x\nname: X\nengine: learning\nconnection: x\n",
    COACH.format(id="x").replace("learner_id: con", "learner_id: ../etc"),  # slug sai
    "- not a mapping\n",
    "id: [unclosed\n",
])
def test_invalid_manifests_rejected_and_collected(tmp_path, text):
    _write(tmp_path, "x", text)
    manifests, errors = load_manifests([tmp_path])
    assert manifests == {} and len(errors) == 1 and "module.yaml" in errors[0]


def test_user_dir_overrides_builtin_and_bad_module_does_not_block_others(tmp_path):
    builtin, user = tmp_path / "b", tmp_path / "u"
    _write(builtin, "ly", COACH.format(id="ly"))
    _write(user, "ly", COACH.format(id="ly").replace("name: Học", "name: Người dùng"))
    _write(user, "bad", "engine: nope\n")
    manifests, errors = load_manifests([builtin, user])
    assert manifests["ly"].name == "Người dùng" and len(errors) == 1


def test_prompt_path_traversal_rejected(tmp_path):
    (tmp_path / "secret.md").write_text("s", encoding="utf-8")
    mod = tmp_path / "m"
    mod.mkdir()
    (mod / "ok.md").write_text("ok", encoding="utf-8")
    m = ModuleManifest(id="w", name="W", engine="work", connection="c",
                       prompts={"ok": "ok.md", "up": "../secret.md", "abs": str(tmp_path / "secret.md")})
    m.module_dir = mod
    assert m.prompt_path("ok") is not None
    assert m.prompt_path("up") is None and m.prompt_path("abs") is None


def test_enabled_override_true_false_none(tmp_path):
    _write(tmp_path / "mods", "work", WORK)
    _write(tmp_path / "mods", "ly", COACH.format(id="ly"))
    reg = _registry(tmp_path, [tmp_path / "mods"])
    assert [m.id for m in reg.enabled()] == ["work"]  # None -> theo manifest
    reg._config.set_module_override("ly", enabled=True)
    reg._config.set_module_override("work", enabled=False)
    assert [m.id for m in reg.enabled()] == ["ly"]
    reg._config.set_module_override("work", enabled=None)
    assert reg.is_enabled("work") and not reg.is_enabled("missing")


def test_connection_override(tmp_path):
    _write(tmp_path / "mods", "ly", COACH.format(id="ly"))
    reg = _registry(tmp_path, [tmp_path / "mods"])
    assert reg.connection_for("ly") == "ly" and reg.connection_for("zzz") is None
    reg._config.set_module_override("ly", connection="other")
    assert reg.connection_for("ly") == "other"


def test_active_falls_back_when_disabled_and_none_when_nothing_enabled(tmp_path):
    _write(tmp_path / "mods", "work", WORK)
    _write(tmp_path / "mods", "ly", COACH.format(id="ly") + "enabled: true\norder: 20\n")
    reg = _registry(tmp_path, [tmp_path / "mods"])
    reg._config.active_module = "ly"
    assert reg.active().id == "ly"
    reg._config.set_module_override("ly", enabled=False)
    assert reg.active().id == "work"
    reg._config.set_module_override("work", enabled=False)
    assert reg.active() is None


def test_set_enabled_persists_to_settings_json_and_emits(tmp_path):
    _write(tmp_path / "mods", "ly", COACH.format(id="ly"))
    reg = _registry(tmp_path, [tmp_path / "mods"])
    emitted = []
    reg.modules_changed.connect(lambda: emitted.append(1))
    reg.set_enabled("ly", True)
    assert emitted == [1] and AppConfig(data_dir=tmp_path / "home").module_override("ly").enabled is True
    reg.set_enabled("unknown", True)  # id lạ: không emit
    assert emitted == [1]


def test_find_by_engine_and_fixed_menus(tmp_path):
    _write(tmp_path / "mods", "work", WORK)
    _write(tmp_path / "mods", "ly", COACH.format(id="ly") + "enabled: true\n")
    reg = _registry(tmp_path, [tmp_path / "mods"])
    assert [m.id for m in reg.find_by_engine("work")] == ["work"]
    assert [a.id for a in ENGINE_MENUS["coach"]] == ["today", "review_now", "ask", "progress", "sync"]
    assert [a.id for a in ENGINE_MENUS["work"]] == ["briefing", "tasks", "ask", "rocks", "calendar"]


def test_kv_store_roundtrip_overwrite_and_corrupt_json():
    kv = KeyValueStore(create_engine("sqlite://"))
    assert kv.get("a") is None and kv.get("a", "d") == "d"
    kv.set("a", "1")
    kv.set("a", "2")
    assert kv.get("a") == "2"
    kv.set_json("j", {"x": [1, "é"]})
    assert kv.get_json("j") == {"x": [1, "é"]}
    kv.set("bad", "{oops")
    assert kv.get_json("bad", default=[]) == []


def test_every_table_module_importable_or_only_missing():
    from src.core.register_all_table_models import TABLE_MODULES
    for name in TABLE_MODULES:
        try:
            importlib.import_module(name)
        except ModuleNotFoundError as e:
            assert e.name == name


class _Boom(ModuleEngineBase):
    def start(self):
        raise RuntimeError("boom")


class _Ok(ModuleEngineBase):
    log: list = []

    def start(self):
        self.log.append("start")

    def stop(self):
        self.log.append("stop")

    def handle_action(self, action_id):
        self.log.append(action_id)


def test_engine_host_isolates_failures_and_syncs(tmp_path, monkeypatch):
    _write(tmp_path / "mods", "work", WORK)
    _write(tmp_path / "mods", "ly", COACH.format(id="ly") + "enabled: true\n")
    reg = _registry(tmp_path, [tmp_path / "mods"])
    monkeypatch.setattr(factory, "load_engine_class", lambda e: _Ok if e == "work" else _Boom)
    _Ok.log = []
    host = ModuleEngineHost(AppRuntimeContext(registry=reg))
    host.sync()
    assert set(host.engines) == {"work"}  # coach start lỗi -> bị bỏ qua, không raise
    host.dispatch("work", "briefing")
    host.dispatch("ghost", "x")
    reg._config.set_module_override("work", enabled=False)
    host.sync()
    assert host.engines == {} and _Ok.log == ["start", "briefing", "stop"]


def test_missing_engine_module_is_skipped_not_fatal(tmp_path):
    _write(tmp_path / "mods", "ly", COACH.format(id="ly") + "enabled: true\n")
    reg = _registry(tmp_path, [tmp_path / "mods"])
    host = ModuleEngineHost(AppRuntimeContext(registry=reg))
    host.sync()  # engine coach chưa có (phase 06+) -> không crash
    assert set(ENGINE_CLASSES) == {"work", "coach"}
