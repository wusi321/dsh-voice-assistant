"""sherpa-onnx TTS adapter (Kokoro or VITS/Piper)."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import numpy as np

from voice_runtime.engines.base import TTSEngine
from voice_runtime.engines.models import prepare_sherpa_runtime


class SherpaTTS(TTSEngine):
    """Sentence-level local TTS with chunked streaming and cancellation."""

    def __init__(
        self,
        model_dir: Path,
        *,
        kind: str = "vits",
        speaker_id: int = 0,
        speed: float = 1.0,
        chunk_ms: int = 200,
    ) -> None:
        super().__init__(f"sherpa-{kind}-tts")
        self.model_dir = model_dir
        self.tts_kind = kind
        self.speaker_id = speaker_id
        self.speed = speed
        self.chunk_ms = chunk_ms
        self.sample_rate = 0
        self._tts: Any | None = None
        self._cancelled = False

    async def initialize(self) -> None:
        prepare_sherpa_runtime()
        import sherpa_onnx  # type: ignore[import-untyped]

        d = self.model_dir
        if self.tts_kind == "kokoro":
            model = self._first(d, "model.onnx")
            voices = self._first(d, "voices.bin")
            tokens = self._first(d, "tokens.txt")
            data_dir = d / "espeak-ng-data"
            lexicon = ",".join(
                str(path)
                for path in (d / "lexicon-us-en.txt", d / "lexicon-zh.txt")
                if path.exists()
            )
            kokoro = sherpa_onnx.OfflineTtsKokoroModelConfig(
                model=str(model),
                voices=str(voices),
                tokens=str(tokens),
                data_dir=str(data_dir),
                lexicon=lexicon,
                lang="zh",
            )
            model_config = sherpa_onnx.OfflineTtsModelConfig(kokoro=kokoro, num_threads=2)
            rule_fsts = ",".join(
                str(path)
                for path in (d / "date-zh.fst", d / "phone-zh.fst", d / "number-zh.fst")
                if path.exists()
            )
        else:
            model = self._first(d, "*.onnx")
            tokens = self._first(d, "tokens.txt")
            data_dir = d / "espeak-ng-data"
            lexicon_path = d / "lexicon.txt"
            if data_dir.is_dir():
                os.environ.setdefault("ESPEAK_DATA_PATH", str(data_dir))
            vits = sherpa_onnx.OfflineTtsVitsModelConfig(
                model=str(model),
                tokens=str(tokens),
                data_dir=str(data_dir) if data_dir.is_dir() else "",
                dict_dir=str(d) if (d / "dict").is_dir() else "",
                lexicon=str(lexicon_path) if lexicon_path.is_file() else "",
            )
            model_config = sherpa_onnx.OfflineTtsModelConfig(vits=vits, num_threads=2)
            rule_fsts = ",".join(
                str(path)
                for path in (d / "date.fst", d / "phone.fst", d / "number.fst")
                if path.exists()
            )

        cfg = sherpa_onnx.OfflineTtsConfig(model=model_config, rule_fsts=rule_fsts)
        self._tts = sherpa_onnx.OfflineTts(cfg)
        self.sample_rate = int(self._tts.sample_rate)
        self._initialized = True

    @staticmethod
    def _first(directory: Path, pattern: str) -> Path:
        matches = sorted(directory.glob(pattern))
        if not matches:
            raise FileNotFoundError(f"{pattern} not found in {directory}")
        return matches[0]

    async def synthesize_stream(self, text: str) -> AsyncIterator[np.ndarray]:
        if self._tts is None:
            raise RuntimeError("TTS is not initialized")
        self._cancelled = False
        audio = await asyncio.to_thread(self._generate, text)
        chunk = max(1, int(self.sample_rate * self.chunk_ms / 1000))
        for start in range(0, audio.size, chunk):
            if self._cancelled:
                return
            yield audio[start : start + chunk]
            await asyncio.sleep(0)

    def _generate(self, text: str) -> np.ndarray:
        assert self._tts is not None
        result = self._tts.generate(text, sid=self.speaker_id, speed=self.speed)
        return np.asarray(result.samples, dtype=np.float32)

    async def cancel(self) -> None:
        self._cancelled = True

    async def shutdown(self) -> None:
        self._tts = None
        self._cancelled = True
        self._initialized = False
