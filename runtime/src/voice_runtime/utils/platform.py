"""Cross-platform application directories and private-file helpers."""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

import platformdirs

APP_NAME = "dsh-voice-assistant"
APP_AUTHOR = "dsh-voice-assistant"


def config_dir() -> Path:
    """Per-user configuration directory."""
    return Path(platformdirs.user_config_path(APP_NAME, APP_AUTHOR, roaming=False))


def data_dir() -> Path:
    """Per-user data directory (models, logs, runtime state)."""
    return Path(platformdirs.user_data_path(APP_NAME, APP_AUTHOR, roaming=False))


def runtime_dir() -> Path:
    """Directory holding the runtime discovery file."""
    return data_dir() / "runtime"


def ensure_dir(path: Path) -> Path:
    """Create a directory with owner-only permissions where the platform allows it."""
    path.mkdir(parents=True, exist_ok=True)
    restrict_permissions(path)
    return path


def restrict_permissions(path: Path) -> None:
    """Best-effort owner-only permissions for a file or directory.

    POSIX uses chmod. Windows uses icacls to remove inheritance and grant the
    current user full control. Failures are intentionally non-fatal: the runtime
    still binds to localhost, and the caller can surface a diagnostic.
    """
    if os.name == "nt":
        user = os.environ.get("USERNAME", "")
        if not user:
            return
        try:
            subprocess.run(
                ["icacls", str(path), "/inheritance:r", "/grant:r", f"{user}:(F)"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return
        return

    try:
        mode = path.stat().st_mode
        if path.is_dir():
            path.chmod(stat.S_IRWXU)
        else:
            path.chmod(mode & ~(stat.S_IRWXG | stat.S_IRWXO) | stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        return


def is_windows() -> bool:
    return sys.platform.startswith("win")


def is_linux() -> bool:
    return sys.platform.startswith("linux")


def is_macos() -> bool:
    return sys.platform == "darwin"
