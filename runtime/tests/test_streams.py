import numpy as np

from audio_fakes import FakeBackend
from voice_runtime.audio.capture import CaptureStream
from voice_runtime.audio.device_manager import DeviceManager, DeviceSelection
from voice_runtime.audio.playback import AudioChunk, PlaybackScheduler, PlaybackStream


def selection(index: int = 0, rate: int = 48_000) -> DeviceSelection:
    backend = FakeBackend()
    backend.devices = [
        {
            "name": "input" if index == 0 else "output",
            "hostapi": 0,
            "max_input_channels": 1 if index == 0 else 0,
            "max_output_channels": 0 if index == 0 else 1,
            "default_samplerate": float(rate),
        }
    ]
    manager = DeviceManager(backend)
    manager.refresh()
    return manager.resolve(None, "input" if index == 0 else "output")


def test_capture_stream_buffers_callback_audio() -> None:
    backend = FakeBackend()
    selected = selection()
    received = []
    stream = CaptureStream(backend, selected, on_audio=received.append)
    stream.start()
    fake = backend.input_streams[-1]
    fake.drive(np.array([0.1, 0.2, 0.3, 0.4], dtype=np.float32))
    assert len(received) == 1
    np.testing.assert_allclose(stream.read(4), [0.1, 0.2, 0.3, 0.4])
    stream.stop()
    assert fake.stopped and fake.closed


def test_playback_scheduler_started_finished_and_cancel() -> None:
    events: list[tuple[str, str]] = []
    scheduler = PlaybackScheduler(on_event=lambda event, uid: events.append((event, uid)))
    scheduler.push(AudioChunk("u1", np.ones(4, dtype=np.float32)))
    np.testing.assert_allclose(scheduler.take(2), [1, 1])
    np.testing.assert_allclose(scheduler.take(2), [1, 1])
    assert events == [("started", "u1"), ("finished", "u1")]
    assert not scheduler.is_active

    scheduler.push(AudioChunk("u2", np.ones(8, dtype=np.float32)))
    assert scheduler.take(2).size == 2
    assert scheduler.cancel("u2") == 1
    assert events[-1] == ("interrupted", "u2")
    assert not scheduler.is_active


def test_playback_stream_writes_output_and_reference() -> None:
    backend = FakeBackend()
    selected = selection(index=1)
    scheduler = PlaybackScheduler()
    referenced = []
    stream = PlaybackStream(backend, selected, scheduler, on_reference=referenced.append)
    stream.start()
    scheduler.push(AudioChunk("u1", np.full(16, 0.5, dtype=np.float32)))
    fake = backend.output_streams[-1]
    fake.drive()
    np.testing.assert_allclose(fake.output[:16], 0.5)
    assert np.count_nonzero(fake.output) == 16
    assert len(referenced) == 1
    assert referenced[0].shape == (fake.frames,)
    stream.stop()
    assert fake.stopped and fake.closed
