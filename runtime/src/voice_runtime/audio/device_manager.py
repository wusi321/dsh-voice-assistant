"""Audio device enumeration, selection, and capability validation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

from voice_runtime.audio.backend import AudioBackend, SoundDeviceBackend

DeviceKind = Literal["input", "output"]


class DeviceError(RuntimeError):
    """No usable device or unsupported requested capabilities."""


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
class DeviceSelection:
    device: AudioDevice
    sample_rate: int
    channels: int


@dataclass(frozen=True)
class DeviceProbe:
    available: bool
    reason: str | None
    inputs: tuple[AudioDevice, ...]
    outputs: tuple[AudioDevice, ...]
    default_input: int | None
    default_output: int | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "reason": self.reason,
            "default_input": self.default_input,
            "default_output": self.default_output,
            "inputs": [asdict(device) for device in self.inputs],
            "outputs": [asdict(device) for device in self.outputs],
        }


def _to_device(index: int, item: dict[str, Any]) -> AudioDevice:
    return AudioDevice(
        index=index,
        name=str(item["name"]),
        hostapi=int(item["hostapi"]),
        max_input_channels=int(item["max_input_channels"]),
        max_output_channels=int(item["max_output_channels"]),
        default_samplerate=float(item["default_samplerate"]),
    )


class DeviceManager:
    """Owns device discovery and resolves selectors to explicit capabilities."""

    def __init__(self, backend: AudioBackend | None = None) -> None:
        self._backend: AudioBackend = backend or SoundDeviceBackend()
        self._devices: list[AudioDevice] = []
        self._default_input: int | None = None
        self._default_output: int | None = None

    @property
    def devices(self) -> tuple[AudioDevice, ...]:
        return tuple(self._devices)

    @property
    def default_input(self) -> int | None:
        return self._default_input

    @property
    def default_output(self) -> int | None:
        return self._default_output

    def refresh(self) -> tuple[AudioDevice, ...]:
        raw = self._backend.query_devices()
        self._devices = [_to_device(index, item) for index, item in enumerate(raw)]
        self._default_input, self._default_output = self._backend.default_devices()
        return tuple(self._devices)

    def inputs(self) -> tuple[AudioDevice, ...]:
        if not self._devices:
            self.refresh()
        return tuple(device for device in self._devices if device.is_input)

    def outputs(self) -> tuple[AudioDevice, ...]:
        if not self._devices:
            self.refresh()
        return tuple(device for device in self._devices if device.is_output)

    def resolve(
        self,
        selector: str | int | None,
        kind: DeviceKind,
        *,
        channels: int = 1,
        preferred_rate: int | None = None,
    ) -> DeviceSelection:
        candidates = self.inputs() if kind == "input" else self.outputs()
        if not candidates:
            raise DeviceError(f"no {kind} device available")
        device = self._pick(selector, kind, candidates)
        max_channels = device.max_input_channels if kind == "input" else device.max_output_channels
        if max_channels < channels:
            raise DeviceError(
                f"device '{device.name}' supports {max_channels} {kind} channel(s), need {channels}"
            )
        rate = self._pick_rate(device, preferred_rate)
        return DeviceSelection(device=device, sample_rate=rate, channels=channels)

    def _pick(
        self,
        selector: str | int | None,
        kind: DeviceKind,
        candidates: tuple[AudioDevice, ...],
    ) -> AudioDevice:
        if isinstance(selector, int):
            for device in candidates:
                if device.index == selector:
                    return device
            raise DeviceError(f"{kind} device index {selector} not found")
        if isinstance(selector, str) and selector.strip():
            text = selector.strip()
            if text.isdigit():
                return self._pick(int(text), kind, candidates)
            lowered = text.casefold()
            matches = [device for device in candidates if lowered in device.name.casefold()]
            if not matches:
                raise DeviceError(f"{kind} device matching '{selector}' not found")
            return matches[0]
        default_index = self._default_input if kind == "input" else self._default_output
        if default_index is not None:
            for device in candidates:
                if device.index == default_index:
                    return device
        return candidates[0]

    @staticmethod
    def _pick_rate(device: AudioDevice, preferred_rate: int | None) -> int:
        default = round(device.default_samplerate)
        if default <= 0:
            default = 48_000
        if preferred_rate is None:
            return default
        if not 8_000 <= preferred_rate <= 192_000:
            raise DeviceError(f"sample rate {preferred_rate} is out of range")
        return preferred_rate


def probe(backend: AudioBackend | None = None) -> DeviceProbe:
    """Enumerate without opening a stream; never raises."""
    try:
        manager = DeviceManager(backend)
        manager.refresh()
        inputs = manager.inputs()
        outputs = manager.outputs()
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
        inputs=inputs,
        outputs=outputs,
        default_input=manager.default_input,
        default_output=manager.default_output,
    )
