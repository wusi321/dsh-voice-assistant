"""Local model discovery and sherpa-onnx runtime preparation."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


class ModelUnavailable(RuntimeError):
    """A required local model directory or file is missing."""


def prepare_sherpa_runtime() -> None:
    """Make the pip-installed ONNX Runtime DLL visible to sherpa-onnx on Windows.

    sherpa-onnx links `onnxruntime.dll` by name. If another copy is earlier on
    the Windows search path, the native library loads an incompatible version.
    Adding the onnxruntime package's `capi` directory is the supported way to
    keep the versions aligned.
    """
    if not sys.platform.startswith("win"):
        return
    try:
        import onnxruntime  # type: ignore[import-untyped]

        capi = Path(onnxruntime.__file__).resolve().parent / "capi"
        if capi.is_dir():
            os.add_dll_directory(str(capi))
    except Exception:
        return


@dataclass(frozen=True)
class SherpaModels:
    """Resolved paths for the P3 local models."""

    root: Path
    vad_model: Path
    kws_dir: Path
    asr_dir: Path
    tts_dir: Path
    tts_kind: str

    @classmethod
    def discover(cls, root: Path) -> SherpaModels:
        root = root.expanduser().resolve()
        if not root.is_dir():
            raise ModelUnavailable(f"model root not found: {root}")
        vad = root / "silero_vad.onnx"
        if not vad.is_file():
            raise ModelUnavailable(f"VAD model not found: {vad}")
        kws = root / "sherpa-onnx-kws-zipformer-wenetspeech-3.3M-2024-01-01"
        asr = root / "sherpa-onnx-streaming-zipformer-zh-14M-2023-02-23"
        if not kws.is_dir():
            raise ModelUnavailable(f"KWS model not found: {kws}")
        if not asr.is_dir():
            raise ModelUnavailable(f"streaming ASR model not found: {asr}")

        kokoro = root / "kokoro-multi-lang-v1_1"
        vits = root / "vits-piper-zh_CN-huayan-medium"
        icefall = root / "vits-icefall-zh-aishell3"
        if kokoro.is_dir():
            tts_dir, tts_kind = kokoro, "kokoro"
        elif vits.is_dir():
            tts_dir, tts_kind = vits, "vits"
        elif icefall.is_dir():
            tts_dir, tts_kind = icefall, "vits"
        else:
            raise ModelUnavailable(f"no TTS model under {root}")
        return cls(root, vad, kws, asr, tts_dir, tts_kind)


def default_model_root() -> Path:
    """Environment override, then the platform data dir, then the workspace cache."""
    env = os.environ.get("DSH_VOICE_MODELS")
    if env:
        return Path(env).expanduser()
    from voice_runtime.utils.platform import data_dir

    candidate = data_dir() / "models"
    if candidate.is_dir():
        return candidate
    return Path.cwd() / ".cache" / "models"
