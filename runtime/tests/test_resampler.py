import numpy as np

from voice_runtime.audio.resampler import StreamingResampler, resample_audio


def test_resample_48k_to_16k_length() -> None:
    source = np.sin(2 * np.pi * 440 * np.arange(4800) / 48000).astype(np.float32)
    out = resample_audio(source, 48000, 16000)
    assert out.dtype == np.float32
    assert abs(len(out) - 1600) <= 2


def test_resample_identity() -> None:
    source = np.arange(100, dtype=np.float32)
    np.testing.assert_array_equal(resample_audio(source, 16000, 16000), source)


def test_streaming_resampler_ratio_across_blocks() -> None:
    resampler = StreamingResampler(48000, 16000)
    blocks = [np.ones(480, dtype=np.float32) for _ in range(10)]
    out = np.concatenate([resampler.process(block) for block in blocks])
    assert abs(len(out) - 1600) <= 2
    assert np.allclose(out, 1.0)


def test_streaming_resampler_upsample() -> None:
    resampler = StreamingResampler(16000, 24000)
    out = resampler.process(np.arange(160, dtype=np.float32))
    assert 230 <= len(out) <= 240


def test_streaming_resampler_empty_and_reset() -> None:
    resampler = StreamingResampler(48000, 16000)
    assert resampler.process(np.zeros(0, dtype=np.float32)).size == 0
    resampler.process(np.ones(10, dtype=np.float32))
    resampler.reset()
    assert resampler.process(np.zeros(0, dtype=np.float32)).size == 0
