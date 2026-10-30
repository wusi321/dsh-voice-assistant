import json

from websockets.asyncio.client import connect

from voice_runtime.config.schema import RuntimeConfig
from voice_runtime.engines.fake import FakeTTSEngine
from voice_runtime.runtime.supervisor import RuntimeSupervisor
from voice_runtime.transport.authentication import TokenAuth
from voice_runtime.voice_service import NullAudio, RuntimeVoiceService


async def test_tts_speak_over_websocket(tmp_path) -> None:
    config = RuntimeConfig(host="127.0.0.1", port=0, data_dir=tmp_path)
    service = RuntimeVoiceService(tts=FakeTTSEngine(), audio=NullAudio())
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
                        "payload": {"utteranceId": "u1", "text": "你好"},
                    }
                )
            )
            started = json.loads(await ws.recv())
            finished = json.loads(await ws.recv())
            assert started["type"] == "tts.started"
            assert started["payload"]["utteranceId"] == "u1"
            assert finished["type"] == "tts.finished"
    finally:
        await supervisor.stop()
