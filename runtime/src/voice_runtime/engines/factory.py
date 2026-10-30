"""Build the engine manager for fake or real sherpa-onnx operation."""

from __future__ import annotations

from pathlib import Path

from voice_runtime.engines.fake import (
    FakeAECProcessor,
    FakeASREngine,
    FakeTTSEngine,
    FakeVADEngine,
    FakeWakeEngine,
)
from voice_runtime.engines.manager import EngineManager
from voice_runtime.engines.models import SherpaModels, default_model_root
from voice_runtime.engines.sherpa_asr import SherpaASR
from voice_runtime.engines.sherpa_kws import SherpaKWS
from voice_runtime.engines.sherpa_tts import SherpaTTS
from voice_runtime.engines.sherpa_vad import SherpaVAD


def build_fake_engines() -> EngineManager:
    manager = EngineManager()
    manager.register(FakeWakeEngine())
    manager.register(FakeVADEngine())
    manager.register(FakeASREngine())
    manager.register(FakeTTSEngine())
    manager.register(FakeAECProcessor())
    return manager


def build_sherpa_engines(
    root: Path | None = None,
    *,
    tts_speaker: int = 0,
    tts_speed: float = 1.0,
) -> EngineManager:
    models = SherpaModels.discover(root or default_model_root())
    manager = EngineManager()
    manager.register(SherpaVAD(models.vad_model))
    manager.register(SherpaKWS(models.kws_dir))
    manager.register(SherpaASR(models.asr_dir))
    manager.register(
        SherpaTTS(
            models.tts_dir,
            kind=models.tts_kind,
            speaker_id=tts_speaker,
            speed=tts_speed,
        )
    )
    return manager
