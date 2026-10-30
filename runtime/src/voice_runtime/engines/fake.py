"""Deterministic fake engines for tests and `--fake-audio`."""

from __future__ import annotations

from typing import AsyncIterator

import numpy as np

from .base import AECProcessor, ASREngine, TTSEngine, VADEngine, WakeEngine

FAKE_SAMPLE_RATE = 16_000


class FakeWakeEngine(WakeEngine):
    def __init__(self) -> None:
        super().__init__("fake-wake")
        self._next_keyword: str | None = None

    def fire(self, keyword: str = "hey assistant") -> None:
        self._next_keyword = keyword

    async def detect(self, frame: np.ndarray) -> str | None:
        _ = frame
        keyword, self._next_keyword = self._next_keyword, None
        return keyword


class FakeVADEngine(VADEngine):
    def __init__(self, threshold: float = 0.01) -> None:
        super().__init__("fake-vad")
        self.threshold = threshold
        self.speaking = False

    async def process(self, frame: np.ndarray) -> bool:
        rms = float(np.sqrt(np.mean(np.square(frame, dtype=np.float64))))
        self.speaking = rms >= self.threshold
        return self.speaking


class FakeASREngine(ASREngine):
    def __init__(self) -> None:
        super().__init__("fake-asr")
        self._text = ""
        self._partial = ""

    def feed_text(self, text: str, *, final: bool = False) -> None:
        if final:
            self._text = text
            self._partial = ""
        else:
            self._partial = text

    async def start_stream(self) -> None:
        self._text = ""
        self._partial = ""

    async def accept_audio(self, samples: np.ndarray) -> None:
        _ = samples

    async def get_partial_result(self) -> str:
        return self._partial

    async def get_final_result(self) -> str:
        return self._text


class FakeTTSEngine(TTSEngine):
    def __init__(self, sample_rate: int = 24_000) -> None:
        super().__init__("fake-tts")
        self.sample_rate = sample_rate
        self.cancelled = False

    async def synthesize_stream(self, text: str) -> AsyncIterator[np.ndarray]:
        self.cancelled = False
        for _ in range(max(1, min(8, len(text)))):
            if self.cancelled:
                return
            yield np.zeros(240, dtype=np.float32)

    async def cancel(self) -> None:
        self.cancelled = True


class FakeAECProcessor(AECProcessor):
    def __init__(self) -> None:
        super().__init__("fake-aec")

    async def process(self, microphone: np.ndarray, reference: np.ndarray) -> np.ndarray:
        _ = reference
        return microphone.astype(np.float32, copy=True)
