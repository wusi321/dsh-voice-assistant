# Engine Adapters

All speech engines are replaceable adapters behind the interfaces in
`runtime/src/voice_runtime/engines/base.py`.

## Interfaces

| Adapter | Methods | Notes |
|---|---|---|
| `WakeEngine` | `initialize`, `detect(frame)`, `reset`, `shutdown` | returns the matched keyword or `None` |
| `VADEngine` | `initialize`, `process(frame)`, `reset`, `shutdown` | returns speech/non-speech; timestamps are added by the segmenter |
| `ASREngine` | `initialize`, `start_stream`, `accept_audio`, `get_partial_result`, `get_final_result`, `reset`, `shutdown` | streaming; partial text is required |
| `TTSEngine` | `initialize`, `synthesize_stream(text)`, `cancel`, `shutdown` | yields float32 mono chunks at the engine sample rate |
| `AECProcessor` | `initialize`, `process(mic, reference)`, `reset`, `shutdown` | reference is the exact playback signal |

`EngineManager` registers exactly one adapter per kind, initializes all, exposes
health, and shuts down safely. The Session Manager never imports an engine SDK.

## Planned implementations (P2/P3)

| Adapter | Candidate | License status |
|---|---|---|
| VAD | sherpa-onnx Silero VAD | MIT; verified |
| Wake | sherpa-onnx KWS (WenetSpeech / GigaSpeech) | runtime Apache-2.0; weights to verify |
| ASR | sherpa-onnx streaming Zipformer (bilingual zh-en) | runtime Apache-2.0; weights to verify |
| TTS | sherpa-onnx Kokoro multi-lang v1.1 | Apache-2.0; verified |
| AEC | livekit WebRTC Audio Processing Module | Apache-2.0; Windows APM to verify |
| Optional second-pass ASR | SenseVoice small | FunASR model license; not a default |

P1 ships deterministic fakes only (`engines/fake.py`) so protocol, state, and UI
tests run without models or audio hardware.

## Model manifest rules

`models/manifest.json` entries must include `model_id`, `engine`, `task`,
`language`, `version`, `download_url`, `sha256`, `size`, `license`,
`license_url`, `commercial_use`, `redistributable`, `supported_platforms`,
`sample_rate`, `capabilities`, and `verified`.

- `verified: true` requires a SHA256 and size; `scripts/download_models.py` will
  download and verify it.
- `candidates` may have `sha256: null` and are never auto-downloaded.
- The downloader writes to a temporary file, verifies SHA256/size, then atomically
  renames. Non-commercial entries require `--accept-license`.

## Adding an adapter

1. Implement the interface in a new module; do not import it from the Session
   Manager.
2. Add a fake/mocked unit test and a real-model smoke test that is skipped when
   the model is absent.
3. Register the adapter in `EngineManager` behind configuration.
4. Record the dependency and model license in `NOTICE.md` and the manifest.
5. Add Windows and Ubuntu notes to `WINDOWS.md` / `LINUX.md`.
