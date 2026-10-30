"""Runtime lifecycle states."""

from __future__ import annotations

from enum import StrEnum


class LifecycleState(StrEnum):
    NEW = "new"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


class Lifecycle:
    """Small guarded state holder for the daemon."""

    def __init__(self) -> None:
        self._state = LifecycleState.NEW

    @property
    def state(self) -> LifecycleState:
        return self._state

    def mark(self, state: LifecycleState) -> None:
        allowed = {
            LifecycleState.NEW: {LifecycleState.STARTING, LifecycleState.FAILED},
            LifecycleState.STARTING: {LifecycleState.RUNNING, LifecycleState.FAILED},
            LifecycleState.RUNNING: {LifecycleState.STOPPING, LifecycleState.FAILED},
            LifecycleState.STOPPING: {LifecycleState.STOPPED, LifecycleState.FAILED},
            LifecycleState.STOPPED: set(),
            LifecycleState.FAILED: set(),
        }
        if state not in allowed[self._state]:
            raise RuntimeError(f"invalid lifecycle transition {self._state} -> {state}")
        self._state = state
