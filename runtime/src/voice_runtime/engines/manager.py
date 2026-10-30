"""Engine registry and lifecycle management."""

from __future__ import annotations

import logging
from typing import cast

from .base import (
    AECProcessor,
    ASREngine,
    AudioEngine,
    EngineHealth,
    EngineKind,
    TTSEngine,
    VADEngine,
    WakeEngine,
)

logger = logging.getLogger(__name__)


class EngineManager:
    """Owns exactly one active adapter per engine kind."""

    def __init__(self) -> None:
        self._engines: dict[EngineKind, AudioEngine] = {}

    def register(self, engine: AudioEngine) -> None:
        if engine.kind in self._engines:
            raise ValueError(f"engine already registered for {engine.kind}")
        self._engines[engine.kind] = engine

    def get(self, kind: EngineKind) -> AudioEngine | None:
        return self._engines.get(kind)

    def wake(self) -> WakeEngine | None:
        return cast(WakeEngine | None, self.get(EngineKind.WAKE))

    def vad(self) -> VADEngine | None:
        return cast(VADEngine | None, self.get(EngineKind.VAD))

    def asr(self) -> ASREngine | None:
        return cast(ASREngine | None, self.get(EngineKind.ASR))

    def tts(self) -> TTSEngine | None:
        return cast(TTSEngine | None, self.get(EngineKind.TTS))

    def aec(self) -> AECProcessor | None:
        return cast(AECProcessor | None, self.get(EngineKind.AEC))

    async def initialize_all(self) -> None:
        for engine in self._engines.values():
            await engine.initialize()

    async def health(self) -> list[EngineHealth]:
        return [await engine.health() for engine in self._engines.values()]

    async def shutdown_all(self) -> None:
        for engine in self._engines.values():
            try:
                await engine.shutdown()
            except Exception:  # noqa: BLE001 - shutdown must continue
                logger.exception("engine shutdown failed", extra={"engine": engine.name})

    async def reset_all(self) -> None:
        for engine in self._engines.values():
            await engine.reset()
