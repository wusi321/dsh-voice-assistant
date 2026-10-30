"""Echo cancellation adapters.

`WebRTCAEC` uses livekit's WebRTC AudioProcessingModule (Apache-2.0). The
reference is the exact signal written to the speaker by PlaybackStream, not a
WASAPI loopback device.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

AEC_SAMPLE_RATE = 16_000
AEC_HOP = 160


class PassthroughAEC:
    """No-op fallback used when AEC is disabled or unavailable."""

    name = "passthrough"
    sample_rate = AEC_SAMPLE_RATE

    def process(self, microphone: np.ndarray, reference: np.ndarray) -> np.ndarray:
        del reference
        return microphone.astype(np.float32, copy=True)

    def reset(self) -> None:
        return None


class WebRTCAEC:
    """WebRTC APM with an injectable processing module for tests."""

    name = "webrtc-apm"
    sample_rate = AEC_SAMPLE_RATE
    hop = AEC_HOP

    def __init__(self, *, delay_ms: int = 40, apm: object | None = None) -> None:
        self._mic = np.zeros(0, dtype=np.float32)
        self._ref = np.zeros(0, dtype=np.float32)
        if apm is not None:
            self._apm = apm
            return
        from livekit import rtc

        self._rtc: Any = rtc
        self._apm = rtc.AudioProcessingModule(
            echo_cancellation=True,
            noise_suppression=True,
            high_pass_filter=True,
            auto_gain_control=False,
        )
        self._apm.set_stream_delay_ms(delay_ms)

    def _frame(self, samples: np.ndarray) -> Any:
        pcm = (np.clip(samples, -1, 1) * 32767).astype(np.int16)
        return self._rtc.AudioFrame(pcm.tobytes(), self.sample_rate, 1, self.hop)

    def process(self, microphone: np.ndarray, reference: np.ndarray) -> np.ndarray:
        self._ref = np.concatenate([self._ref, np.asarray(reference, dtype=np.float32)])
        while self._ref.size >= self.hop:
            frame, self._ref = self._ref[: self.hop], self._ref[self.hop :]
            self._apm.process_reverse_stream(self._frame(frame))  # type: ignore[attr-defined]

        self._mic = np.concatenate([self._mic, np.asarray(microphone, dtype=np.float32)])
        out: list[np.ndarray] = []
        while self._mic.size >= self.hop:
            frame, self._mic = self._mic[: self.hop], self._mic[self.hop :]
            audio_frame: Any = self._frame(frame)
            self._apm.process_stream(audio_frame)  # type: ignore[attr-defined]
            out.append(
                np.frombuffer(bytes(audio_frame.data), dtype=np.int16).astype(np.float32) / 32767.0
            )
        if not out:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(out)

    def reset(self) -> None:
        self._mic = np.zeros(0, dtype=np.float32)
        self._ref = np.zeros(0, dtype=np.float32)


def create_aec(enabled: bool, *, delay_ms: int = 40) -> PassthroughAEC | WebRTCAEC:
    if not enabled:
        return PassthroughAEC()
    try:
        return WebRTCAEC(delay_ms=delay_ms)
    except Exception as exc:
        logger.warning("WebRTC AEC unavailable, using passthrough: %s", exc)
        return PassthroughAEC()
