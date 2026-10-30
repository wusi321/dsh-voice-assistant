# Protocol

Version: **1**. Runtime binds to `127.0.0.1` only. The DSH plugin is the client.

## Discovery

The Runtime writes a JSON file with owner-only permissions:

```json
{
  "pid": 1234,
  "host": "127.0.0.1",
  "port": 49152,
  "token": "<32-byte urlsafe token>",
  "runtimeVersion": "0.1.0",
  "protocolVersion": 1,
  "startedAt": "2026-10-30T00:00:00+00:00"
}
```

Default paths:

- Windows: `%LOCALAPPDATA%\dsh-voice-assistant\runtime.json`
- Linux: `$XDG_DATA_HOME/dsh-voice-assistant/runtime.json` or `~/.local/share/dsh-voice-assistant/runtime.json`
- macOS: `~/Library/Application Support/dsh-voice-assistant/runtime.json`

The plugin must reject a discovery file whose host is not `127.0.0.1`, whose
port is invalid, whose token is too short, or whose PID is not alive.

## Authentication

The first WebSocket message is always JSON:

```json
{
  "type": "auth",
  "version": 1,
  "token": "<discovery token>",
  "clientId": "dsh-voice-assistant",
  "protocolVersion": 1
}
```

The server replies `auth.ok` then `runtime.ready`, or `auth.error` and closes
with code `4001`. Tokens are compared in constant time and never appear in logs
or URLs.

## JSON control event

```ts
interface VoiceEvent<T> {
  version: 1;
  id: string;          // unique message id
  sessionId: string;   // bound DSH session, or "runtime" for runtime events
  sequence: number;    // per-session monotonic counter
  timestamp: number;   // Unix epoch milliseconds
  type: string;
  payload: T;
}
```

### Runtime → Plugin

`runtime.ready`, `runtime.error`, `wake.detected`, `speech.started`,
`speech.partial`, `speech.final`, `tts.started`, `tts.finished`,
`tts.interrupted`, `device.changed`, `session.state_changed`, `runtime.health`,
`pong`.

### Plugin → Runtime

`listen.start`, `listen.stop`, `listen.cancel`, `tts.speak`, `tts.cancel`,
`session.interrupt`, `config.update`, `runtime.shutdown`, `ping`.

`ping` must be answered with `pong` carrying the same `pingId`. The server also
uses WebSocket protocol ping/pong as a transport keepalive.

## Binary PCM frame

Binary messages carry audio; they are never Base64 JSON. Header is 28 bytes,
little-endian.

| Offset | Size | Field | Notes |
|---|---|---|---|
| 0 | 4 | magic | ASCII `VAP1` |
| 4 | 1 | version | `1` |
| 5 | 1 | flags | bit 0 = discontinuity, bit 1 = final |
| 6 | 2 | headerLength | `28` |
| 8 | 4 | sequence | uint32 |
| 12 | 4 | timestampMs | uint32, session-relative |
| 16 | 4 | sampleRate | 8000–192000 |
| 20 | 2 | channels | 1 or 2 |
| 22 | 1 | format | `1` = PCM16LE |
| 23 | 1 | reserved | `0` |
| 24 | 4 | frameCount | samples per channel, 1–48000 |
| 28 | n | payload | interleaved PCM16LE |

`n = frameCount * channels * 2`. A frame with a bad magic, version, format,
length, or count is rejected with a non-fatal `runtime.error` (`invalid_message`).

## Session and sequencing

- The Runtime's own events use `sessionId: "runtime"` until a DSH session is
  bound; plugin commands carry the bound DSH `sessionId`.
- `sequence` starts at 1 for each sender/session. The receiver may detect gaps;
  P1 does not retransmit. A reconnect creates a new transport, not a new
  sequence space.
- Reconnect is exponential backoff (500 ms → 15 s by default) with jitter
  reserved for P4.
- `runtime.shutdown` is a graceful request; the Runtime removes the discovery
  file before exit.

## State machine

Voice states: `IDLE`, `WAKEUP`, `LISTENING`, `TRANSCRIBING`, `DISPATCHING`,
`THINKING`, `SPEAKING`, `INTERRUPTING`, `CONFIRMATION`, `ERROR`. The allowed
transition table is in `runtime/src/voice_runtime/session/state_machine.py`.
Illegal transitions throw `InvalidTransition`; global cancel/device loss may
force `IDLE` with a history entry.

TTS interruption and Agent cancellation are distinct protocol actions:
`tts.cancel` stops playback; `session.interrupt` with `action: "agent"` asks the
plugin to cancel the DSH turn; `action: "steer"` asks it to steer instead.
