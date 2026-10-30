import numpy as np
import pytest

from voice_runtime.engines.base import EngineKind
from voice_runtime.engines.fake import (
    FakeAECProcessor,
    FakeASREngine,
    FakeTTSEngine,
    FakeVADEngine,
    FakeWakeEngine,
)
from voice_runtime.engines.manager import EngineManager


async def test_fake_wake_and_vad() -> None:
    wake = FakeWakeEngine()
    wake.fire("hello")
    assert await wake.detect(np.zeros(160, dtype=np.float32)) == "hello"
    assert await wake.detect(np.zeros(160, dtype=np.float32)) is None

    vad = FakeVADEngine(threshold=0.1)
    assert await vad.process(np.full(160, 0.5, dtype=np.float32)) is True
    assert await vad.process(np.zeros(160, dtype=np.float32)) is False


async def test_fake_asr_partial_and_final() -> None:
    asr = FakeASREngine()
    await asr.start_stream()
    asr.feed_text("你", final=False)
    assert await asr.get_partial_result() == "你"
    asr.feed_text("你好", final=True)
    assert await asr.get_final_result() == "你好"


async def test_fake_tts_cancel() -> None:
    tts = FakeTTSEngine()
    chunks = [chunk async for chunk in tts.synthesize_stream("hello")]
    assert chunks
    await tts.cancel()
    assert tts.cancelled is True


async def test_manager_lifecycle_and_health() -> None:
    manager = EngineManager()
    manager.register(FakeWakeEngine())
    manager.register(FakeVADEngine())
    manager.register(FakeASREngine())
    manager.register(FakeTTSEngine())
    manager.register(FakeAECProcessor())
    await manager.initialize_all()
    health = await manager.health()
    assert {item.kind for item in health} == {
        EngineKind.WAKE,
        EngineKind.VAD,
        EngineKind.ASR,
        EngineKind.TTS,
        EngineKind.AEC,
    }
    assert all(item.ok for item in health)
    await manager.shutdown_all()
    assert not any(item.initialized for item in manager._engines.values())


async def test_manager_rejects_duplicate_kind() -> None:
    manager = EngineManager()
    manager.register(FakeWakeEngine())
    with pytest.raises(ValueError, match="already registered"):
        manager.register(FakeWakeEngine())
