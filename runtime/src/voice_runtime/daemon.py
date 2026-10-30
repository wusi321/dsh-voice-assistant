"""CLI entry point: doctor, probe, daemon."""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import logging
import signal
import sys
from pathlib import Path
from typing import Any

from voice_runtime import __version__
from voice_runtime.audio.audio_io import AudioIO
from voice_runtime.audio.device_manager import probe as probe_devices
from voice_runtime.config.schema import RuntimeConfig, config_json_schema, load_config
from voice_runtime.engines.fake import FakeTTSEngine
from voice_runtime.engines.models import SherpaModels, default_model_root
from voice_runtime.engines.sherpa_tts import SherpaTTS
from voice_runtime.runtime.supervisor import RuntimeSupervisor
from voice_runtime.utils.logging import configure_logging
from voice_runtime.utils.platform import data_dir, ensure_dir, is_linux, is_windows
from voice_runtime.voice_service import NullAudio, RuntimeVoiceService

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _check(name: str, ok: bool, detail: str, *, required: bool = True) -> dict[str, Any]:
    return {"name": name, "ok": ok, "detail": detail, "required": required}


def run_doctor(config: RuntimeConfig, *, as_json: bool) -> int:
    checks: list[dict[str, Any]] = []
    python_ok = sys.version_info >= (3, 11)
    checks.append(
        _check(
            "python",
            python_ok,
            f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        )
    )
    checks.append(
        _check(
            "platform",
            True,
            "windows" if is_windows() else "linux" if is_linux() else sys.platform,
            required=False,
        )
    )
    checks.append(
        _check(
            "protocol",
            config.protocol_version >= 1,
            f"protocol version {config.protocol_version}",
        )
    )

    root = config.resolved_data_dir(data_dir())
    try:
        ensure_dir(root)
        probe_file = root / ".doctor-write-test"
        probe_file.write_text("ok", encoding="utf-8")
        probe_file.unlink()
        checks.append(_check("data_dir", True, str(root)))
    except OSError as exc:
        checks.append(_check("data_dir", False, f"{root}: {exc}"))

    manifest = PROJECT_ROOT / "models" / "manifest.json"
    if manifest.exists():
        try:
            json.loads(manifest.read_text(encoding="utf-8"))
            checks.append(_check("models_manifest", True, str(manifest)))
        except (OSError, ValueError) as exc:
            checks.append(_check("models_manifest", False, str(exc)))
    else:
        checks.append(
            _check("models_manifest", False, "models/manifest.json not found", required=False)
        )

    for module, required in (("sherpa_onnx", False), ("sounddevice", False), ("livekit", False)):
        checks.append(
            _check(
                f"dependency:{module}",
                importlib.util.find_spec(module) is not None,
                "installed" if importlib.util.find_spec(module) else "not installed (P2/P3)",
                required=required,
            )
        )

    devices = probe_devices()
    checks.append(
        _check(
            "audio_devices",
            devices.available,
            devices.reason or f"{len(devices.inputs)} input / {len(devices.outputs)} output",
            required=False,
        )
    )

    required_ok = all(check["ok"] for check in checks if check["required"])
    payload = {"ok": required_ok, "version": __version__, "checks": checks}
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"dsh-voice-runtime {__version__}")
        for check in checks:
            marker = "OK" if check["ok"] else "WARN" if not check["required"] else "FAIL"
            print(f"[{marker}] {check['name']}: {check['detail']}")
        print("doctor:", "ok" if required_ok else "failed")
    return 0 if required_ok else 1


def run_probe(*, as_json: bool) -> int:
    devices = probe_devices()
    payload = devices.to_dict()
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"available: {payload['available']} ({payload['reason'] or 'ok'})")
        print(f"default input: {payload['default_input']}  output: {payload['default_output']}")
        for device in payload["inputs"]:
            print(
                f"  input  [{device['index']}] {device['name']} @ {device['default_samplerate']} Hz"
            )
        for device in payload["outputs"]:
            print(
                f"  output [{device['index']}] {device['name']} @ {device['default_samplerate']} Hz"
            )
    return 0 if devices.available else 1


