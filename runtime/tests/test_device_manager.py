import pytest

from audio_fakes import FakeBackend
from voice_runtime.audio.device_manager import DeviceError, DeviceManager


def test_enumerates_and_resolves_defaults() -> None:
    manager = DeviceManager(FakeBackend())
    manager.refresh()
    assert [device.name for device in manager.inputs()] == ["Fake Mic"]
    assert [device.name for device in manager.outputs()] == ["Fake Speaker"]
    selected = manager.resolve(None, "input")
    assert selected.device.index == 0
    assert selected.sample_rate == 48_000


def test_resolves_by_index_name_and_preferred_rate() -> None:
    backend = FakeBackend()
    backend.devices.append(
        {
            "name": "USB Headset",
            "hostapi": 0,
            "max_input_channels": 2,
            "max_output_channels": 2,
            "default_samplerate": 44_100.0,
        }
    )
    manager = DeviceManager(backend)
    manager.refresh()
    by_index = manager.resolve(2, "input", preferred_rate=16_000)
    assert by_index.device.name == "USB Headset"
    assert by_index.sample_rate == 16_000
    by_name = manager.resolve("usb", "output")
    assert by_name.device.index == 2


def test_rejects_unknown_device_and_channels() -> None:
    manager = DeviceManager(FakeBackend())
    manager.refresh()
    with pytest.raises(DeviceError, match="not found"):
        manager.resolve("missing", "input")
    with pytest.raises(DeviceError, match="channel"):
        manager.resolve(None, "input", channels=2)


def test_rejects_invalid_rate() -> None:
    manager = DeviceManager(FakeBackend())
    manager.refresh()
    with pytest.raises(DeviceError, match="out of range"):
        manager.resolve(None, "output", preferred_rate=1_000)
