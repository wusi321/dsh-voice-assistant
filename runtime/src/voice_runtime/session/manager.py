"""Session binding and event sequence management."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from voice_runtime.session.state_machine import VoiceState, VoiceStateMachine
from voice_runtime.transport.protocol import EventType, make_event


@dataclass
class VoiceSession:
    session_id: str
    state_machine: VoiceStateMachine
    sequence: int = 0

    def next_event(self, event_type: EventType, payload: dict[str, object]) -> dict[str, object]:
        self.sequence += 1
        return make_event(
            event_type,
            payload,
            session_id=self.session_id,
            sequence=self.sequence,
            event_id=uuid.uuid4().hex,
        )


class SessionManager:
    """Owns the current voice session and its state machine."""

    def __init__(self) -> None:
        self._session = VoiceSession(session_id="runtime", state_machine=VoiceStateMachine())

    @property
    def session(self) -> VoiceSession:
        return self._session

    @property
    def state(self) -> VoiceState:
        return self._session.state_machine.state

    def set_state(self, state: VoiceState, reason: str = "") -> VoiceState:
        return self._session.state_machine.transition(state, reason)

    def reset(self) -> None:
        self._session.state_machine.reset()
