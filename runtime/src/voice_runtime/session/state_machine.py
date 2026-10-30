"""Voice state machine and Avatar projection.

Voice, Agent, and Avatar states are deliberately separate. The Runtime owns
VoiceState; the DSH plugin derives AgentState from Session/Agent events; Avatar
state is a projection of both (see `derive_avatar_state`).
"""

from __future__ import annotations

from collections import deque
from enum import StrEnum


class VoiceState(StrEnum):
    IDLE = "IDLE"
    WAKEUP = "WAKEUP"
    LISTENING = "LISTENING"
    TRANSCRIBING = "TRANSCRIBING"
    DISPATCHING = "DISPATCHING"
    THINKING = "THINKING"
    SPEAKING = "SPEAKING"
    INTERRUPTING = "INTERRUPTING"
    CONFIRMATION = "CONFIRMATION"
    ERROR = "ERROR"


class AgentState(StrEnum):
    IDLE = "IDLE"
    THINKING = "THINKING"
    TOOL_CALLING = "TOOL_CALLING"
    TOOL_RUNNING = "TOOL_RUNNING"
    WAITING_CONFIRMATION = "WAITING_CONFIRMATION"
    SUCCESS = "SUCCESS"
    ERROR = "ERROR"
    CANCELLED = "CANCELLED"


class AvatarState(StrEnum):
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    THINKING = "THINKING"
    WORKING = "WORKING"
    SPEAKING = "SPEAKING"
    CONFIRMATION = "CONFIRMATION"
    SUCCESS = "SUCCESS"
    ERROR = "ERROR"


ALLOWED_TRANSITIONS: dict[VoiceState, frozenset[VoiceState]] = {
    VoiceState.IDLE: frozenset({VoiceState.WAKEUP, VoiceState.ERROR}),
    VoiceState.WAKEUP: frozenset({VoiceState.LISTENING, VoiceState.IDLE, VoiceState.ERROR}),
    VoiceState.LISTENING: frozenset(
        {VoiceState.TRANSCRIBING, VoiceState.INTERRUPTING, VoiceState.IDLE, VoiceState.ERROR}
    ),
    VoiceState.TRANSCRIBING: frozenset(
        {VoiceState.DISPATCHING, VoiceState.LISTENING, VoiceState.IDLE, VoiceState.ERROR}
    ),
    VoiceState.DISPATCHING: frozenset(
        {VoiceState.THINKING, VoiceState.LISTENING, VoiceState.IDLE, VoiceState.ERROR}
    ),
    VoiceState.THINKING: frozenset(
        {
            VoiceState.SPEAKING,
            VoiceState.CONFIRMATION,
            VoiceState.INTERRUPTING,
            VoiceState.IDLE,
            VoiceState.ERROR,
        }
    ),
    VoiceState.SPEAKING: frozenset(
        {VoiceState.LISTENING, VoiceState.INTERRUPTING, VoiceState.IDLE, VoiceState.ERROR}
    ),
    VoiceState.INTERRUPTING: frozenset(
        {VoiceState.LISTENING, VoiceState.THINKING, VoiceState.IDLE, VoiceState.ERROR}
    ),
    VoiceState.CONFIRMATION: frozenset(
        {VoiceState.THINKING, VoiceState.LISTENING, VoiceState.IDLE, VoiceState.ERROR}
    ),
    VoiceState.ERROR: frozenset({VoiceState.IDLE}),
}


class InvalidTransition(RuntimeError):
    """Raised when a state change is not in the transition table."""


class VoiceStateMachine:
    """Synchronous, testable state holder with transition history."""

    def __init__(self, history_size: int = 64) -> None:
        self._state = VoiceState.IDLE
        self._history: deque[tuple[VoiceState, VoiceState, str]] = deque(maxlen=history_size)

    @property
    def state(self) -> VoiceState:
        return self._state

    @property
    def history(self) -> tuple[tuple[VoiceState, VoiceState, str], ...]:
        return tuple(self._history)

    def can_transition(self, next_state: VoiceState) -> bool:
        return next_state in ALLOWED_TRANSITIONS[self._state]

    def transition(self, next_state: VoiceState, reason: str = "") -> VoiceState:
        if next_state == self._state:
            return self._state
        if not self.can_transition(next_state):
            raise InvalidTransition(f"{self._state} -> {next_state} is not allowed")
        previous, self._state = self._state, next_state
        self._history.append((previous, next_state, reason))
        return self._state

    def force_idle(self, reason: str = "global_cancel") -> VoiceState:
        """Global cancel/device loss: any state may return to IDLE, with history."""
        if self._state != VoiceState.IDLE:
            previous, self._state = self._state, VoiceState.IDLE
            self._history.append((previous, self._state, reason))
        return self._state

    def reset(self) -> None:
        self._state = VoiceState.IDLE
        self._history.clear()


def derive_avatar_state(voice: VoiceState, agent: AgentState = AgentState.IDLE) -> AvatarState:
    """Project Voice + Agent into Avatar presentation.

    Agent work wins over an idle/listening voice, but never over an explicit
    confirmation or error. Speaking wins only when the Agent is not working.
    """
    if agent is AgentState.WAITING_CONFIRMATION:
        return AvatarState.CONFIRMATION
    if agent is AgentState.ERROR:
        return AvatarState.ERROR
    if agent in (AgentState.THINKING, AgentState.TOOL_CALLING):
        return AvatarState.THINKING
    if agent is AgentState.TOOL_RUNNING:
        return AvatarState.WORKING
    if agent is AgentState.SUCCESS and voice is VoiceState.IDLE:
        return AvatarState.SUCCESS
    if voice is VoiceState.ERROR:
        return AvatarState.ERROR
    if voice is VoiceState.SPEAKING:
        return AvatarState.SPEAKING
    if voice in (VoiceState.WAKEUP, VoiceState.LISTENING, VoiceState.TRANSCRIBING):
        return AvatarState.LISTENING
    if voice in (VoiceState.THINKING, VoiceState.DISPATCHING, VoiceState.INTERRUPTING):
        return AvatarState.THINKING
    if voice is VoiceState.CONFIRMATION:
        return AvatarState.CONFIRMATION
    return AvatarState.IDLE
