# dsh-voice-runtime

Python voice runtime for DSH Voice Assistant. It runs independently from DSH
and exposes a localhost-only WebSocket control channel plus binary PCM frames.

Implemented in P2-P4:

- device enumeration/selection, separate capture/playback streams, bounded
  buffers, streaming resampling, software-reference WebRTC AEC;
- sherpa-onnx VAD, Chinese KWS, streaming Zipformer ASR, VITS/Piper TTS;
- versioned JSON events, PCM frames, token auth, heartbeat, timeouts, reconnect.

```bash
uv sync --extra full
uv run voice-runtime probe --json
uv run voice-runtime doctor
uv run voice-runtime daemon --fake-audio
uv run pytest
```

Real-model e2e tests require `sherpa-onnx` and models at
`DSH_VOICE_TEST_MODELS` (default `D:/dsh-voice-models`); without them the tests
skip. See `../docs/P2_REPORT.md`, `P3_REPORT.md`, `P4_REPORT.md`.
