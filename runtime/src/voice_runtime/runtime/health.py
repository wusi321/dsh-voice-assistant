"""Runtime health snapshot."""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class HealthMonitor:
    started_at: float = field(default_factory=time.monotonic)

    @property
    def uptime_ms(self) -> int:
        return int((time.monotonic() - self.started_at) * 1000)

    def snapshot(
        self,
        *,
        engines: dict[str, str] | None = None,
        status: str = "ok",
        queue_depth: int | None = None,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "status": status,
            "uptimeMs": self.uptime_ms,
            "engines": engines or {},
        }
        if queue_depth is not None:
            payload["queueDepth"] = queue_depth
        return payload
