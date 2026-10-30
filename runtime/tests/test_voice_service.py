from collections.abc import AsyncIterator

import numpy as np

from voice_runtime.engines.base import TTSEngine
from voice_runtime.transport.protocol import VoiceEvent
from voice_runtime.voice_service import RuntimeVoiceService


class FakeTTS(TTSEngine):
    sample_rate = 24_000

    def __init__(self) -> None:
        super().__init__("fake-tts")
        self.cancelled = False

    async def synthesize_stream(self, text: str) -> AsyncIterator[np.ndarray]:
        for _ in range(max(1, len(text))):
            if self.cancelled:
                return
            yield np.ones(240, dtype=np.float32)

    async def cancel(self) -> None:
        self.cancelled = True


class FakeAudio:
    def __init__(self) -> None:
        self.played: list[tuple[str, int, int]] = []
        self.cancelled: list[str | None] = []

    def play(self, samples: np.ndarray, *, utterance_id: str, sample_rate: int) -> None:
        self.played.append((utterance_id, samples.size, sample_rate))

    def cancel_playback(self, utterance_id: str | None = None) -> int:
        self.cancelled.append(utterance_id)
        return 1


def event(event_type: str, payload: dict[str, object]) -> VoiceEvent:
    return VoiceEvent(
        id="e1",
        sessionId="s1",
        sequence=1,
        timestamp=1,
        type=event_type,  # type: ignore[arg-type]
        payload=payload,
    )


async def test_speaks_text_and_emits_started_finished() -> None:
    tts = FakeTTS()
    audio = FakeAudio()
    emitted: list[tuple[str, dict[str, object]]] = []

    async def emit(name: str, payload: dict[str, object]) -> None:
        emitted.append((name, payload))

    service = RuntimeVoiceService(tts=tts, audio=audio)
    service.set_emitter(emit)
    await service.start()
    await service.handle_event(
        event("tts.speak", {"utteranceId": "u1", "text": "你好", "interruptible": True})
    )
    await service.stop()
    assert [name for name, _ in emitted] == ["tts.started", "tts.finished"]
    assert audio.played and audio.played[0][0] == "u1"
    assert audio.played[0][2] == 24_000


async def test_missing_tts_reports_engine_unavailable() -> None:
    emitted: list[tuple[str, dict[str, object]]] = []

    async def emit(name: str, payload: dict[str, object]) -> None:
        emitted.append((name, payload))

    service = RuntimeVoiceService(tts=None, audio=FakeAudio())
    service.set_emitter(emit)
    await service.handle_event(event("tts.speak", {"utteranceId": "u1", "text": "你好"}))
    assert emitted[0][0] == "runtime.error"
    assert emitted[0][1]["code"] == "engine_unavailable"


async def test_invalid_speak_payload_is_rejected() -> None:
    emitted: list[tuple[str, dict[str, object]]] = []

    async def emit(name: str, payload: dict[str, object]) -> None:
        emitted.append((name, payload))

    service = RuntimeVoiceService(tts=FakeTTS(), audio=FakeAudio())
    service.set_emitter(emit)
    await service.handle_event(event("tts.speak", {"utteranceId": "u1", "text": " "}))
    assert emitted[0][0] == "runtime.error"
    assert emitted[0][1]["code"] == "invalid_message"


async def test_cancel_interrupts_active_playback() -> None:
    tts = FakeTTS()
    audio = FakeAudio()
    emitted: list[str] = []

    async def emit(name: str, payload: dict[str, object]) -> None:
        _ = payload
        emitted.append(name)

    service = RuntimeVoiceService(tts=tts, audio=audio)
    service.set_emitter(emit)
    await service.handle_event(event("tts.speak", {"utteranceId": "u1", "text": "你好"}))
    await service.handle_event(event("tts.cancel", {"utteranceId": "u1", "reason": "barge_in"}))
    assert "tts.cancelled" not in emitted
    assert tts.cancelled is True
