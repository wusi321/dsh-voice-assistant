# NOTICE

DSH Voice Assistant
Copyright 2026 DSH Voice Assistant contributors
Licensed under the Apache License, Version 2.0.

This product includes or interacts with third-party software and models. Each
component remains under its own license; the Apache-2.0 license of this project
does not relicense third-party components or model weights.

## Runtime and protocol dependencies

| Component | Use | License |
|---|---|---|
| Python | Runtime language | PSF-2.0 |
| Pydantic / pydantic-settings | Configuration and protocol models | MIT |
| platformdirs | Cross-platform directories | MIT |
| NumPy | Audio buffers and DSP | BSD-3-Clause |
| SciPy | Polyphase resampling | BSD-3-Clause |
| websockets | Runtime WebSocket transport | BSD-3-Clause |
| sherpa-onnx / sherpa-onnx-core | VAD / KWS / ASR / TTS runtime | Apache-2.0 |
| onnxruntime | Model inference runtime | MIT |
| sounddevice / PortAudio | Audio capture and playback | MIT |
| soundfile | WAV read/write in tests | BSD-3-Clause |
| livekit | WebRTC Audio Processing (AEC) | Apache-2.0 |

## Plugin and UI dependencies

| Component | Use | License |
|---|---|---|
| Node.js | Plugin runtime | MIT |
| TypeScript | Plugin language | Apache-2.0 |
| Zod | Protocol schemas | MIT |
| ws | Runtime WebSocket client | MIT |
| @deepseek-ai/schemastery | DSH plugin Config schema | MIT |
| DeepSeek Harness (DSH) | Host application and plugin API | MIT |
| dsh-pet (integration target, not bundled) | Avatar / animation / HTTP API | MIT |

## Models

Models are downloaded separately and are not distributed with this repository.
Each model carries its own license. The default allowlist is limited to models
with a verified permissive license; candidates whose license is unverified must
not be selected as defaults.

| Model | Task | Status |
|---|---|---|
| Silero VAD (`silero_vad.onnx`) | Voice activity detection | MIT; default candidate |
| Kokoro multi-lang v1.1 | TTS | Apache-2.0; candidate, not yet tested locally |
| sherpa-onnx KWS (WenetSpeech 3.3M) | Chinese wake word | Runtime Apache-2.0; weights unverified, local test only |
| sherpa-onnx streaming Zipformer zh 14M | Streaming ASR | Runtime Apache-2.0; weights unverified, local test only |
| vits-piper-zh_CN-huayan-medium | Chinese TTS (P3 test) | Piper model card; local test only |
| SenseVoice small | Optional second-pass ASR | FunASR model license; not a default |

Do not redistribute non-commercial or unverified model weights. See
`docs/ENGINE_ADAPTERS.md` and `models/manifest.json` for the current status.

## Upstream references

`GDDXX-Jarvis` is GPL-3.0 and is used only as a read-only behavioral reference.
No GPL code is copied into this project. `piper-tts` is GPL-3.0-or-later and is
not a default dependency. openWakeWord's pre-trained "hey jarvis" model is
CC BY-NC-SA 4.0 and is not distributed.
