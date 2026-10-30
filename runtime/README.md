# dsh-voice-runtime

Python voice runtime for DSH Voice Assistant. It runs independently from DSH
and exposes a localhost-only WebSocket control channel plus binary PCM frames.

P1 implements the process, configuration, discovery, authentication, transport,
audio-buffer/resampler, and state-machine skeleton. Real wake/VAD/ASR/TTS/AEC
engines are P2/P3 work; the engine interfaces and fake implementations exist so
the protocol can be tested without audio hardware or models.

```bash
uv sync
uv run voice-runtime doctor
uv run voice-runtime daemon --fake-audio
uv run pytest
```
