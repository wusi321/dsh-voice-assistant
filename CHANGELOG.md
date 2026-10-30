# Changelog

## [0.3.0] - 2026-10-30

### Added

- P5 DSH plugin integration: `SessionBinder` (client-reported active session, fixed, last), `DshAgentBridge` (`followup`/`steer`/`cancel`/`whenIdle`), assistant-stream sentence segmentation, `session/event` tool status, and TTS output through the Runtime.
- Client `conversation.composer.dock` session reporter and richer settings status (session, Agent state, tool, TTS).
- Runtime `RuntimeVoiceService` and `--voice off|fake|real`; TTS `tts.speak`/`tts.cancel` over the versioned WebSocket protocol.
- Tests for AgentBridge, SessionBinder, sentence sanitization, TTS output, HTTP session route, and real TTS via WebSocket.

### Notes

- Live DSH installation/session verification remains; AgentBridge is tested with the verified stable API and Mock agents.
- dsh-pet bridge, full-duplex barge-in, and permission confirmation remain P6-P8.

## [0.2.0] - 2026-10-30

### Added

- P2 audio system: injectable PortAudio backend, device enumeration/selection, separate capture and playback streams, bounded ring buffers, streaming resampling, software-reference WebRTC AEC, device switching, restart-on-error.
- P3 sherpa-onnx adapters: Silero VAD, Chinese KWS, streaming Zipformer ASR with partials, VITS/Piper TTS (Kokoro config path). Real local-model e2e tests for TTS, VAD→ASR, and KWS.
- P4 transport hardening: payload validation, application heartbeat, idle/auth/connect timeouts, exponential reconnect, binary frame delivery, heartbeat/reconnect tests.
- `models/manifest.json` candidates for local P2/P3 test models with hashes and license status.

### Notes

- Windows real-device capture/playback verified; Ubuntu hardware verification remains.
- Kokoro is not downloaded or tested yet; VITS/Piper is used for P3 TTS e2e.
- KWS/ASR weight licenses remain unverified and are not auto-downloaded.

## [0.1.0] - 2026-10-30

### Added

- P1 monorepo scaffold: pnpm workspace, uv Python project, TypeScript and Python quality gates.
- `@dsh-voice/protocol`: versioned event envelope, error codes, and binary PCM frame codec.
- `voice-runtime` daemon skeleton: config, discovery file, token authentication, WebSocket handshake and heartbeat, audio buffer/resampler, state-machine skeleton.
- `dsh-voice-assistant` DSH plugin skeleton: Host RuntimeManager/RuntimeClient and Client settings section.
- Windows/Ubuntu CI workflow and initial architecture, protocol, security, engine-adapter, platform, and roadmap docs.

### Notes

- No real wake/VAD/ASR/TTS engine is implemented in P1. Engine adapters are interfaces and fakes only.
- No model is downloaded by CI or by default.
