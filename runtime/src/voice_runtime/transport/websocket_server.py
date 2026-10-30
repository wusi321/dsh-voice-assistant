"""Localhost WebSocket server for the Runtime control channel."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import ValidationError
from websockets.asyncio.server import Server, ServerConnection, serve
from websockets.exceptions import ConnectionClosed

from voice_runtime import __version__
from voice_runtime.config.schema import RuntimeConfig
from voice_runtime.session.manager import SessionManager
from voice_runtime.transport.authentication import AuthError, TokenAuth
from voice_runtime.transport.protocol import (
    AuthErrorResponse,
    AuthOk,
    AuthRequest,
    PcmFrame,
    ProtocolError,
    VoiceEvent,
    parse_event,
)

logger = logging.getLogger(__name__)

EventHandler = Callable[[ServerConnection, VoiceEvent], Awaitable[None]]
FrameHandler = Callable[[ServerConnection, PcmFrame], Awaitable[None]]


class RuntimeWebSocketServer:
    """Authenticated control channel; binary messages are PCM frames."""

    def __init__(
        self,
        config: RuntimeConfig,
        auth: TokenAuth,
        *,
        session_manager: SessionManager | None = None,
        on_event: EventHandler | None = None,
        on_frame: FrameHandler | None = None,
    ) -> None:
        self._config = config
        self._auth = auth
        self._session = session_manager or SessionManager()
        self._on_event = on_event
        self._on_frame = on_frame
        self._server: Server | None = None
        self._clients: set[ServerConnection] = set()
        self._started_at = time.monotonic()
        self.shutdown_event = asyncio.Event()
        self.port = config.port

    @property
    def clients(self) -> int:
        return len(self._clients)

    async def start(self) -> int:
        """Bind and start serving; returns the actual port."""
        self._server = await serve(
            self._handle,
            self._config.host,
            self._config.port,
            max_size=1 << 20,
            ping_interval=20,
            ping_timeout=20,
        )
        socket = next(iter(self._server.sockets))
        self.port = int(socket.getsockname()[1])
        logger.info("runtime websocket listening on %s:%s", self._config.host, self.port)
        return self.port

    async def stop(self) -> None:
        """Close client connections and the listener."""
        for client in list(self._clients):
            try:
                await client.close(code=1001, reason="runtime stopping")
            except ConnectionClosed:
                pass
        self._clients.clear()
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def broadcast(self, event: dict[str, Any]) -> None:
        message = json.dumps(event, ensure_ascii=False)
        for client in list(self._clients):
            try:
                await client.send(message)
            except ConnectionClosed:
                self._clients.discard(client)

    async def send_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        event = self._session.session.next_event(  # type: ignore[arg-type]
            event_type,  # type: ignore[arg-type]
            payload,
        )
        if session_id is not None:
            event["sessionId"] = session_id
        await self.broadcast(event)
        return event

    async def _handle(self, ws: ServerConnection) -> None:
        if len(self._clients) >= self._config.max_connections:
            await ws.close(code=1013, reason="runtime busy")
            return
        self._clients.add(ws)
        try:
            if not await self._authenticate(ws):
                return
            await self._send_ready(ws)
            async for raw in ws:
                await self._handle_message(ws, raw)
        except ConnectionClosed:
            pass
        except Exception:  # noqa: BLE001 - one client must not take down the server
            logger.exception("client handler failed")
            try:
                await ws.close(code=1011, reason="runtime error")
            except ConnectionClosed:
                pass
        finally:
            self._clients.discard(ws)

    async def _authenticate(self, ws: ServerConnection) -> bool:
        try:
            raw = await asyncio.wait_for(
                ws.recv(), timeout=self._config.auth_timeout_seconds
            )
        except TimeoutError:
            await self._send_auth_error(ws, "auth_failed", "authentication timed out")
            return False
        if not isinstance(raw, str):
            await self._send_auth_error(ws, "invalid_message", "first message must be JSON auth")
            return False
        try:
            request = AuthRequest.model_validate_json(raw)
        except ValidationError:
            await self._send_auth_error(ws, "invalid_message", "invalid auth message")
            return False
        if request.protocolVersion != self._config.protocol_version:
            await self._send_auth_error(
                ws,
                "protocol_version_mismatch",
                f"expected protocol {self._config.protocol_version}",
            )
            return False
        try:
            self._auth.require(request.token)
        except AuthError:
            await self._send_auth_error(ws, "auth_failed", "invalid runtime token")
            return False
        await ws.send(
            AuthOk(protocolVersion=self._config.protocol_version, runtimeVersion=__version__).model_dump_json()
        )
        return True

    async def _send_auth_error(
        self, ws: ServerConnection, code: str, message: str
    ) -> None:
        response = AuthErrorResponse(code=code, message=message)  # type: ignore[arg-type]
        await ws.send(response.model_dump_json())
        await ws.close(code=4001, reason=code)

    async def _send_ready(self, ws: ServerConnection) -> None:
        capabilities = ["fake-audio"] if self._config.fake_audio else []
        await ws.send(
            json.dumps(
                self._session.session.next_event(
                    "runtime.ready",
                    {
                        "runtimeVersion": __version__,
                        "protocolVersion": self._config.protocol_version,
                        "capabilities": capabilities,
                        "audio": {"sampleRate": 16_000, "channels": 1},
                    },
                ),
                ensure_ascii=False,
            )
        )

    async def _handle_message(self, ws: ServerConnection, raw: str | bytes) -> None:
        if isinstance(raw, bytes):
            try:
                frame = PcmFrame.decode(raw)
            except ProtocolError as exc:
                await self._send_error(ws, "invalid_message", str(exc))
                return
            if self._on_frame is not None:
                await self._on_frame(ws, frame)
            return

        try:
            event = parse_event(raw)
        except ProtocolError as exc:
            await self._send_error(ws, "invalid_message", str(exc))
            return

        if event.type == "ping":
            ping_id = str(event.payload.get("pingId", ""))
            await self.send_event(
                "pong",
                {"pingId": ping_id, "receivedAt": int(time.time() * 1000)},
            )
            return
        if event.type == "runtime.shutdown":
            logger.info("shutdown requested by client")
            self.shutdown_event.set()
            await ws.close(code=1001, reason="runtime shutdown")
            return
        if self._on_event is not None:
            await self._on_event(ws, event)

    async def _send_error(self, ws: ServerConnection, code: str, message: str) -> None:
        await ws.send(
            json.dumps(
                self._session.session.next_event(
                    "runtime.error",
                    {"code": code, "message": message, "fatal": False},
                ),
                ensure_ascii=False,
            )
        )
