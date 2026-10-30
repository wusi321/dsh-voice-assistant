import numpy as np
import pytest

from audio_fakes import FakeBackend
from voice_runtime.audio.audio_io import AudioIO
from voice_runtime.audio.backend import AudioBackendError


def make_backend() -> FakeBackend:
    backend = FakeBackend()
    backend.devices = [
        {
            "name": "Built-in Mic",
            "hostapi": 0,
            "max_input_channels": 1,
            "max_output_channels": 0,
            "default_samplerate": 48_000.0,
        },
        {
            "name": "Built-in Speaker",
            "hostapi": 0,
            "max_input_channels": 0,
            "max_output_channels": 1,
            "default_samplerate": 48_000.0,
        },
        {
            "name": "USB Mic",
            "hostapi": 0,
            "max_input_channels": 1,
            "max_output_channels": 0,
            "default_samplerate": 44_100.0,
        },
        {
            "name": "USB Speaker",
            "hostapi": 0,
            "max_input_channels": 0,
            "max_output_channels": 1,
            "default_samplerate": 48_000.0,
        },
    ]
    return backend


def test_start_capture_playback_and_stop() -> None:
    backend = make_backend()
    captured = []
    audio = AudioIO(backend=backend, aec_enabled=False, on_capture=captured.append)
    audio.start()
    assert audio.running
    assert audio.input_selection is not None
    assert audio.input_selection.sample_rate == 48_000

    audio.play(np.full(2400, 0.2, dtype=np.float32), utterance_id="u1", sample_rate=24_000)
    output = backend.output_streams[-1]
    output.drive()
    assert output.output[:20].max() > 0

    fake_input = backend.input_streams[-1]
    fake_input.drive(np.full(480, 0.25, dtype=np.float32))
    assert captured
    assert captured[-1].size > 0
    assert audio.read_clean(100).size > 0

    audio.stop()
    assert not audio.running
    assert output.stopped and output.closed
    assert fake_input.stopped and fake_input.closed


def test_switch_input_device() -> None:
    backend = make_backend()
    audio = AudioIO(backend=backend, aec_enabled=False)
    audio.start()
    audio.switch_devices(input_device=2, output_device=3)
    assert audio.running
    assert audio.input_selection is not None
    assert audio.output_selection is not None
    assert audio.input_selection.device.name == "USB Mic"
    assert audio.output_selection.device.name == "USB Speaker"
    audio.stop()


def test_restart_recovers_after_open_failure() -> None:
    backend = make_backend()
    audio = AudioIO(backend=backend, aec_enabled=False)
    backend.fail_input = True
    with pytest.raises(AudioBackendError):
        audio.start()
    assert not audio.running
    backend.fail_input = False
    assert audio.restart(retries=2, delay=0.01) is True
    assert audio.running
    audio.stop()


def test_stream_finished_calls_error_callback() -> None:
    backend = make_backend()
    errors = []
    audio = AudioIO(backend=backend, aec_enabled=False, on_error=errors.append)
    audio.start()
    backend.input_streams[-1].finish()
    assert errors
    audio.stop()
