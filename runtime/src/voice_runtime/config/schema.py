"""Validated runtime configuration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AudioConfig(BaseModel):
    """Audio device and DSP settings. Sample rates are probed, not assumed."""

    input_device: str | None = None
    output_device: str | None = None
    preferred_sample_rate: int | None = Field(default=None, ge=8_000, le=192_000)
    block_ms: int = Field(default=10, ge=5, le=50)
    aec_enabled: bool = True
    echo_delay_ms: int = Field(default=40, ge=0, le=500)
    noise_suppression: bool = True


class EnginesConfig(BaseModel):
    """Adapter names and model locations. Implementations land in P3."""

    wake: Literal["sherpa_kws", "fake"] = "sherpa_kws"
    vad: Literal["silero", "fake"] = "silero"
    asr: Literal["sherpa_streaming", "fake"] = "sherpa_streaming"
    tts: Literal["kokoro", "fake"] = "kokoro"
    aec: Literal["webrtc_apm", "none"] = "webrtc_apm"
    model_dir: Path | None = None


class SessionConfig(BaseModel):
    """Voice-session timing and interruption behavior."""

    follow_up_window_seconds: float = Field(default=8.0, ge=1.0, le=60.0)
    max_utterance_seconds: float = Field(default=15.0, ge=1.0, le=120.0)
    vad_silence_ms: int = Field(default=450, ge=200, le=2000)
    barge_in_ms: int = Field(default=350, ge=100, le=2000)
    wake_verify_ms: int = Field(default=400, ge=100, le=1500)
    auto_speak: bool = True


class RuntimeConfig(BaseSettings):
    """Runtime configuration; environment variables use the DSH_VOICE_ prefix."""

    model_config = SettingsConfigDict(
        env_prefix="DSH_VOICE_",
        env_nested_delimiter="__",
        env_file_encoding="utf-8",
        extra="ignore",
        validate_assignment=True,
    )

    host: str = "127.0.0.1"
    port: int = Field(default=0, ge=0, le=65_535)
    protocol_version: int = Field(default=1, ge=1)
    auth_timeout_seconds: float = Field(default=5.0, ge=0.5, le=30.0)
    idle_timeout_seconds: float = Field(default=60.0, ge=0.5, le=3600.0)
    heartbeat_interval_seconds: float = Field(default=10.0, ge=2.0, le=60.0)
    max_connections: int = Field(default=8, ge=1, le=64)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    json_logs: bool = False
    data_dir: Path | None = None
    fake_audio: bool = False
    audio: AudioConfig = Field(default_factory=AudioConfig)
    engines: EnginesConfig = Field(default_factory=EnginesConfig)
    session: SessionConfig = Field(default_factory=SessionConfig)

    def resolved_data_dir(self, default: Path) -> Path:
        """Return the configured data dir, or the platform default."""
        return self.data_dir.expanduser() if self.data_dir is not None else default


def load_config(path: Path | None) -> RuntimeConfig:
    """Load defaults, an optional JSON file, then environment overrides.

    pydantic-settings precedence is init kwargs > environment > dotenv file >
    defaults, so passing `_env_file` keeps environment variables authoritative.
    """
    if path is None:
        return RuntimeConfig()
    if not path.exists():
        raise FileNotFoundError(f"config file not found: {path}")
    return RuntimeConfig(_env_file=path)  # type: ignore[call-arg]


def default_config_dict() -> dict[str, object]:
    """JSON-serializable default config for `config/default.json` and tests."""
    return RuntimeConfig().model_dump(mode="json")


def config_json_schema() -> dict[str, object]:
    """JSON Schema for editors and CI validation."""
    return RuntimeConfig.model_json_schema()


def dump_config(config: RuntimeConfig) -> str:
    return json.dumps(config.model_dump(mode="json"), ensure_ascii=False, indent=2)
