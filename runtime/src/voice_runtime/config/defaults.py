"""Built-in configuration defaults, kept in code so a missing file is safe."""

from __future__ import annotations

from .schema import AudioConfig, EnginesConfig, RuntimeConfig, SessionConfig


def default_config() -> RuntimeConfig:
    """Return a fresh default config object."""
    return RuntimeConfig(
        audio=AudioConfig(),
        engines=EnginesConfig(),
        session=SessionConfig(),
    )
