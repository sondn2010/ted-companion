import json

import pytest

from src.config import AppConfig
from src.core.connection_registry_and_settings_migration import (
    SETTINGS_SCHEMA_VERSION,
    HermesConnection,
    migrate_settings_payload,
)

V1_PAYLOAD = {
    "character_skin": "panda",
    "mode": "vps",
    "local_base_url": "http://127.0.0.1:8642/v1",
    "local_api_key": "local-secret",
    "vps_base_url": "http://100.1.2.3:8642/v1/",
    "vps_api_key": "vps-secret",
    "model_name": "hermes-agent",
    "default_pomodoro_mins": 30,
    "mindful_ping_mins": 10,
    "ambient_sound_enabled": True,
}


def _write(dir_path, payload) -> None:
    (dir_path / "settings.json").write_text(json.dumps(payload), encoding="utf-8")


def test_v1_vps_mode_becomes_two_connections_with_work_on_vps():
    payload, changed = migrate_settings_payload(V1_PAYLOAD, env={})
    assert changed
    assert payload["schema_version"] == SETTINGS_SCHEMA_VERSION
    assert [c["id"] for c in payload["connections"]] == ["local", "vps"]
    assert payload["connections"][1]["api_key"] == "vps-secret"
    assert payload["modules"] == {"work": {"connection": "vps"}}
    assert payload["active_module"] == "work"
    for dropped in ("mode", "local_base_url", "vps_api_key", "model_name"):
        assert dropped not in payload
    assert payload["default_pomodoro_mins"] == 30


def test_v1_local_mode_keeps_local_and_identical_urls_are_not_deduped():
    raw = {**V1_PAYLOAD, "mode": "local", "vps_base_url": V1_PAYLOAD["local_base_url"]}
    payload, _ = migrate_settings_payload(raw, env={})
    assert payload["modules"]["work"]["connection"] == "local"
    assert len(payload["connections"]) == 2


def test_env_only_first_run_seeds_connections_from_env():
    env = {"HERMES_LOCAL_BASE_URL": "http://10.0.0.5:9000/v1", "HERMES_MODEL_NAME": "custom", "TED_CONNECTION_MODE": "vps"}
    payload, changed = migrate_settings_payload({}, env)
    assert changed
    assert payload["connections"][0]["base_url"] == "http://10.0.0.5:9000/v1"
    assert all(c["model"] == "custom" for c in payload["connections"])
    assert payload["modules"]["work"]["connection"] == "vps"


def test_v2_payload_is_idempotent():
    v2, _ = migrate_settings_payload(V1_PAYLOAD, env={})
    again, changed = migrate_settings_payload(v2, env={"HERMES_LOCAL_BASE_URL": "http://other/v1"})
    assert not changed
    assert again == v2


def test_connection_validates_scheme_and_strips_trailing_slash():
    conn = HermesConnection(id="vps", name="VPS", base_url="https://h.example/v1/")
    assert conn.base_url == "https://h.example/v1"
    with pytest.raises(ValueError):
        HermesConnection(id="bad", name="Bad", base_url="ftp://h.example")
    with pytest.raises(ValueError):
        HermesConnection(id="Bad Id", name="Bad", base_url="http://h")


def test_app_config_migrates_file_writes_backup_once_and_resolves_work_connection(tmp_path):
    _write(tmp_path, V1_PAYLOAD)
    config = AppConfig(data_dir=tmp_path)
    saved = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    backup = json.loads((tmp_path / "settings.json.bak").read_text(encoding="utf-8"))
    assert saved["schema_version"] == 2 and len(saved["connections"]) == 2
    assert backup == V1_PAYLOAD
    work_conn_id = config.module_override("work").connection
    assert work_conn_id == "vps"
    assert config.get_connection(work_conn_id).base_url == "http://100.1.2.3:8642/v1"
    assert config.character_skin == "panda"

    # Lần load thứ 2 (đã là v2): .bak không bị ghi đè
    AppConfig(data_dir=tmp_path)
    assert json.loads((tmp_path / "settings.json.bak").read_text(encoding="utf-8")) == V1_PAYLOAD


