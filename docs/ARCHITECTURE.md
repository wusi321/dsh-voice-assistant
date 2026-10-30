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

## Status (P2–P4)

- P2 audio: device enumeration/selection, separate capture and playback streams,
  bounded buffers, streaming resampling, software-reference WebRTC AEC, device
  switching, restart-on-error, mock backend tests.
- P3 engines: sherpa-onnx VAD, Chinese KWS, streaming Zipformer ASR, VITS/Piper
  TTS; real local end-to-end tests for TTS, VAD → ASR, and KWS.
- P4 transport: versioned JSON events, binary PCM frames, token auth, heartbeat,
  idle/auth/connect timeouts, exponential-backoff reconnect, event tests.
- P1 scaffold and DSH plugin skeleton remain.

Not implemented: DSH Agent bridge and live settings/mic UI (P5), dsh-pet bridge
(P6), full-duplex barge-in (P7), permission confirmation (P8), packaging (P9).

## Audio path

```text
mic (device rate) → CaptureStream ring → StreamingResampler → 16 kHz
  → WebRTCAEC(mic, reference) → clean ring / on_capture
speaker (device rate) ← PlaybackStream ← PlaybackScheduler ← resampled TTS
  └─ reference callback → StreamingResampler → 16 kHz reference ring
```

- `PlaybackScheduler` is the only writer to the speaker; `AudioIO` is the only
  owner of capture/playback streams.
- AEC reference is the exact speaker signal, not WASAPI loopback.
- `AudioIO.restart()` and `switch_devices()` close and reopen both streams; the
  caller decides when to retry.
- Engine adapters are synchronous native calls wrapped by async interfaces;
  TTS generation runs in `asyncio.to_thread` and yields chunks.

## Process and concurrency model

- The Runtime is one asyncio process. PortAudio callbacks only copy samples into
  bounded ring buffers; no model inference or blocking I/O runs in a callback.
- VAD/ASR/TTS run in the Runtime process; TTS generation uses a worker thread.
- The DSH plugin host is one Node event loop. It owns one RuntimeClient,
  sends application heartbeats, and reconnects with exponential backoff.
- The DSH client page only polls non-sensitive status; it never receives audio.
