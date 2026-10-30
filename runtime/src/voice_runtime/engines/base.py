"""Engine adapter interfaces.

Concrete sherpa-onnx / livekit adapters land in P2/P3. The interfaces are
deliberately narrow so the Session Manager never imports an engine SDK directly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from enum import StrEnum

import numpy as np


class EngineKind(StrEnum):
    WAKE = "wake"
    VAD = "vad"
    ASR = "asr"
    TTS = "tts"
    AEC = "aec"


@dataclass(frozen=True)
class EngineHealth:
    kind: EngineKind
    name: str
    ok: bool
    detail: str = ""


class AudioEngine(ABC):
    """Common lifecycle for every engine adapter."""

    kind: EngineKind

    def __init__(self, name: str) -> None:
        self.name = name
        self._initialized = False

    @property
    def initialized(self) -> bool:
        return self._initialized

    async def initialize(self) -> None:
        self._initialized = True

    async def reset(self) -> None:
        return None

    async def shutdown(self) -> None:
        self._initialized = False

    async def health(self) -> EngineHealth:
        return EngineHealth(self.kind, self.name, self._initialized)


class WakeEngine(AudioEngine):
    kind = EngineKind.WAKE

    @abstractmethod
    async def detect(self, frame: np.ndarray) -> str | None:
        """Return the matched keyword, or None."""


class VADEngine(AudioEngine):
    kind = EngineKind.VAD

    @abstractmethod
    async def process(self, frame: np.ndarray) -> bool:
        """Return True when the frame contains speech."""


class ASREngine(AudioEngine):
    kind = EngineKind.ASR

    @abstractmethod
    async def start_stream(self) -> None: ...

    @abstractmethod
    async def accept_audio(self, samples: np.ndarray) -> None: ...

    @abstractmethod
    async def get_partial_result(self) -> str: ...

    @abstractmethod
    async def get_final_result(self) -> str: ...


class TTSEngine(AudioEngine):
    kind = EngineKind.TTS

    #: Output sample rate, set by the adapter after initialization.
    sample_rate: int = 0

    @abstractmethod
    def synthesize_stream(self, text: str) -> AsyncIterator[np.ndarray]:
        """Yield float32 mono chunks at the engine's sample rate."""

    @abstractmethod
    async def cancel(self) -> None: ...


class AECProcessor(AudioEngine):
    kind = EngineKind.AEC

    @abstractmethod
    async def process(self, microphone: np.ndarray, reference: np.ndarray) -> np.ndarray: ...
