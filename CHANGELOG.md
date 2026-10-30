# Changelog

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
