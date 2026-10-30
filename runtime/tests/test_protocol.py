import pytest

from voice_runtime.transport.protocol import (
    PcmFrame,
    ProtocolError,
    make_event,
    parse_event,
)

KNOWN_FRAME_HEX = "5641503101001c0007000000d2040000803e00000100000100040000000102030405060708"


def test_known_frame_matches_typescript_wire_format() -> None:
    encoded = bytes.fromhex(KNOWN_FRAME_HEX)
    frame = PcmFrame.decode(encoded)
    assert frame.sequence == 7
    assert frame.timestamp_ms == 1234
    assert frame.sample_rate == 16000
    assert frame.channels == 1
    assert frame.data == bytes(range(1, 9))
    assert PcmFrame(
        sequence=7,
        timestamp_ms=1234,
        sample_rate=16000,
        channels=1,
        data=bytes(range(1, 9)),
    ).encode() == encoded


def test_frame_flags_round_trip() -> None:
    frame = PcmFrame(
        sequence=1,
        timestamp_ms=2,
        sample_rate=24000,
        channels=2,
        data=b"\x00\x01\x02\x03\x04\x05\x06\x07",
        discontinuity=True,
        final=True,
    )
    decoded = PcmFrame.decode(frame.encode())
    assert decoded.discontinuity is True
    assert decoded.final is True
    assert decoded.channels == 2


def test_frame_rejects_bad_magic() -> None:
    encoded = bytearray(bytes.fromhex(KNOWN_FRAME_HEX))
    encoded[0] = 0
    with pytest.raises(ProtocolError, match="magic"):
        PcmFrame.decode(bytes(encoded))


def test_frame_rejects_header_count_mismatch() -> None:
    encoded = bytearray(bytes.fromhex(KNOWN_FRAME_HEX))
    encoded[24] = 3
    with pytest.raises(ProtocolError, match="frameCount"):
        PcmFrame.decode(bytes(encoded))


def test_event_round_trip() -> None:
    event = make_event(
        "ping",
        {"pingId": "p1"},
        session_id="s1",
        sequence=3,
        event_id="e1",
        timestamp=10,
    )
    parsed = parse_event(event)
    assert parsed.type == "ping"
    assert parsed.payload["pingId"] == "p1"
    assert parsed.sequence == 3


def test_event_rejects_unknown_type() -> None:
    with pytest.raises(ProtocolError):
        parse_event(
            {
                "version": 1,
                "id": "e1",
                "sessionId": "s1",
                "sequence": 1,
                "timestamp": 1,
                "type": "does.not.exist",
                "payload": {},
            }
        )


def test_event_rejects_negative_sequence() -> None:
    with pytest.raises(ProtocolError):
        parse_event(
            {
                "version": 1,
                "id": "e1",
                "sessionId": "s1",
                "sequence": -1,
                "timestamp": 1,
                "type": "ping",
                "payload": {"pingId": "p1"},
            }
        )
