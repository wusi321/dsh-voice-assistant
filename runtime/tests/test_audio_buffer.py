import numpy as np

from voice_runtime.audio.audio_buffer import AudioRingBuffer


def test_write_and_read_oldest_first() -> None:
    ring = AudioRingBuffer(5)
    assert ring.write(np.array([1, 2, 3], dtype=np.float32)) == 3
    assert ring.available == 3
    np.testing.assert_array_equal(ring.read(2), np.array([1, 2], dtype=np.float32))
    assert ring.available == 1


def test_overwrite_keeps_newest_samples() -> None:
    ring = AudioRingBuffer(4)
    ring.write(np.array([1, 2, 3, 4], dtype=np.float32))
    ring.write(np.array([5, 6], dtype=np.float32))
    assert ring.available == 4
    np.testing.assert_array_equal(ring.read(4), np.array([3, 4, 5, 6], dtype=np.float32))


def test_large_write_keeps_tail() -> None:
    ring = AudioRingBuffer(3)
    ring.write(np.array([1, 2, 3, 4, 5], dtype=np.float32))
    np.testing.assert_array_equal(ring.snapshot(), np.array([3, 4, 5], dtype=np.float32))


def test_snapshot_does_not_consume() -> None:
    ring = AudioRingBuffer(4)
    ring.write(np.array([1, 2], dtype=np.float32))
    np.testing.assert_array_equal(ring.snapshot(1), np.array([2], dtype=np.float32))
    assert ring.available == 2


def test_empty_reads_and_clear() -> None:
    ring = AudioRingBuffer(4)
    assert ring.read(3).size == 0
    assert ring.snapshot().size == 0
    ring.write(np.array([1.0], dtype=np.float32))
    ring.clear()
    assert ring.available == 0


def test_capacity_must_be_positive() -> None:
    try:
        AudioRingBuffer(0)
    except ValueError as exc:
        assert "positive" in str(exc)
    else:
        raise AssertionError("expected ValueError")