def _install_signal_handlers(loop: asyncio.AbstractEventLoop, event: asyncio.Event) -> None:
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, event.set)
        except (NotImplementedError, RuntimeError):
            try:
                signal.signal(sig, lambda *_: loop.call_soon_threadsafe(event.set))
            except (ValueError, OSError):
                continue


def _build_voice_service(config: RuntimeConfig, mode: str) -> RuntimeVoiceService | None:
    if mode == "off":
        return None
    if mode == "fake":
        return RuntimeVoiceService(tts=FakeTTSEngine(), audio=NullAudio())
    models = SherpaModels.discover(config.engines.model_dir or default_model_root())
    tts = SherpaTTS(models.tts_dir, kind=models.tts_kind)
    audio = AudioIO(
        input_device=config.audio.input_device,
        output_device=config.audio.output_device,
        preferred_input_rate=config.audio.preferred_sample_rate,
        preferred_output_rate=config.audio.preferred_sample_rate,
        block_ms=config.audio.block_ms,
        aec_enabled=config.audio.aec_enabled,
        echo_delay_ms=config.audio.echo_delay_ms,
    )
    return RuntimeVoiceService(tts=tts, audio=audio)


async def _serve(config: RuntimeConfig, voice_mode: str = "off") -> int:
    service = _build_voice_service(config, voice_mode)
    supervisor = RuntimeSupervisor(config, voice_service=service)
    info = await supervisor.start()
    print(
        json.dumps(
            {
                "ok": True,
                "port": info.port,
                "pid": info.pid,
                "discovery": str(supervisor.discovery_path),
                "protocolVersion": info.protocol_version,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    loop = asyncio.get_running_loop()
    _install_signal_handlers(loop, supervisor.server.shutdown_event)
    try:
        await supervisor.wait_for_shutdown()
    finally:
        await supervisor.stop()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="voice-runtime", description="DSH Voice Runtime")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser(
        "doctor", help="check Python, config, model manifest, and audio devices"
    )
    doctor.add_argument("--config", type=Path, default=None)
    doctor.add_argument("--json", action="store_true")

    probe = sub.add_parser("probe", help="list audio input/output devices")
    probe.add_argument("--json", action="store_true")

    daemon = sub.add_parser("daemon", help="start the localhost WebSocket runtime")
    daemon.add_argument("--config", type=Path, default=None)
    daemon.add_argument("--host", default=None)
    daemon.add_argument("--port", type=int, default=None)
    daemon.add_argument("--data-dir", type=Path, default=None)
    daemon.add_argument("--fake-audio", action="store_true")
    daemon.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], default=None)
    daemon.add_argument("--json-logs", action="store_true")
    daemon.add_argument(
        "--voice",
        choices=["off", "fake", "real"],
        default="off",
        help="TTS output mode: off, fake (no devices), real (models + audio)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "doctor":
        config = load_config(args.config)
        return run_doctor(config, as_json=args.json)
    if args.command == "probe":
        return run_probe(as_json=args.json)

    config = load_config(args.config)
    updates: dict[str, Any] = {}
    if args.host is not None:
        updates["host"] = args.host
    if args.port is not None:
        updates["port"] = args.port
    if args.data_dir is not None:
        updates["data_dir"] = args.data_dir
    if args.fake_audio:
        updates["fake_audio"] = True
    if args.log_level is not None:
        updates["log_level"] = args.log_level
    if args.json_logs:
        updates["json_logs"] = True
    if updates:
        config = RuntimeConfig(**{**config.model_dump(), **updates})

    configure_logging(config.log_level, json_output=config.json_logs)
    try:
        return asyncio.run(_serve(config, args.voice))
    except KeyboardInterrupt:
        return 130


def cli() -> None:
    raise SystemExit(main())


def config_schema_command() -> None:
    """Print the config JSON Schema; used by scripts and CI."""
    print(json.dumps(config_json_schema(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
