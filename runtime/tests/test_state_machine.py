import pytest

from voice_runtime.session.state_machine import (
    AgentState,
    AvatarState,
    InvalidTransition,
    VoiceState,
    VoiceStateMachine,
    derive_avatar_state,
)


def test_happy_path_idle_to_speaking() -> None:
    machine = VoiceStateMachine()
    for state in (
        VoiceState.WAKEUP,
        VoiceState.LISTENING,
        VoiceState.TRANSCRIBING,
        VoiceState.DISPATCHING,
        VoiceState.THINKING,
        VoiceState.SPEAKING,
    ):
        assert machine.transition(state) is state
    assert machine.state is VoiceState.SPEAKING


def test_illegal_transition_raises() -> None:
    machine = VoiceStateMachine()
    with pytest.raises(InvalidTransition):
        machine.transition(VoiceState.SPEAKING)


def test_force_idle_from_any_state() -> None:
    machine = VoiceStateMachine()
    machine.transition(VoiceState.WAKEUP)
    machine.transition(VoiceState.LISTENING)
    assert machine.force_idle("device_lost") is VoiceState.IDLE
    assert machine.history[-1][2] == "device_lost"


def test_reset_clears_history() -> None:
    machine = VoiceStateMachine()
    machine.transition(VoiceState.WAKEUP)
    machine.reset()
    assert machine.state is VoiceState.IDLE
    assert machine.history == ()


def test_avatar_agent_work_beats_idle_voice() -> None:
    assert derive_avatar_state(VoiceState.IDLE, AgentState.TOOL_RUNNING) is AvatarState.WORKING
    assert derive_avatar_state(VoiceState.IDLE, AgentState.THINKING) is AvatarState.THINKING


def test_avatar_confirmation_and_error_precedence() -> None:
    assert (
        derive_avatar_state(VoiceState.SPEAKING, AgentState.WAITING_CONFIRMATION)
        is AvatarState.CONFIRMATION
    )
    assert derive_avatar_state(VoiceState.SPEAKING, AgentState.ERROR) is AvatarState.ERROR
    assert derive_avatar_state(VoiceState.SPEAKING, AgentState.IDLE) is AvatarState.SPEAKING


def test_avatar_listening_and_success() -> None:
    assert derive_avatar_state(VoiceState.LISTENING) is AvatarState.LISTENING
    assert derive_avatar_state(VoiceState.IDLE, AgentState.SUCCESS) is AvatarState.SUCCESS
