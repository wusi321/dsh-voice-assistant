"""sherpa-onnx keyword spotting adapter for Chinese wake words."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from voice_runtime.engines.base import WakeEngine
from voice_runtime.engines.models import prepare_sherpa_runtime


class SherpaKWS(WakeEngine):
    """KeywordSpotter with the WenetSpeech 3.3M model."""

    def __init__(
        self,
        model_dir: Path,
        *,
        keywords_file: Path | None = None,
        threshold: float = 0.25,
        score: float = 1.5,
        sample_rate: int = 16_000,
    ) -> None:
        super().__init__("sherpa-kws")
        self.model_dir = model_dir
        self.keywords_file = keywords_file or model_dir / "keywords.txt"
        self.threshold = threshold
        self.score = score
        self.sample_rate = sample_rate
        self._spotter: Any | None = None
        self._stream: Any | None = None
        self._last_score = 0.0

    @property
    def score_value(self) -> float:
        return self._last_score

    async def initialize(self) -> None:
        prepare_sherpa_runtime()
        import sherpa_onnx  # type: ignore[import-untyped]

        d = self.model_dir
        self._spotter = sherpa_onnx.KeywordSpotter(
            tokens=str(d / "tokens.txt"),
            encoder=str(d / "encoder-epoch-12-avg-2-chunk-16-left-64.int8.onnx"),
            decoder=str(d / "decoder-epoch-12-avg-2-chunk-16-left-64.int8.onnx"),
            joiner=str(d / "joiner-epoch-12-avg-2-chunk-16-left-64.int8.onnx"),
            keywords_file=str(self.keywords_file),
            num_threads=2,
            keywords_score=self.score,
            keywords_threshold=self.threshold,
            num_trailing_blanks=1,
            provider="cpu",
        )
        self._stream = self._spotter.create_stream()
        self._initialized = True

    async def detect(self, frame: np.ndarray) -> str | None:
        if self._spotter is None or self._stream is None:
            raise RuntimeError("KWS is not initialized")
        data = np.asarray(frame, dtype=np.float32).reshape(-1)
        if data.size:
            self._stream.accept_waveform(self.sample_rate, data)
        hit: str | None = None
        while self._spotter.is_ready(self._stream):
            self._spotter.decode_stream(self._stream)
            result = self._spotter.get_result(self._stream)
            if result:
                hit = str(result)
                self._spotter.reset_stream(self._stream)
        return hit

    async def reset(self) -> None:
        if self._spotter is not None and self._stream is not None:
            self._spotter.reset_stream(self._stream)

    async def shutdown(self) -> None:
        self._spotter = None
        self._stream = None
        self._initialized = False
