# Architecture

DSH Voice Assistant is split into three independently runnable pieces:

```text
┌──────────────────────────── DSH Host (Node.js) ────────────────────────────┐
│  dsh-voice-assistant plugin (Host half)                                    │
│    RuntimeManager ── spawn / discovery / reconnect                         │
│    RuntimeClient  ── authenticated WebSocket                               │
│    status route   ── GET /dsh-voice-assistant/status                       │
│                                                                            │
│  DSH Client page (browser)                                                 │
│    settings.section page ── polls the read-only status route               │
└───────────────────────────────┬────────────────────────────────────────────┘
                                │ localhost WebSocket + binary PCM
┌───────────────────────────────▼────────────────────────────────────────────┐
│ Python Voice Runtime (independent process)                                 │
│  daemon → supervisor → WebSocket server                                    │
│  SessionManager / VoiceStateMachine                                        │
│  AudioRingBuffer / StreamingResampler / DeviceManager (P1)                 │
│  EngineManager: Wake / VAD / ASR / TTS / AEC adapters (P2/P3)              │
└───────────────────────────────┬────────────────────────────────────────────┘
                                │ HTTP (pet API) / Cordis (optional)
┌───────────────────────────────▼────────────────────────────────────────────┐
│ dsh-pet (MIT, optional)                                                    │
│  /state, /work-status, /anim, /lock, /broadcast, /playback                 │
└────────────────────────────────────────────────────────────────────────────┘
```

## Hard boundaries

1. **DSH is the only Agent execution core.** The Runtime never calls an LLM and
   never creates a second Agent. The plugin maps voice text to
   `agent.followup()`/`agent.steer()`.
2. **Voice Runtime is independent of DSH.** It can start, authenticate, and
   health-check with no DSH process. P1 proves this with `--fake-audio`.
3. **Voice, Agent, and Avatar states are separate.**
   - VoiceState is owned by the Runtime state machine.
   - AgentState is derived by the plugin from DSH Session/Agent events.
   - AvatarState is a projection; it never overwrites AgentState.
4. **One playback authority.** Only the Runtime writes to the speaker. dsh-pet
   is display-only by default. Its TTS Provider registration is an optional,
   mutually exclusive mode.
5. **All speech engines are adapters.** The Session Manager does not import
   sherpa-onnx, livekit, or sounddevice. `EngineManager` owns the adapters.

## P1 status

Implemented:

- Monorepo, strict TypeScript, Ruff/mypy/pytest, Vitest, Windows/Ubuntu CI.
- Versioned JSON control events and binary PCM frame codec.
- Runtime daemon: config, discovery file, token auth, WebSocket handshake,
  heartbeat (`ping`/`pong`), graceful shutdown, status/health skeleton.
- Audio ring buffer and streaming resampler.
- Voice state machine and Avatar projection.
- Engine interfaces and deterministic fakes.
- DSH plugin host: Runtime spawn/attach, reconnect, read-only status route.
- DSH client: settings section with Runtime status.

Not implemented (P2+): microphone capture, speaker playback, real VAD/KWS/ASR/
TTS/AEC, Agent bridge, barge-in, dsh-pet bridge, packaging.

## Process and concurrency model (planned)

- The Runtime is one asyncio process. PortAudio callbacks only copy samples into
  a bounded ring buffer; no model inference or blocking I/O runs in a callback.
- ASR/TTS engines may use worker threads/processes; the interface is async and
  cancellation is explicit.
- The DSH plugin host is one Node event loop. It owns one RuntimeClient and
  reconnects with exponential backoff.
- The DSH client page only polls non-sensitive status; it never receives audio.
