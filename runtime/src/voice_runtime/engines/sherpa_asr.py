"""sherpa-onnx streaming Zipformer ASR adapter."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from voice_runtime.engines.base import ASREngine
from voice_runtime.engines.models import prepare_sherpa_runtime


class SherpaASR(ASREngine):
    """Streaming Chinese Zipformer with partial and final results."""

    def __init__(
        self,
        model_dir: Path,
        *,
        sample_rate: int = 16_000,
        num_threads: int = 2,
    ) -> None:
        super().__init__("sherpa-streaming-asr")
        self.model_dir = model_dir
        self.sample_rate = sample_rate
        self.num_threads = num_threads
        self._recognizer: object | None = None
        self._stream: object | None = None
        self._partial = ""
        self._final = ""

    async def initialize(self) -> None:
        prepare_sherpa_runtime()
        import sherpa_onnx  # type: ignore[import-untyped]

        d = self.model_dir
        self._recognizer = sherpa_onnx.OnlineRecognizer.from_transducer(
            tokens=str(d / "tokens.txt"),
            encoder=str(d / "encoder-epoch-99-avg-1.int8.onnx"),
            decoder=str(d / "decoder-epoch-99-avg-1.int8.onnx"),
            joiner=str(d / "joiner-epoch-99-avg-1.int8.onnx"),
            num_threads=self.num_threads,
            sample_rate=self.sample_rate,
            feature_dim=80,
            decoding_method="greedy_search",
        )
        await self.start_stream()
        self._initialized = True

    async def start_stream(self) -> None:
        if self._recognizer is None:
            raise RuntimeError("ASR is not initialized")
        self._stream = self._recognizer.create_stream()  # type: ignore[attr-defined]
        self._partial = ""
        self._final = ""

    async def accept_audio(self, samples: np.ndarray) -> None:
        if self._stream is None or self._recognizer is None:
            raise RuntimeError("ASR stream is not started")
        data = np.asarray(samples, dtype=np.float32).reshape(-1)
        if data.size:
            self._stream.accept_waveform(self.sample_rate, data)  # type: ignore[attr-defined]
        self._decode()

    def _decode(self) -> None:
        if self._recognizer is None or self._stream is None:
            return
        while self._recognizer.is_ready(self._stream):  # type: ignore[attr-defined]
            self._recognizer.decode_stream(self._stream)  # type: ignore[attr-defined]
        result = self._recognizer.get_result(self._stream)  # type: ignore[attr-defined]
        self._partial = str(result)

    async def get_partial_result(self) -> str:
        return self._partial

    async def get_final_result(self) -> str:
        if self._stream is None or self._recognizer is None:
            return self._final
        self._stream.accept_waveform(  # type: ignore[attr-defined]
            self.sample_rate, np.zeros(int(self.sample_rate * 0.6), dtype=np.float32)
        )
        self._stream.input_finished()  # type: ignore[attr-defined]
        self._decode()
        self._final = self._partial
        return self._final

    async def reset(self) -> None:
        await self.start_stream()

    async def shutdown(self) -> None:
        self._recognizer = None
        self._stream = None
        self._initialized = False
