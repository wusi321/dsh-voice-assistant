"""Audio backend abstraction over PortAudio/sounddevice.

The backend is injectable so unit tests never open a real device. Every call
into sounddevice happens through this interface.
"""

from __future__ import annotations

from typing import Any, Protocol, cast


class AudioBackendError(RuntimeError):
    """The backend failed to enumerate or open a device."""


class AudioStreamLike(Protocol):
    def start(self) -> None: ...

    def stop(self) -> None: ...

    def close(self) -> None: ...


class AudioBackend(Protocol):
    """Minimal PortAudio surface used by the runtime."""

    def query_devices(self) -> list[dict[str, Any]]: ...

    def default_devices(self) -> tuple[int | None, int | None]: ...

    def open_input_stream(
        self,
        *,
        device: int,
        samplerate: int,
        channels: int,
        blocksize: int,
        callback: Any,
        finished_callback: Any | None = None,
    ) -> AudioStreamLike: ...

    def open_output_stream(
        self,
        *,
        device: int,
        samplerate: int,
        channels: int,
        blocksize: int,
        callback: Any,
        finished_callback: Any | None = None,
    ) -> AudioStreamLike: ...


class SoundDeviceBackend:
    """Lazy sounddevice backend; importing this class does not require PortAudio."""

    def __init__(self) -> None:
        try:
            import sounddevice as sd  # type: ignore[import-untyped]
        except Exception as exc:
            raise AudioBackendError(
                f"sounddevice/PortAudio is unavailable: {type(exc).__name__}: {exc}"
            ) from exc
        self._sd = sd

    def query_devices(self) -> list[dict[str, Any]]:
        try:
            return [dict(item) for item in self._sd.query_devices()]
        except Exception as exc:
            raise AudioBackendError(f"query_devices failed: {exc}") from exc

    def default_devices(self) -> tuple[int | None, int | None]:
        try:
            input_device, output_device = self._sd.default.device
        except (TypeError, ValueError):
            return None, None
        return (
            int(input_device) if input_device is not None and int(input_device) >= 0 else None,
            int(output_device) if output_device is not None and int(output_device) >= 0 else None,
        )

    def open_input_stream(
        self,
        *,
        device: int,
        samplerate: int,
        channels: int,
        blocksize: int,
        callback: Any,
        finished_callback: Any | None = None,
    ) -> AudioStreamLike:
        try:
            return cast(
                AudioStreamLike,
                self._sd.InputStream(
                    device=device,
                    samplerate=samplerate,
                    channels=channels,
                    blocksize=blocksize,
                    dtype="float32",
                    callback=callback,
                    finished_callback=finished_callback,
                ),
            )
        except Exception as exc:
            raise AudioBackendError(f"open input stream failed: {exc}") from exc

    def open_output_stream(
        self,
        *,
        device: int,
        samplerate: int,
        channels: int,
        blocksize: int,
        callback: Any,
        finished_callback: Any | None = None,
    ) -> AudioStreamLike:
        try:
            return cast(
                AudioStreamLike,
                self._sd.OutputStream(
                    device=device,
                    samplerate=samplerate,
                    channels=channels,
                    blocksize=blocksize,
                    dtype="float32",
                    callback=callback,
                    finished_callback=finished_callback,
                ),
            )
        except Exception as exc:
            raise AudioBackendError(f"open output stream failed: {exc}") from exc
