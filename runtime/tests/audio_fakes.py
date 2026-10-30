"""Deterministic fake PortAudio backend for unit tests."""

from __future__ import annotations

from typing import Any

import numpy as np


class FakeStream:
    def __init__(
        self,
        *,
        callback: Any,
        finished_callback: Any | None,
        frames: int,
        channels: int,
    ) -> None:
        self.callback = callback
        self.finished_callback = finished_callback
        self.frames = frames
        self.channels = channels
        self.started = False
        self.stopped = False
        self.closed = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True

    def close(self) -> None:
        self.closed = True

    def finish(self) -> None:
        if self.finished_callback is not None:
            self.finished_callback()


class FakeInputStream(FakeStream):
    def drive(self, samples: np.ndarray | None = None) -> None:
        frames = samples.size if samples is not None else self.frames
        data = (
            np.asarray(samples, dtype=np.float32).reshape(-1, 1)
            if samples is not None
            else np.zeros((frames, self.channels), dtype=np.float32)
        )
        self.callback(data, data.shape[0], None, None)


class FakeOutputStream(FakeStream):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.output = np.zeros(0, dtype=np.float32)

    def drive(self) -> None:
        outdata = np.zeros((self.frames, self.channels), dtype=np.float32)
        self.callback(outdata, self.frames, None, None)
        self.output = outdata[:, 0].copy()


class FakeBackend:
    """In-memory backend with the same surface as SoundDeviceBackend."""

    def __init__(self, devices: list[dict[str, Any]] | None = None) -> None:
        self.devices = devices or [
            {
                "name": "Fake Mic",
                "hostapi": 0,
                "max_input_channels": 1,
                "max_output_channels": 0,
                "default_samplerate": 48_000.0,
            },
            {
                "name": "Fake Speaker",
                "hostapi": 0,
                "max_input_channels": 0,
                "max_output_channels": 1,
                "default_samplerate": 48_000.0,
            },
        ]
        self.default_input = 0
        self.default_output = 1
        self.input_streams: list[FakeInputStream] = []
        self.output_streams: list[FakeOutputStream] = []
        self.fail_input = False
        self.fail_output = False

    def query_devices(self) -> list[dict[str, Any]]:
        return self.devices

    def default_devices(self) -> tuple[int | None, int | None]:
        return self.default_input, self.default_output

    def open_input_stream(
        self,
        *,
        device: int,
        samplerate: int,
        channels: int,
        blocksize: int,
        callback: Any,
        finished_callback: Any | None = None,
    ) -> FakeInputStream:
        _ = samplerate
        if self.fail_input:
            raise OSError("fake input failure")
        stream = FakeInputStream(
            callback=callback,
            finished_callback=finished_callback,
            frames=blocksize,
            channels=channels,
        )
        self.input_streams.append(stream)
        return stream

    def open_output_stream(
        self,
        *,
        device: int,
        samplerate: int,
        channels: int,
        blocksize: int,
        callback: Any,
        finished_callback: Any | None = None,
    ) -> FakeOutputStream:
        _ = samplerate
        if self.fail_output:
            raise OSError("fake output failure")
        stream = FakeOutputStream(
            callback=callback,
            finished_callback=finished_callback,
            frames=blocksize,
            channels=channels,
        )
        self.output_streams.append(stream)
        return stream
