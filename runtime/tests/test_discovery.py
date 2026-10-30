import os
import stat
from dataclasses import replace

import pytest

from voice_runtime.transport.discovery import (
    DiscoveryInfo,
    discovery_path,
    live_discovery,
    process_alive,
    read_discovery,
    remove_discovery,
    write_discovery,
)


def info(token: str = "secret") -> DiscoveryInfo:
    return DiscoveryInfo(
        pid=os.getpid(),
        host="127.0.0.1",
        port=12345,
        token=token,
        runtime_version="0.1.0",
        protocol_version=1,
        started_at="2026-10-30T00:00:00+00:00",
    )


def test_write_read_and_remove(tmp_path) -> None:
    path = discovery_path(tmp_path)
    write_discovery(path, info())
    parsed = read_discovery(path)
    assert parsed.port == 12345
    assert parsed.token == "secret"
    remove_discovery(path)
    assert not path.exists()
    remove_discovery(path)


def test_discovery_file_is_owner_only(tmp_path) -> None:
    if os.name == "nt":
        pytest.skip("POSIX permission bits are not meaningful on Windows")
    path = discovery_path(tmp_path)
    write_discovery(path, info())
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_live_discovery_checks_process(tmp_path) -> None:
    path = discovery_path(tmp_path)
    write_discovery(path, info())
    assert live_discovery(path) is not None
    dead = replace(info(), pid=999_999)
    write_discovery(path, dead)
    assert live_discovery(path) is None


def test_process_alive_for_self() -> None:
    assert process_alive(os.getpid()) is True
    assert process_alive(-1) is False


def test_missing_discovery_returns_none(tmp_path) -> None:
    assert live_discovery(tmp_path / "missing.json") is None
