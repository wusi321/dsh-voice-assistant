import asyncio
import json

import pytest
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from voice_runtime.config.schema import RuntimeConfig
from voice_runtime.transport.authentication import TokenAuth
from voice_runtime.transport.protocol import make_event
from voice_runtime.transport.websocket_server import RuntimeWebSocketServer


async def auth_message(token: str, protocol: int = 1) -> str:
    return json.dumps(
        {
            "type": "auth",
            "version": 1,
            "token": token,
            "clientId": "test-client",
            "protocolVersion": protocol,
        }
    )


@pytest.fixture
async def server():
    config = RuntimeConfig(host="127.0.0.1", port=0, auth_timeout_seconds=2)
    instance = RuntimeWebSocketServer(config, TokenAuth("secret"))
    port = await instance.start()
    try:
        yield instance, port
    finally:
        await instance.stop()


async def test_auth_ready_and_ping(server) -> None:
    instance, port = server
    async with connect(f"ws://127.0.0.1:{port}") as ws:
        await ws.send(await auth_message("secret"))
        auth = json.loads(await ws.recv())
        assert auth["type"] == "auth.ok"
        ready = json.loads(await ws.recv())
        assert ready["type"] == "runtime.ready"
        assert ready["payload"]["protocolVersion"] == 1
        assert "fake-audio" not in ready["payload"]["capabilities"]

        await ws.send(json.dumps(make_event("ping", {"pingId": "p1"}, session_id="s1", sequence=1)))
        pong = json.loads(await ws.recv())
        assert pong["type"] == "pong"
        assert pong["payload"]["pingId"] == "p1"
    assert instance.clients == 0


async def test_bad_token_is_rejected(server) -> None:
    _, port = server
    async with connect(f"ws://127.0.0.1:{port}") as ws:
        await ws.send(await auth_message("wrong"))
        error = json.loads(await ws.recv())
        assert error == {
            "type": "auth.error",
            "code": "auth_failed",
            "message": "invalid runtime token",
        }
        with pytest.raises(ConnectionClosed):
            await ws.recv()


async def test_protocol_mismatch_is_rejected(server) -> None:
    _, port = server
    async with connect(f"ws://127.0.0.1:{port}") as ws:
        await ws.send(await auth_message("secret", protocol=2))
        error = json.loads(await ws.recv())
        assert error["type"] == "auth.error"
        assert error["code"] == "protocol_version_mismatch"


async def test_binary_frame_is_accepted(server) -> None:
    instance, port = server
    frames = []

    async def on_frame(_ws, frame):
        frames.append(frame)

    instance._on_frame = on_frame  # type: ignore[assignment]
    async with connect(f"ws://127.0.0.1:{port}") as ws:
        await ws.send(await auth_message("secret"))
        await ws.recv()
        await ws.recv()
        await ws.send(b"\x00" * 8)
        error = json.loads(await ws.recv())
        assert error["type"] == "runtime.error"
        assert error["payload"]["code"] == "invalid_message"
    assert frames == []


async def test_shutdown_event_set(server) -> None:
    instance, port = server
    async with connect(f"ws://127.0.0.1:{port}") as ws:
        await ws.send(await auth_message("secret"))
        await ws.recv()
        await ws.recv()
        await ws.send(json.dumps(make_event("runtime.shutdown", {}, session_id="s1", sequence=2)))
        await asyncio.sleep(0.05)
    assert instance.shutdown_event.is_set()
