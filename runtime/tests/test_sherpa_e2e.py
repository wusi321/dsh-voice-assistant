import importlib.util
import os
from pathlib import Path

import numpy as np
import pytest

from voice_runtime.audio.resampler import resample_audio
from voice_runtime.engines.sherpa_asr import SherpaASR
from voice_runtime.engines.sherpa_kws import SherpaKWS
from voice_runtime.engines.sherpa_tts import SherpaTTS
from voice_runtime.engines.sherpa_vad import SherpaVAD

MODEL_ROOT = Path(os.environ.get("DSH_VOICE_TEST_MODELS", "D:/dsh-voice-models"))
pytestmark = [
    pytest.mark.skipif(not MODEL_ROOT.is_dir(), reason="local sherpa models are not installed"),
    pytest.mark.skipif(
        not importlib.util.find_spec("sherpa_onnx"), reason="sherpa-onnx is not installed"
    ),
]


def tts_dir() -> Path:
    kokoro = MODEL_ROOT / "kokoro-multi-lang-v1_1"
    if kokoro.is_dir():
        return kokoro
    return MODEL_ROOT / "vits-piper-zh_CN-huayan-medium"


async def synthesize(text: str) -> tuple[np.ndarray, int]:
    directory = tts_dir()
    tts = SherpaTTS(directory, kind="kokoro" if (directory / "voices.bin").exists() else "vits")
    await tts.initialize()
    chunks = [chunk async for chunk in tts.synthesize_stream(text)]
    await tts.shutdown()
    return np.concatenate(chunks), tts.sample_rate


async def test_tts_generates_audio() -> None:
    audio, sample_rate = await synthesize("你好，这是语音测试。")
    assert sample_rate > 0
    assert audio.size > sample_rate * 0.5
    assert np.max(np.abs(audio)) > 0.01


async def test_vad_asr_end_to_end() -> None:
    audio, sample_rate = await synthesize("你好，请打开台灯。")
    if sample_rate != 16_000:
        audio = resample_audio(audio, sample_rate, 16_000)
    vad = SherpaVAD(MODEL_ROOT / "silero_vad.onnx")
    await vad.initialize()
    for start in range(0, audio.size, 512):
        await vad.process(audio[start : start + 512])
    await vad.flush()
    segments = vad.segments()
    assert segments, "VAD found no speech in synthesized audio"
    speech = np.concatenate([segment.samples for segment in segments])

    asr = SherpaASR(MODEL_ROOT / "sherpa-onnx-streaming-zipformer-zh-14M-2023-02-23")
    await asr.initialize()
    partials: list[str] = []
    for start in range(0, speech.size, 1600):
        await asr.accept_audio(speech[start : start + 1600])
        partial = await asr.get_partial_result()
        if partial and (not partials or partial != partials[-1]):
            partials.append(partial)
    final = await asr.get_final_result()
    await vad.shutdown()
    await asr.shutdown()
    assert partials, "streaming ASR produced no partial results"
    assert final, "streaming ASR produced no final result"
    assert "台灯" in final or "打开" in final or len(final) >= 4


async def test_kws_detects_wake_phrase() -> None:
    audio, sample_rate = await synthesize("你好军哥。")
    if sample_rate != 16_000:
        audio = resample_audio(audio, sample_rate, 16_000)
    # KWS needs a short trailing silence to emit a result, as it does in a live stream.
    audio = np.concatenate([audio, np.zeros(16_000, dtype=np.float32)])
    kws = SherpaKWS(MODEL_ROOT / "sherpa-onnx-kws-zipformer-wenetspeech-3.3M-2024-01-01")
    await kws.initialize()
    hits: list[str] = []
    for start in range(0, audio.size, 1600):
        hit = await kws.detect(audio[start : start + 1600])
        if hit:
            hits.append(hit)
    await kws.shutdown()
    assert hits, "KWS did not detect the synthesized wake phrase"
