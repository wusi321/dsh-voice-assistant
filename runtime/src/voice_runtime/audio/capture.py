"""Microphone capture stream with a bounded buffer."""

from __future__ import annotations

import logging
from collections.abc import Callable

import numpy as np

from voice_runtime.audio.audio_buffer import AudioRingBuffer
from voice_runtime.audio.backend import AudioBackend, AudioBackendError, AudioStreamLike
from voice_runtime.audio.device_manager import DeviceSelection

logger = logging.getLogger(__name__)

AudioCallback = Callable[[np.ndarray], None]
ErrorCallback = Callable[[str], None]


class CaptureStream:
    """One InputStream; samples are copied into a ring buffer in the callback."""

    def __init__(
        self,
        backend: AudioBackend,
        selection: DeviceSelection,
        *,
        block_ms: int = 10,
        buffer_seconds: float = 5.0,
        on_audio: AudioCallback | None = None,
        on_error: ErrorCallback | None = None,
    ) -> None:
        self._backend = backend
        self._selection = selection
        self._block_frames = max(1, int(selection.sample_rate * block_ms / 1000))
        self._buffer = AudioRingBuffer(int(selection.sample_rate * buffer_seconds))
        self._on_audio = on_audio
        self._on_error = on_error
        self._stream: AudioStreamLike | None = None
        self._last_error: str | None = None
        self._stopping = False

    @property
    def selection(self) -> DeviceSelection:
        return self._selection

    @property
    def block_frames(self) -> int:
        return self._block_frames

    @property
    def last_error(self) -> str | None:
        return self._last_error

    @property
    def active(self) -> bool:
        return self._stream is not None

    def start(self) -> None:
        if self._stream is not None:
            raise RuntimeError("capture stream is already started")
        try:
            stream = self._backend.open_input_stream(
                device=self._selection.device.index,
                samplerate=self._selection.sample_rate,
                channels=self._selection.channels,
                blocksize=self._block_frames,
                callback=self._callback,
                finished_callback=self._finished,
            )
            stream.start()
            self._stream = stream
        except Exception as exc:
            raise AudioBackendError(f"capture start failed: {exc}") from exc

    def stop(self) -> None:
        self._stopping = True
        if self._stream is None:
            return
        stream, self._stream = self._stream, None
        try:
            stream.stop()
        finally:
            stream.close()

    def read(self, count: int) -> np.ndarray:
        return self._buffer.read(count)

    def snapshot(self, count: int | None = None) -> np.ndarray:
        return self._buffer.snapshot(count)

    def _callback(self, indata: np.ndarray, frames: int, time: object, status: object) -> None:
        del time
        if status:
            self._last_error = str(status)
            logger.warning("capture status: %s", status)
        data = np.asarray(indata, dtype=np.float32)
        mono = data[:, 0] if data.ndim > 1 else data
        self._buffer.write(mono)
        if self._on_audio is not None:
            try:
                self._on_audio(mono.copy())
            except Exception:
                logger.exception("capture consumer failed")
        del frames

    def _finished(self) -> None:
        if self._stopping:
            self._stopping = False
            return
        message = "capture stream finished unexpectedly"
        self._last_error = message
        if self._on_error is not None:
            self._on_error(message)
        logger.warning(message)
