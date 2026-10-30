"""Single-authority playback scheduler and output stream."""

from __future__ import annotations

import logging
import threading
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from voice_runtime.audio.backend import AudioBackend, AudioBackendError, AudioStreamLike
from voice_runtime.audio.device_manager import DeviceSelection

logger = logging.getLogger(__name__)

PlaybackEvent = Callable[[str, str], None]
ReferenceCallback = Callable[[np.ndarray], None]
ErrorCallback = Callable[[str], None]


@dataclass
class AudioChunk:
    utterance_id: str
    samples: np.ndarray


class PlaybackScheduler:
    """The only place TTS samples are queued for the speaker."""

    def __init__(self, *, on_event: PlaybackEvent | None = None) -> None:
        self._queue: deque[AudioChunk] = deque()
        self._current: AudioChunk | None = None
        self._offset = 0
        self._lock = threading.Lock()
        self._on_event = on_event
        self._started: set[str] = set()

    @property
    def is_active(self) -> bool:
        with self._lock:
            return self._current is not None or bool(self._queue)

    def push(self, chunk: AudioChunk) -> None:
        if chunk.samples.size == 0:
            return
        with self._lock:
            self._queue.append(chunk)

    def cancel(self, utterance_id: str | None = None) -> int:
        with self._lock:
            removed = 0
            if utterance_id is None:
                removed = len(self._queue) + (1 if self._current else 0)
                idle = self._current.utterance_id if self._current else None
                self._queue.clear()
                self._current = None
                self._offset = 0
            else:
                idle = (
                    utterance_id
                    if self._current and self._current.utterance_id == utterance_id
                    else None
                )
                kept: deque[AudioChunk] = deque()
                while self._queue:
                    item = self._queue.popleft()
                    if item.utterance_id == utterance_id:
                        removed += 1
                    else:
                        kept.append(item)
                self._queue = kept
                if self._current and self._current.utterance_id == utterance_id:
                    self._current = None
                    self._offset = 0
                    removed += 1
        if idle:
            self._emit("interrupted", idle)
        return removed

    def take(self, frames: int) -> np.ndarray:
        out = np.zeros(frames, dtype=np.float32)
        if frames <= 0:
            return out
        started: str | None = None
        finished: str | None = None
        with self._lock:
            written = 0
            while written < frames:
                if self._current is None:
                    if not self._queue:
                        break
                    self._current = self._queue.popleft()
                    self._offset = 0
                    if self._current.utterance_id not in self._started:
                        self._started.add(self._current.utterance_id)
                        started = self._current.utterance_id
                chunk = self._current
                assert chunk is not None
                remaining = chunk.samples.size - self._offset
                count = min(frames - written, remaining)
                out[written : written + count] = chunk.samples[self._offset : self._offset + count]
                written += count
                self._offset += count
                if self._offset >= chunk.samples.size:
                    finished = chunk.utterance_id
                    self._current = None
                    self._offset = 0
                    self._started.discard(finished)
        if started:
            self._emit("started", started)
        if finished:
            self._emit("finished", finished)
        return out

    def _emit(self, event: str, utterance_id: str) -> None:
        if self._on_event is None:
            return
        try:
            self._on_event(event, utterance_id)
        except Exception:
            logger.exception("playback event consumer failed")


class PlaybackStream:
    """OutputStream that drains the scheduler and exposes the playback reference."""

    def __init__(
        self,
        backend: AudioBackend,
        selection: DeviceSelection,
        scheduler: PlaybackScheduler,
        *,
        block_ms: int = 10,
        on_reference: ReferenceCallback | None = None,
        on_error: ErrorCallback | None = None,
    ) -> None:
        self._backend = backend
        self._selection = selection
        self._scheduler = scheduler
        self._block_frames = max(1, int(selection.sample_rate * block_ms / 1000))
        self._on_reference = on_reference
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
            raise RuntimeError("playback stream is already started")
        try:
            stream = self._backend.open_output_stream(
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
            raise AudioBackendError(f"playback start failed: {exc}") from exc

    def stop(self) -> None:
        self._stopping = True
        if self._stream is None:
            return
        stream, self._stream = self._stream, None
        try:
            stream.stop()
        finally:
            stream.close()

    def _callback(self, outdata: np.ndarray, frames: int, time: object, status: object) -> None:
        del time
        if status:
            self._last_error = str(status)
            logger.warning("playback status: %s", status)
        samples = self._scheduler.take(frames)
        data = np.asarray(outdata)
        if data.ndim > 1:
            data[:, 0] = samples
            for channel in range(1, data.shape[1]):
                data[:, channel] = samples
        else:
            data[:] = samples
        if self._on_reference is not None:
            try:
                self._on_reference(samples.copy())
            except Exception:
                logger.exception("playback reference consumer failed")
        del frames

    def _finished(self) -> None:
        if self._stopping:
            self._stopping = False
            return
        message = "playback stream finished unexpectedly"
        self._last_error = message
        if self._on_error is not None:
            self._on_error(message)
        logger.warning(message)
