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

## Implemented adapters (P3)

| Adapter | Implementation | Status |
|---|---|---|
| VAD | `SherpaVAD` (Silero VAD, 512-sample windows) | tested on Windows |
| Wake | `SherpaKWS` (WenetSpeech 3.3M, configurable keywords) | tested on Windows |
| ASR | `SherpaASR` (streaming Zipformer zh 14M) | tested on Windows |
| TTS | `SherpaTTS` (VITS/Piper; Kokoro config path) | VITS tested; Kokoro not yet |
| AEC | `audio/aec.py` livekit WebRTC APM | 16k/10ms processing tested; real echo test pending |

P3 uses local models outside the repository; see `docs/P3_REPORT.md` for hashes
and license status. Deterministic fakes remain in `engines/fake.py` for tests and
`--fake-audio`.

## Planned implementations (P5+)

| Adapter | Candidate | License status |
|---|---|---|
| TTS default | sherpa-onnx Kokoro multi-lang v1.1 | Apache-2.0; pending local e2e |
| ASR bilingual | sherpa-onnx streaming Zipformer zh-en | weights to verify |
| Optional second-pass ASR | SenseVoice small | FunASR model license; not a default |
| Speaker verification | CAM++ | Apache-2.0; P6 optional |

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
