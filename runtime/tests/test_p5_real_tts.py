import importlib.util
import json
import os
from pathlib import Path

import pytest
from websockets.asyncio.client import connect

from voice_runtime.config.schema import RuntimeConfig
from voice_runtime.engines.sherpa_tts import SherpaTTS
from voice_runtime.runtime.supervisor import RuntimeSupervisor
from voice_runtime.transport.authentication import TokenAuth
from voice_runtime.voice_service import NullAudio, RuntimeVoiceService

MODEL_ROOT = Path(os.environ.get("DSH_VOICE_TEST_MODELS", "D:/dsh-voice-models"))
pytestmark = [
    pytest.mark.skipif(not MODEL_ROOT.is_dir(), reason="local sherpa models are not installed"),
    pytest.mark.skipif(
        not importlib.util.find_spec("sherpa_onnx"), reason="sherpa-onnx is not installed"
    ),
]


async def test_real_tts_over_websocket(tmp_path) -> None:
    tts_dir = MODEL_ROOT / "vits-piper-zh_CN-huayan-medium"
    if not tts_dir.is_dir():
        pytest.skip("VITS test model is not installed")
    config = RuntimeConfig(host="127.0.0.1", port=0, data_dir=tmp_path)
    service = RuntimeVoiceService(tts=SherpaTTS(tts_dir), audio=NullAudio())
    supervisor = RuntimeSupervisor(config, auth=TokenAuth("secret"), voice_service=service)
    info = await supervisor.start()
    try:
        async with connect(f"ws://127.0.0.1:{info.port}") as ws:
            await ws.send(
                json.dumps(
                    {
                        "type": "auth",
                        "version": 1,
                        "token": "secret",
                        "clientId": "test",
                        "protocolVersion": 1,
                    }
                )
            )
            await ws.recv()
            await ws.recv()
            await ws.send(
                json.dumps(
                    {
                        "version": 1,
                        "id": "e1",
                        "sessionId": "s1",
                        "sequence": 1,
                        "timestamp": 1,
                        "type": "tts.speak",
                        "payload": {"utteranceId": "u1", "text": "你好，这是 P5 测试。"},
                    }
                )
            )
            started = json.loads(await ws.recv())
            finished = json.loads(await ws.recv())
            assert started["type"] == "tts.started"
            assert started["payload"]["sampleRate"] == 22_050
            assert finished["type"] == "tts.finished"
    finally:
        await supervisor.stop()
