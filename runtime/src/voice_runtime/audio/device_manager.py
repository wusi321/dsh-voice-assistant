"""Audio device enumeration and capability probing.

`sounddevice` is imported lazily so unit tests and the `doctor` command still
work on machines without PortAudio. P1 only reads capabilities; opening streams
is P2 work.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class AudioDevice:
    index: int
    name: str
    hostapi: int
    max_input_channels: int
    max_output_channels: int
    default_samplerate: float

    @property
    def is_input(self) -> bool:
        return self.max_input_channels > 0

    @property
    def is_output(self) -> bool:
        return self.max_output_channels > 0


@dataclass(frozen=True)
class DeviceProbe:
    available: bool
    reason: str | None
    inputs: tuple[AudioDevice, ...]
    outputs: tuple[AudioDevice, ...]
    default_input: int | None
    default_output: int | None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "available": self.available,
            "reason": self.reason,
            "default_input": self.default_input,
            "default_output": self.default_output,
            "inputs": [asdict(device) for device in self.inputs],
            "outputs": [asdict(device) for device in self.outputs],
        }
        return result


def list_devices() -> list[AudioDevice]:
    import sounddevice as sd  # type: ignore[import-not-found]

    raw = sd.query_devices()
    devices: list[AudioDevice] = []
    for index, item in enumerate(raw):
        devices.append(
            AudioDevice(
                index=index,
                name=str(item["name"]),
                hostapi=int(item["hostapi"]),
                max_input_channels=int(item["max_input_channels"]),
                max_output_channels=int(item["max_output_channels"]),
                default_samplerate=float(item["default_samplerate"]),
            )
        )
    return devices


def default_devices() -> tuple[int | None, int | None]:
    import sounddevice as sd  # type: ignore[import-not-found]

    try:
        input_device, output_device = sd.default.device
    except (TypeError, ValueError):
        return None, None
    return (
        int(input_device) if input_device is not None and int(input_device) >= 0 else None,
        int(output_device) if output_device is not None and int(output_device) >= 0 else None,
    )


def probe() -> DeviceProbe:
    """Enumerate devices without opening a stream; never raises."""
    try:
        devices = list_devices()
        default_input, default_output = default_devices()
    except Exception as exc:
        return DeviceProbe(
            available=False,
            reason=f"{type(exc).__name__}: {exc}",
            inputs=(),
            outputs=(),
            default_input=None,
            default_output=None,
        )
    return DeviceProbe(
        available=True,
        reason=None,
        inputs=tuple(device for device in devices if device.is_input),
        outputs=tuple(device for device in devices if device.is_output),
        default_input=default_input,
        default_output=default_output,
    )
