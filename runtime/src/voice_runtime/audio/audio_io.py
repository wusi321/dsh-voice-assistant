"""Audio I/O composition: capture, playback, resampling, AEC, device switching."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

import numpy as np

from voice_runtime.audio.aec import AEC_SAMPLE_RATE, PassthroughAEC, WebRTCAEC, create_aec
from voice_runtime.audio.audio_buffer import AudioRingBuffer
from voice_runtime.audio.backend import AudioBackend, AudioBackendError, SoundDeviceBackend
from voice_runtime.audio.capture import CaptureStream
from voice_runtime.audio.device_manager import DeviceError, DeviceManager, DeviceSelection
from voice_runtime.audio.playback import AudioChunk, PlaybackScheduler, PlaybackStream
from voice_runtime.audio.resampler import StreamingResampler, resample_audio

logger = logging.getLogger(__name__)

INTERNAL_RATE = AEC_SAMPLE_RATE


class AudioIO:
    """One capture stream + one playback stream with a shared AEC reference."""

    def __init__(
        self,
        *,
        backend: AudioBackend | None = None,
        input_device: str | int | None = None,
        output_device: str | int | None = None,
        preferred_input_rate: int | None = None,
        preferred_output_rate: int | None = None,
        block_ms: int = 10,
        aec_enabled: bool = True,
        echo_delay_ms: int = 40,
        on_capture: Callable[[np.ndarray], None] | None = None,
        on_playback_event: Callable[[str, str], None] | None = None,
        on_error: Callable[[str], None] | None = None,
    ) -> None:
        self._backend = backend
        self._input_selector = input_device
        self._output_selector = output_device
        self._preferred_input_rate = preferred_input_rate
        self._preferred_output_rate = preferred_output_rate
        self._block_ms = block_ms
        self._aec_enabled = aec_enabled
        self._echo_delay_ms = echo_delay_ms
        self._on_capture = on_capture
        self._on_playback_event = on_playback_event
        self._on_error = on_error

        self._manager: DeviceManager | None = None
        self._capture: CaptureStream | None = None
        self._playback: PlaybackStream | None = None
        self._scheduler: PlaybackScheduler | None = None
        self._aec: PassthroughAEC | WebRTCAEC | None = None
        self._capture_resampler: StreamingResampler | None = None
        self._reference_resampler: StreamingResampler | None = None
        self._reference = AudioRingBuffer(INTERNAL_RATE * 2)
        self._clean = AudioRingBuffer(INTERNAL_RATE * 5)
        self._lock = threading.Lock()
        self._input_selection: DeviceSelection | None = None
        self._output_selection: DeviceSelection | None = None
        self._last_error: str | None = None

    @property
    def running(self) -> bool:
        return self._capture is not None and self._playback is not None

    @property
    def input_selection(self) -> DeviceSelection | None:
        return self._input_selection

    @property
    def output_selection(self) -> DeviceSelection | None:
        return self._output_selection

    @property
    def last_error(self) -> str | None:
        return self._last_error

    @property
    def scheduler(self) -> PlaybackScheduler:
        if self._scheduler is None:
            raise RuntimeError("audio I/O is not started")
        return self._scheduler

    def start(self) -> None:
        if self.running:
            return
        backend = self._backend or SoundDeviceBackend()
        self._backend = backend
        self._manager = DeviceManager(backend)
        self._manager.refresh()
        input_selection = self._manager.resolve(
            self._input_selector,
            "input",
            channels=1,
            preferred_rate=self._preferred_input_rate,
        )
        output_selection = self._manager.resolve(
            self._output_selector,
            "output",
            channels=1,
            preferred_rate=self._preferred_output_rate,
        )
        self._input_selection = input_selection
        self._output_selection = output_selection
        self._aec = create_aec(self._aec_enabled, delay_ms=self._echo_delay_ms)
        self._capture_resampler = StreamingResampler(input_selection.sample_rate, INTERNAL_RATE)
        self._reference_resampler = StreamingResampler(output_selection.sample_rate, INTERNAL_RATE)
        self._scheduler = PlaybackScheduler(on_event=self._on_playback_event)
        self._reference.clear()
        self._clean.clear()

        self._playback = PlaybackStream(
            backend,
            output_selection,
            self._scheduler,
            block_ms=self._block_ms,
            on_reference=self._on_reference,
            on_error=self._stream_error,
        )
        self._capture = CaptureStream(
            backend,
            input_selection,
            block_ms=self._block_ms,
            on_audio=self._on_microphone,
            on_error=self._stream_error,
        )
        try:
            self._playback.start()
            self._capture.start()
        except AudioBackendError as exc:
            self._last_error = str(exc)
            self.stop()
            self._notify_error(str(exc))
            raise

    def stop(self) -> None:
        capture, self._capture = self._capture, None
        playback, self._playback = self._playback, None
        if capture is not None:
            try:
                capture.stop()
            except Exception:
                logger.exception("capture stop failed")
        if playback is not None:
            try:
                playback.stop()
            except Exception:
                logger.exception("playback stop failed")
        if self._scheduler is not None:
            self._scheduler.cancel()

    def restart(self, *, retries: int = 3, delay: float = 1.0) -> bool:
        """Stop and reopen the current devices; used after a device error."""
        last_error: Exception | None = None
        for attempt in range(retries):
            try:
                self.stop()
                self.start()
                return True
            except (AudioBackendError, DeviceError) as exc:
                last_error = exc
                if attempt + 1 < retries:
                    time.sleep(delay)
        self._last_error = str(last_error) if last_error else "restart failed"
        return False

    def switch_devices(
        self,
        *,
        input_device: str | int | None = None,
        output_device: str | int | None = None,
    ) -> None:
        """Switch devices by stopping, updating selectors, and reopening."""
        was_running = self.running
        self.stop()
        self._input_selector = input_device
        self._output_selector = output_device
        if was_running:
            self.start()

    def play(
        self,
        samples: np.ndarray,
        *,
        utterance_id: str,
        sample_rate: int,
    ) -> None:
        if self._scheduler is None or self._output_selection is None:
            raise RuntimeError("audio I/O is not started")
        audio = np.asarray(samples, dtype=np.float32).reshape(-1)
        if audio.size == 0:
            return
        if sample_rate != self._output_selection.sample_rate:
            audio = resample_audio(audio, sample_rate, self._output_selection.sample_rate)
        self._scheduler.push(AudioChunk(utterance_id=utterance_id, samples=audio))

    def cancel_playback(self, utterance_id: str | None = None) -> int:
        return self._scheduler.cancel(utterance_id) if self._scheduler else 0

    def read_clean(self, count: int) -> np.ndarray:
        return self._clean.read(count)

    def _on_microphone(self, samples: np.ndarray) -> None:
        if self._capture_resampler is None or self._aec is None:
            return
        resampled = self._capture_resampler.process(samples)
        if resampled.size == 0:
            return
        reference = self._reference.read(resampled.size)
        if reference.size < resampled.size:
            reference = np.pad(reference, (0, resampled.size - reference.size))
        clean = self._aec.process(resampled, reference)
        if clean.size:
            self._clean.write(clean)
            if self._on_capture is not None:
                try:
                    self._on_capture(clean.copy())
                except Exception:
                    logger.exception("capture consumer failed")

    def _on_reference(self, samples: np.ndarray) -> None:
        if self._reference_resampler is None:
            return
        resampled = self._reference_resampler.process(samples)
        if resampled.size:
            self._reference.write(resampled)

    def _stream_error(self, message: str) -> None:
        self._last_error = message
        self._notify_error(message)

    def _notify_error(self, message: str) -> None:
        logger.warning("audio stream error: %s", message)
        if self._on_error is not None:
            self._on_error(message)
