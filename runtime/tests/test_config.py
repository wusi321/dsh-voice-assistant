import json
from pathlib import Path

import jsonschema

from voice_runtime.config.schema import (
    RuntimeConfig,
    config_json_schema,
    default_config_dict,
    load_config,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_defaults_are_localhost_and_dynamic_port() -> None:
    config = RuntimeConfig()
    assert config.host == "127.0.0.1"
    assert config.port == 0
    assert config.protocol_version == 1
    assert config.audio.aec_enabled is True


def test_env_override(monkeypatch) -> None:
    monkeypatch.setenv("DSH_VOICE_PORT", "23456")
    monkeypatch.setenv("DSH_VOICE_LOG_LEVEL", "DEBUG")
    config = RuntimeConfig()
    assert config.port == 23456
    assert config.log_level == "DEBUG"


def test_load_json_and_env_precedence(tmp_path, monkeypatch) -> None:
    path: Path = tmp_path / "config.json"
    path.write_text(json.dumps({"port": 11111, "host": "127.0.0.1"}), encoding="utf-8")
    monkeypatch.setenv("DSH_VOICE_PORT", "22222")
    config = load_config(path)
    assert config.port == 22222


def test_invalid_port_is_rejected() -> None:
    try:
        RuntimeConfig(port=70000)
    except ValueError:
        return
    raise AssertionError("expected validation error")


def test_default_dict_and_schema_are_json_safe() -> None:
    data = default_config_dict()
    assert data["host"] == "127.0.0.1"
    json.dumps(data)  # must not raise
    schema = config_json_schema()
    assert "properties" in schema
    assert "port" in schema["properties"]


def test_committed_config_matches_schema() -> None:
    data = json.loads((PROJECT_ROOT / "config" / "default.json").read_text(encoding="utf-8"))
    schema = json.loads((PROJECT_ROOT / "config" / "schema.json").read_text(encoding="utf-8"))
    jsonschema.validate(data, schema)
    assert data == default_config_dict()
