"""Runtime-side handling of TTS commands from the DSH plugin."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Protocol

import numpy as np

from voice_runtime.audio.audio_io import AudioIO
from voice_runtime.engines.base import TTSEngine
from voice_runtime.transport.protocol import VoiceEvent

logger = logging.getLogger(__name__)

Emitter = Callable[[str, dict[str, object]], Awaitable[None]]


class AudioSink(Protocol):
    def play(self, samples: np.ndarray, *, utterance_id: str, sample_rate: int) -> None: ...

    def cancel_playback(self, utterance_id: str | None = None) -> int: ...


class NullAudio:
    """No-device sink used by `--voice fake` and unit tests."""

    def play(self, samples: np.ndarray, *, utterance_id: str, sample_rate: int) -> None:
        _ = (samples, utterance_id, sample_rate)

    def cancel_playback(self, utterance_id: str | None = None) -> int:
        _ = utterance_id
        return 0


class RuntimeVoiceService:
    """Owns TTS synthesis and the single playback authority for plugin commands."""

    def __init__(
        self,
        *,
        tts: TTSEngine | None,
        audio: AudioSink | None,
        session_id: str = "runtime",
    ) -> None:
        self._tts = tts
        self._audio = audio or NullAudio()
        self._session_id = session_id
        self._emit: Emitter | None = None
        self._active: str | None = None
        self._cancelled = False
        self._task: asyncio.Task[None] | None = None
        self._started = False

    @property
    def tts_available(self) -> bool:
        return self._tts is not None

    def set_emitter(self, emitter: Emitter) -> None:
        self._emit = emitter

    async def start(self) -> None:
        if isinstance(self._audio, AudioIO):
            self._audio.start()
        if self._tts is not None:
            await self._tts.initialize()
        self._started = True

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None
        if isinstance(self._audio, AudioIO):
            self._audio.stop()
        if self._tts is not None:
            await self._tts.shutdown()
        self._started = False

    async def handle_event(self, event: VoiceEvent) -> None:
        if event.type == "tts.speak":
            await self._speak(event.payload)
        elif event.type == "tts.cancel":
            await self.cancel(str(event.payload.get("reason", "user_stop")))
        elif event.type == "runtime.shutdown":
            await self.cancel("cancel")

    async def _speak(self, payload: dict[str, object]) -> None:
        if self._tts is None:
            await self._send_error("engine_unavailable", "TTS engine is not configured")
            return

        text = str(payload.get("text", "")).strip()
        utterance_id = str(payload.get("utteranceId", "")).strip()
        if not text or not utterance_id:
            await self._send_error("invalid_message", "tts.speak needs utteranceId and text")
            return
        if self._active is not None:
            await self.cancel("cancel")

        self._active = utterance_id
        self._cancelled = False
        await self._emit_event(
            "tts.started",
            {
                "utteranceId": utterance_id,
                "text": text,
                "sampleRate": int(self._tts.sample_rate),
                "channels": 1,
            },
        )

        chunks: list[np.ndarray] = []
        try:
            async for chunk in self._tts.synthesize_stream(text):
                if self._cancelled:
                    break
                data = np.asarray(chunk, dtype=np.float32).reshape(-1)
                if data.size:
                    chunks.append(data.copy())
        except Exception as exc:
            logger.exception("TTS synthesis failed")
            self._active = None
            await self._send_error("engine_unavailable", f"TTS synthesis failed: {exc}")
            return

        if self._cancelled or not chunks:
            self._active = None
            await self._emit_event(
                "tts.interrupted",
                {"utteranceId": utterance_id, "reason": "cancel"},
            )
            return

        audio = np.concatenate(chunks)
        self._audio.play(
            audio,
            utterance_id=utterance_id,
            sample_rate=int(self._tts.sample_rate),
        )
        if isinstance(self._audio, AudioIO):
            await self._wait_for_playback()
        if self._active != utterance_id:
            return
        self._active = None
        await self._emit_event("tts.finished", {"utteranceId": utterance_id})

    async def _wait_for_playback(self, timeout: float = 120.0) -> None:
        if not isinstance(self._audio, AudioIO):
            return
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while self._active is not None and self._audio.scheduler.is_active:
            if loop.time() >= deadline:
                return
            await asyncio.sleep(0.02)
        # Give the output callback one block to drain the final samples.
        await asyncio.sleep(0.05)

    async def cancel(self, reason: str = "user_stop") -> None:
        self._cancelled = True
        utterance_id = self._active
        if utterance_id is not None:
            self._audio.cancel_playback(utterance_id)
            self._active = None
            await self._emit_event(
                "tts.interrupted",
                {"utteranceId": utterance_id, "reason": reason},
            )
        if self._tts is not None:
            await self._tts.cancel()

    async def _emit_event(self, event_type: str, payload: dict[str, object]) -> None:
        if self._emit is None:
            return
        try:
            await self._emit(event_type, payload)
        except Exception:
            logger.exception("TTS event emitter failed")

    async def _send_error(self, code: str, message: str) -> None:
        await self._emit_event(
            "runtime.error",
            {"code": code, "message": message, "fatal": False},
        )
