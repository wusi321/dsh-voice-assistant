"""Sample-rate conversion.

`resample_poly` is used for offline blocks and tests. `StreamingResampler` uses
linear interpolation with fractional-phase continuity so arbitrary device rates
can feed the fixed 16 kHz ASR/KWS pipeline without assuming hardware support.
"""

from __future__ import annotations

import numpy as np
from scipy.signal import resample_poly  # type: ignore[import-untyped]


def resample_audio(samples: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    """Resample one block with a polyphase FIR, preserving float32 and shape."""
    if source_rate <= 0 or target_rate <= 0:
        raise ValueError("sample rates must be positive")
    data = np.asarray(samples, dtype=np.float32)
    if data.size == 0 or source_rate == target_rate:
        return data.copy()
    from math import gcd

    factor = gcd(source_rate, target_rate)
    up = target_rate // factor
    down = source_rate // factor
    out = resample_poly(data, up, down, axis=0)
    return np.asarray(out, dtype=np.float32)


class StreamingResampler:
    """Streaming linear resampler with phase continuity across blocks."""

    def __init__(self, source_rate: int, target_rate: int) -> None:
        if source_rate <= 0 or target_rate <= 0:
            raise ValueError("sample rates must be positive")
        self.source_rate = source_rate
        self.target_rate = target_rate
        self._step = source_rate / target_rate
        self._tail = np.zeros((0,), dtype=np.float32)
        self._position = 0.0

    def reset(self) -> None:
        self._tail = np.zeros((0,), dtype=np.float32)
        self._position = 0.0

    def process(self, samples: np.ndarray) -> np.ndarray:
        """Consume a 1-D block and return the resampled 1-D block."""
        data = np.asarray(samples, dtype=np.float32).reshape(-1)
        if data.size == 0:
            return np.zeros(0, dtype=np.float32)
        if self.source_rate == self.target_rate:
            return data.copy()

        buf = np.concatenate([self._tail, data])
        if buf.size < 2:
            self._tail = buf
            return np.zeros(0, dtype=np.float32)

        out: list[float] = []
        position = self._position
        while position + 1.0 < buf.size:
            index = int(position)
            fraction = position - index
            left = float(buf[index])
            right = float(buf[index + 1])
            out.append(left + (right - left) * fraction)
            position += self._step

        consumed = int(position)
        self._tail = buf[consumed:].copy()
        self._position = position - consumed
        return np.asarray(out, dtype=np.float32)
