"""Runtime discovery file: port, token, PID, and version."""

from __future__ import annotations

import ctypes
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from voice_runtime.utils.platform import ensure_dir, restrict_permissions

DISCOVERY_FILENAME = "runtime.json"


@dataclass(frozen=True)
class DiscoveryInfo:
    """Everything a local client needs to connect to a running Runtime."""

    pid: int
    host: str
    port: int
    token: str
    runtime_version: str
    protocol_version: int
    started_at: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> DiscoveryInfo:
        required = {
            "pid": int,
            "host": str,
            "port": int,
            "token": str,
            "runtime_version": str,
            "protocol_version": int,
            "started_at": str,
        }
        kwargs: dict[str, object] = {}
        for key, expected in required.items():
            raw = value.get(key)
            if raw is None:
                raise ValueError(f"discovery file missing {key}")
            if not isinstance(raw, expected):
                raise ValueError(f"discovery field {key} has wrong type")
            kwargs[key] = raw
        return cls(**kwargs)  # type: ignore[arg-type]


def discovery_path(data_root: Path) -> Path:
    return data_root / DISCOVERY_FILENAME


def write_discovery(path: Path, info: DiscoveryInfo) -> None:
    """Atomically write the discovery file with owner-only permissions."""
    ensure_dir(path.parent)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(info.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    restrict_permissions(tmp)
    os.replace(tmp, path)
    restrict_permissions(path)


def read_discovery(path: Path) -> DiscoveryInfo:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except (OSError, ValueError) as exc:
        raise ValueError(f"cannot read discovery file: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError("discovery file must contain a JSON object")
    return DiscoveryInfo.from_dict(raw)


def remove_discovery(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return


def process_alive(pid: int) -> bool:
    """Check liveness without sending a signal (safe on Windows)."""
    if pid <= 0:
        return False
    if sys.platform.startswith("win"):
        process_query_limited_information = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(process_query_limited_information, False, pid)
        if not handle:
            return False
        try:
            return True
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def live_discovery(path: Path) -> DiscoveryInfo | None:
    """Read a discovery file and return it only when its process is alive."""
    try:
        info = read_discovery(path)
    except (FileNotFoundError, ValueError):
        return None
    return info if process_alive(info.pid) else None