def test_corrupt_settings_file_is_not_overwritten(tmp_path):
    (tmp_path / "settings.json").write_text("{not json", encoding="utf-8")
    config = AppConfig(data_dir=tmp_path)
    assert (tmp_path / "settings.json").read_text(encoding="utf-8") == "{not json"
    assert not (tmp_path / "settings.json.bak").exists()
    assert config.connections  # vẫn có kết nối mặc định để app chạy được


def test_connection_crud_refuses_deleting_used_or_last_connection(tmp_path):
    _write(tmp_path, V1_PAYLOAD)
    config = AppConfig(data_dir=tmp_path)
    assert "work" in (config.delete_connection("vps") or "")
    config.upsert_connection(HermesConnection(id="tutor", name="Tutor", base_url="http://t/v1"))
    config.set_module_override("work", connection="tutor")
    assert config.delete_connection("vps") is None
    assert config.delete_connection("local") is None
    assert config.delete_connection("tutor") is not None  # module work dùng + là kết nối cuối
    config.save()
    reloaded = AppConfig(data_dir=tmp_path)
    assert [c.id for c in reloaded.connections] == ["tutor"]
    assert reloaded.module_override("work").connection == "tutor"


def test_unknown_keys_survive_save(tmp_path):
    v2, _ = migrate_settings_payload(V1_PAYLOAD, env={})
    _write(tmp_path, {**v2, "future_key": {"x": 1}})
    config = AppConfig(data_dir=tmp_path)
    config.save()
    assert json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))["future_key"] == {"x": 1}


def test_newer_schema_file_is_read_only_and_never_overwritten(tmp_path):
    v3 = {"schema_version": 3, "connections": [{"id": "x", "name": "X", "base_url": "http://x/v1"}], "new_thing": 1}
    _write(tmp_path, v3)
    config = AppConfig(data_dir=tmp_path)
    assert config.read_only and [c.id for c in config.connections] == ["x"]
    config.save()
    assert json.loads((tmp_path / "settings.json").read_text(encoding="utf-8")) == v3


def test_wrong_value_types_fall_back_to_defaults_instead_of_crashing(tmp_path):
    v2, _ = migrate_settings_payload(V1_PAYLOAD, env={})
    _write(tmp_path, {**v2, "default_pomodoro_mins": None, "mindful_ping_mins": "abc"})
    config = AppConfig(data_dir=tmp_path)
    assert isinstance(config.default_pomodoro_mins, int) and isinstance(config.mindful_ping_mins, int)


def test_corrupt_file_is_backed_up_before_any_later_save(tmp_path):
    (tmp_path / "settings.json").write_text("{not json", encoding="utf-8")
    config = AppConfig(data_dir=tmp_path)
    config.save()
    backups = list(tmp_path.glob("settings.json.corrupt-*"))
    assert len(backups) == 1 and backups[0].read_text(encoding="utf-8") == "{not json"
    assert not list(tmp_path.glob("*.tmp"))


def test_v1_url_without_scheme_gets_http_prefix_instead_of_being_dropped():
    payload, _ = migrate_settings_payload({**V1_PAYLOAD, "local_base_url": "127.0.0.1:8080/v1"}, env={})
    assert HermesConnection.model_validate(payload["connections"][0]).base_url == "http://127.0.0.1:8080/v1"


def test_base_url_without_host_is_rejected():
    for bad in ("http://", "https:///v1", "http://a b/v1"):
        with pytest.raises(ValueError):
            HermesConnection(id="bad", name="Bad", base_url=bad)


def test_invalid_connection_log_does_not_leak_api_key(tmp_path, caplog):
    v2, _ = migrate_settings_payload(V1_PAYLOAD, env={})
    v2["connections"].append({"id": "broken", "api_key": "sk-leak-me", "base_url": "http://b/v1"})
    _write(tmp_path, v2)
    with caplog.at_level("WARNING", logger="ted"):
        AppConfig(data_dir=tmp_path)
    assert "broken" in caplog.text and "sk-leak-me" not in caplog.text
