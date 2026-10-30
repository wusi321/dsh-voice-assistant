"""Fixed-capacity mono/stereo audio ring buffer."""

from __future__ import annotations

import threading

import numpy as np


class AudioRingBuffer:
    """A bounded, overwrite-oldest ring buffer.

    The buffer owns its samples; callers must copy before handing them to another
    thread. The lock exists because capture callbacks and the pipeline normally
    run on different threads.
    """

    def __init__(self, capacity_samples: int) -> None:
        if capacity_samples <= 0:
            raise ValueError("capacity_samples must be positive")
        self._capacity = int(capacity_samples)
        self._buffer = np.zeros(self._capacity, dtype=np.float32)
        self._write = 0
        self._size = 0
        self._lock = threading.Lock()

    @property
    def capacity(self) -> int:
        return self._capacity

    @property
    def available(self) -> int:
        with self._lock:
            return self._size

    def clear(self) -> None:
        with self._lock:
            self._buffer.fill(0.0)
            self._write = 0
            self._size = 0

    def write(self, samples: np.ndarray) -> int:
        """Append samples, keeping the newest `capacity` values. Returns written count."""
        data = np.asarray(samples, dtype=np.float32).reshape(-1)
        if data.size == 0:
            return 0
        if data.size > self._capacity:
            data = data[-self._capacity :]
        with self._lock:
            count = data.size
            first = min(count, self._capacity - self._write)
            self._buffer[self._write : self._write + first] = data[:first]
            remaining = count - first
            if remaining:
                self._buffer[:remaining] = data[first:]
            self._write = (self._write + count) % self._capacity
            self._size = min(self._capacity, self._size + count)
        return count

    def read(self, count: int) -> np.ndarray:
        """Read up to `count` oldest samples; returns fewer when empty."""
        if count <= 0:
            return np.zeros(0, dtype=np.float32)
        with self._lock:
            count = min(count, self._size)
            if count == 0:
                return np.zeros(0, dtype=np.float32)
            start = (self._write - self._size) % self._capacity
            first = min(count, self._capacity - start)
            out = np.empty(count, dtype=np.float32)
            out[:first] = self._buffer[start : start + first]
            if count > first:
                out[first:] = self._buffer[: count - first]
            self._size -= count
            return out

    def snapshot(self, count: int | None = None) -> np.ndarray:
        """Return the newest `count` samples without consuming them."""
        with self._lock:
            size = self._size if count is None else min(count, self._size)
            if size == 0:
                return np.zeros(0, dtype=np.float32)
            start = (self._write - size) % self._capacity
            first = min(size, self._capacity - start)
            out = np.empty(size, dtype=np.float32)
            out[:first] = self._buffer[start : start + first]
            if size > first:
                out[first:] = self._buffer[: size - first]
            return out
