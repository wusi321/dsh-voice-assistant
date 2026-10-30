import json

from websockets.asyncio.client import connect

from voice_runtime.config.schema import RuntimeConfig
from voice_runtime.runtime.supervisor import RuntimeSupervisor
from voice_runtime.transport.authentication import TokenAuth


async def test_supervisor_start_connect_and_stop(tmp_path) -> None:
    config = RuntimeConfig(host="127.0.0.1", port=0, data_dir=tmp_path)
    supervisor = RuntimeSupervisor(config, auth=TokenAuth("secret"))
    info = await supervisor.start()
    try:
        assert supervisor.discovery_path.exists()
        assert info.port == supervisor.server.port
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
            assert json.loads(await ws.recv())["type"] == "auth.ok"
            ready = json.loads(await ws.recv())
            assert ready["type"] == "runtime.ready"
            assert ready["payload"]["runtimeVersion"] == "0.1.0"
    finally:
        await supervisor.stop()
    assert not supervisor.discovery_path.exists()
