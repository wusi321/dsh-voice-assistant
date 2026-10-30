import numpy as np
import pytest

from voice_runtime.audio.aec import PassthroughAEC, create_aec


def test_passthrough_is_identity() -> None:
    aec = PassthroughAEC()
    mic = np.linspace(-0.5, 0.5, 160, dtype=np.float32)
    out = aec.process(mic, np.zeros(160, dtype=np.float32))
    np.testing.assert_array_equal(out, mic)


def test_create_aec_disabled() -> None:
    assert isinstance(create_aec(False), PassthroughAEC)


def test_webrtc_aec_processes_16k_frames() -> None:
    pytest.importorskip("livekit")
    aec = create_aec(True, delay_ms=40)
    mic = np.zeros(320, dtype=np.float32)
    ref = np.zeros(320, dtype=np.float32)
    out = aec.process(mic, ref)
    assert out.dtype == np.float32
    assert out.size == 320
    aec.reset()
