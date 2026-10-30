"""sherpa-onnx Silero VAD adapter."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from voice_runtime.engines.base import VADEngine
from voice_runtime.engines.models import prepare_sherpa_runtime


@dataclass(frozen=True)
class VADSegment:
    samples: np.ndarray
    start_sample: int


class SherpaVAD(VADEngine):
    """Silero VAD fed in exact 512-sample windows."""

    WINDOW = 512

    def __init__(
        self,
        model_path: Path,
        *,
        threshold: float = 0.5,
        min_silence: float = 0.45,
        min_speech: float = 0.15,
        sample_rate: int = 16_000,
    ) -> None:
        super().__init__("sherpa-silero-vad")
        self.model_path = model_path
        self.threshold = threshold
        self.min_silence = min_silence
        self.min_speech = min_speech
        self.sample_rate = sample_rate
        self._vad: object | None = None
        self._pending = np.zeros(0, dtype=np.float32)
        self._consumed = 0
        self._segments: list[VADSegment] = []

    async def initialize(self) -> None:
        prepare_sherpa_runtime()
        import sherpa_onnx  # type: ignore[import-untyped]

        cfg = sherpa_onnx.VadModelConfig()
        cfg.silero_vad.model = str(self.model_path)
        cfg.silero_vad.threshold = self.threshold
        cfg.silero_vad.min_silence_duration = self.min_silence
        cfg.silero_vad.min_speech_duration = self.min_speech
        cfg.silero_vad.window_size = self.WINDOW
        cfg.sample_rate = self.sample_rate
        self._vad = sherpa_onnx.VoiceActivityDetector(cfg, buffer_size_in_seconds=30)
        self._pending = np.zeros(0, dtype=np.float32)
        self._consumed = 0
        self._segments.clear()
        self._initialized = True

    async def process(self, frame: np.ndarray) -> bool:
        if self._vad is None:
            raise RuntimeError("VAD is not initialized")
        data = np.asarray(frame, dtype=np.float32).reshape(-1)
        if data.size:
            self._pending = np.concatenate([self._pending, data])
        speech = False
        while self._pending.size >= self.WINDOW:
            block, self._pending = self._pending[: self.WINDOW], self._pending[self.WINDOW :]
            self._vad.accept_waveform(block)  # type: ignore[attr-defined]
            self._consumed += self.WINDOW
            speech = speech or bool(self._vad.is_speech_detected())  # type: ignore[attr-defined]
            self._drain()
        return speech

    async def flush(self) -> None:
        if self._vad is None:
            return
        self._vad.flush()  # type: ignore[attr-defined]
        self._drain()

    def _drain(self) -> None:
        if self._vad is None:
            return
        while not self._vad.empty():  # type: ignore[attr-defined]
            segment = self._vad.front  # type: ignore[attr-defined]
            samples = np.asarray(segment.samples, dtype=np.float32).copy()
            self._segments.append(VADSegment(samples=samples, start_sample=self._consumed))
            self._vad.pop()  # type: ignore[attr-defined]

    def take_segment(self) -> VADSegment | None:
        return self._segments.pop(0) if self._segments else None

    def segments(self) -> list[VADSegment]:
        return list(self._segments)

    async def reset(self) -> None:
        if self._vad is not None:
            self._vad.reset()  # type: ignore[attr-defined]
        self._pending = np.zeros(0, dtype=np.float32)
        self._segments.clear()
        self._consumed = 0

    async def shutdown(self) -> None:
        self._vad = None
        self._initialized = False
