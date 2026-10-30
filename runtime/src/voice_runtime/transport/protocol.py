"""Python mirror of the TypeScript voice protocol.

This module intentionally keeps the payload as a JSON object. P1 validates the
envelope and event name; P4 will add one Pydantic payload model per event.
"""

from __future__ import annotations

import json
import struct
import time
import uuid
from dataclasses import dataclass
from typing import Any, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, ValidationError

PROTOCOL_VERSION = 1
VOICE_EVENT_VERSION = 1
PCM_FRAME_MAGIC = b"VAP1"
PCM_FRAME_HEADER_BYTES = 28
PCM_FORMAT_PCM16_LE = 1
MAX_FRAME_COUNT = 48_000

EventType = Literal[
    "runtime.ready",
    "runtime.error",
    "wake.detected",
    "speech.started",
    "speech.partial",
    "speech.final",
    "tts.started",
    "tts.finished",
    "tts.interrupted",
    "device.changed",
    "session.state_changed",
    "runtime.health",
    "pong",
    "listen.start",
    "listen.stop",
    "listen.cancel",
    "tts.speak",
    "tts.cancel",
    "session.interrupt",
    "config.update",
    "runtime.shutdown",
    "ping",
]
EVENT_TYPES: frozenset[str] = frozenset(get_args(EventType))


class ProtocolError(ValueError):
    """A malformed control message or binary frame."""


class VoiceEvent(BaseModel):
    """Versioned JSON control event."""

    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = VOICE_EVENT_VERSION
    id: str = Field(min_length=1, max_length=128)
    sessionId: str = Field(min_length=1)
    sequence: int = Field(ge=0)
    timestamp: int = Field(ge=0)
    type: EventType
    payload: dict[str, Any]


class AuthRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["auth"] = "auth"
    version: Literal[1] = VOICE_EVENT_VERSION
    token: str = Field(min_length=1, max_length=512)
    clientId: str = Field(min_length=1, max_length=128)
    protocolVersion: int = Field(gt=0)


class AuthOk(BaseModel):
    type: Literal["auth.ok"] = "auth.ok"
    protocolVersion: int
    runtimeVersion: str


class AuthErrorResponse(BaseModel):
    type: Literal["auth.error"] = "auth.error"
    code: Literal["auth_failed", "protocol_version_mismatch", "invalid_message"]
    message: str


def make_event(
    event_type: EventType,
    payload: dict[str, Any],
    *,
    session_id: str,
    sequence: int,
    event_id: str | None = None,
    timestamp: int | None = None,
) -> dict[str, Any]:
    """Build a validated event dict ready for `json.dumps`."""
    event = VoiceEvent(
        id=event_id or uuid.uuid4().hex,
        sessionId=session_id,
        sequence=sequence,
        timestamp=timestamp if timestamp is not None else int(time.time() * 1000),
        type=event_type,
        payload=payload,
    )
    return event.model_dump(mode="json")


def parse_event(raw: str | bytes | dict[str, Any]) -> VoiceEvent:
    """Parse an untrusted control message into a VoiceEvent."""
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    if isinstance(raw, str):
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ProtocolError(f"invalid JSON: {exc}") from exc
    else:
        value = raw
    try:
        return VoiceEvent.model_validate(value)
    except ValidationError as exc:
        raise ProtocolError(f"invalid event: {exc}") from exc


@dataclass(frozen=True)
class PcmFrame:
    """One binary PCM frame (28-byte header + interleaved PCM16LE)."""

    sequence: int
    timestamp_ms: int
    sample_rate: int
    channels: int
    data: bytes
    format: int = PCM_FORMAT_PCM16_LE
    discontinuity: bool = False
    final: bool = False

    @property
    def frame_count(self) -> int:
        return len(self.data) // (self.channels * 2)

    def encode(self) -> bytes:
        self.validate()
        flags = (1 if self.discontinuity else 0) | (2 if self.final else 0)
        header = struct.pack(
            "<4sBBHIIIHBBI",
            PCM_FRAME_MAGIC,
            1,
            flags,
            PCM_FRAME_HEADER_BYTES,
            self.sequence,
            self.timestamp_ms,
            self.sample_rate,
            self.channels,
            self.format,
            0,
            self.frame_count,
        )
        return header + self.data

    def validate(self) -> None:
        if not 0 <= self.sequence <= 0xFFFFFFFF:
            raise ProtocolError("sequence must be a uint32")
        if not 0 <= self.timestamp_ms <= 0xFFFFFFFF:
            raise ProtocolError("timestampMs must be a uint32")
        if not 8_000 <= self.sample_rate <= 192_000:
            raise ProtocolError("sampleRate must be 8000..192000")
        if self.channels not in (1, 2):
            raise ProtocolError("channels must be 1 or 2")
        if self.format != PCM_FORMAT_PCM16_LE:
            raise ProtocolError("unsupported sample format")
        payload_bytes = len(self.data)
        if payload_bytes <= 0 or payload_bytes % (self.channels * 2) != 0:
            raise ProtocolError("payload length is not aligned to PCM16 frames")
        if self.frame_count > MAX_FRAME_COUNT:
            raise ProtocolError("frameCount exceeds the protocol maximum")

    @classmethod
    def decode(cls, raw: bytes | bytearray | memoryview) -> PcmFrame:
        data = bytes(raw)
        if len(data) < PCM_FRAME_HEADER_BYTES:
            raise ProtocolError("frame is shorter than the header")
        (
            magic,
            version,
            flags,
            header_len,
            sequence,
            timestamp_ms,
            sample_rate,
            channels,
            fmt,
            _reserved,
            frame_count,
        ) = struct.unpack("<4sBBHIIIHBBI", data[:PCM_FRAME_HEADER_BYTES])
        if magic != PCM_FRAME_MAGIC:
            raise ProtocolError("bad frame magic")
        if version != 1:
            raise ProtocolError(f"unsupported frame version {version}")
        if header_len != PCM_FRAME_HEADER_BYTES:
            raise ProtocolError("unexpected header length")
        if fmt != PCM_FORMAT_PCM16_LE:
            raise ProtocolError("unsupported sample format")
        if channels not in (1, 2):
            raise ProtocolError("channels must be 1 or 2")
        payload_bytes = len(data) - PCM_FRAME_HEADER_BYTES
        if payload_bytes <= 0 or payload_bytes % (channels * 2) != 0:
            raise ProtocolError("payload length is not aligned to PCM16 frames")
        if frame_count != payload_bytes // (channels * 2):
            raise ProtocolError("header frameCount does not match payload")
        expected = PCM_FRAME_HEADER_BYTES + frame_count * channels * 2
        if len(data) != expected:
            raise ProtocolError(f"frame is {len(data)} bytes, expected {expected}")
        frame = cls(
            sequence=sequence,
            timestamp_ms=timestamp_ms,
            sample_rate=sample_rate,
            channels=channels,
            data=data[PCM_FRAME_HEADER_BYTES:],
            format=fmt,
            discontinuity=bool(flags & 1),
            final=bool(flags & 2),
        )
        frame.validate()
        return frame
