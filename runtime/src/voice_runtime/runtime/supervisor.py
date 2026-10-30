"""Runtime supervisor: discovery, transport, lifecycle, health."""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from pathlib import Path

from websockets.asyncio.server import ServerConnection

from voice_runtime import __version__
from voice_runtime.config.schema import RuntimeConfig
from voice_runtime.runtime.health import HealthMonitor
from voice_runtime.runtime.lifecycle import Lifecycle, LifecycleState
from voice_runtime.session.manager import SessionManager
from voice_runtime.transport.authentication import TokenAuth
from voice_runtime.transport.discovery import (
    DiscoveryInfo,
    discovery_path,
    remove_discovery,
    write_discovery,
)
from voice_runtime.transport.protocol import VoiceEvent
from voice_runtime.transport.websocket_server import RuntimeWebSocketServer
from voice_runtime.utils.platform import data_dir, ensure_dir
from voice_runtime.voice_service import RuntimeVoiceService

logger = logging.getLogger(__name__)


class RuntimeSupervisor:
    """Owns the pieces that must start and stop in order."""

    def __init__(
        self,
        config: RuntimeConfig,
        *,
        auth: TokenAuth | None = None,
        voice_service: RuntimeVoiceService | None = None,
    ) -> None:
        self.config = config
        self.auth = auth or TokenAuth.generate()
        self.session = SessionManager()
        self.health = HealthMonitor()
        self.lifecycle = Lifecycle()
        self.voice_service = voice_service
        self.data_root: Path = config.resolved_data_dir(data_dir())
        self.discovery_path: Path = discovery_path(self.data_root)
        self.server = RuntimeWebSocketServer(
            config,
            self.auth,
            session_manager=self.session,
            on_event=self._on_event if voice_service is not None else None,
        )

    async def start(self) -> DiscoveryInfo:
        self.lifecycle.mark(LifecycleState.STARTING)
        ensure_dir(self.data_root)
        ensure_dir(self.discovery_path.parent)
        if self.voice_service is not None:
            self.voice_service.set_emitter(self._emit_voice_event)
            await self.voice_service.start()
        port = await self.server.start()
        info = DiscoveryInfo(
            pid=os.getpid(),
            host=self.config.host,
            port=port,
            token=self.auth.token,
            runtime_version=__version__,
            protocol_version=self.config.protocol_version,
            started_at=datetime.now(UTC).isoformat(timespec="seconds"),
        )
        write_discovery(self.discovery_path, info)
        self.lifecycle.mark(LifecycleState.RUNNING)
        logger.info("runtime ready on port %s", port)
        return info

    async def _on_event(self, _ws: ServerConnection, event: VoiceEvent) -> None:
        if self.voice_service is not None:
            await self.voice_service.handle_event(event)

    async def _emit_voice_event(self, event_type: str, payload: dict[str, object]) -> None:
        await self.server.send_event(event_type, payload)  # type: ignore[arg-type]

    async def wait_for_shutdown(self) -> None:
        await self.server.shutdown_event.wait()

    async def stop(self) -> None:
        if self.lifecycle.state is LifecycleState.RUNNING:
            self.lifecycle.mark(LifecycleState.STOPPING)
        await self.server.stop()
        if self.voice_service is not None:
            await self.voice_service.stop()
        remove_discovery(self.discovery_path)
        if self.lifecycle.state is LifecycleState.STOPPING:
            self.lifecycle.mark(LifecycleState.STOPPED)
