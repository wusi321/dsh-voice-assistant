#!/usr/bin/env python
"""Model manifest inspector and verified downloader.

P1 deliberately downloads nothing by default. Only entries with
`verified: true` and a SHA256 can be fetched; candidates are reported but
refused until their hash, size, and license are recorded.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "models" / "manifest.json"
SCHEMA_PATH = ROOT / "models" / "manifest.schema.json"
DEFAULT_MODELS_DIR = Path(
    os.environ.get("DSH_VOICE_MODELS", Path.home() / ".dsh-voice-assistant" / "models")
)


class ManifestError(RuntimeError):
    pass


def load_manifest() -> dict[str, Any]:
    raw = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ManifestError("manifest must be a JSON object")
    if raw.get("schemaVersion") != 1:
        raise ManifestError("unsupported manifest schemaVersion")
    try:
        import jsonschema
    except ImportError:
        jsonschema = None
    if jsonschema is not None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        jsonschema.validate(raw, schema)
    return raw


def all_entries(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return [*manifest.get("models", []), *manifest.get("candidates", [])]


def printable(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "model_id": entry.get("model_id"),
        "task": entry.get("task"),
        "license": entry.get("license"),
        "commercial_use": entry.get("commercial_use"),
        "verified": entry.get("verified", False),
        "sha256": entry.get("sha256"),
        "download_url": entry.get("download_url", []),
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def download(entry: dict[str, Any], target_dir: Path, *, accept_license: bool) -> Path:
    if not entry.get("verified") or not entry.get("sha256"):
        raise ManifestError(f"{entry['model_id']}: not verified; refusing download")
    if not entry.get("commercial_use") and not accept_license:
        raise ManifestError(f"{entry['model_id']}: non-commercial model requires --accept-license")
    urls = entry.get("download_url") or []
    if not urls:
        raise ManifestError(f"{entry['model_id']}: no download URL")
    target_dir.mkdir(parents=True, exist_ok=True)
    filename = Path(urllib.parse.urlparse(urls[0]).path).name
    if not filename:
        raise ManifestError(f"{entry['model_id']}: cannot derive a filename")
    target = target_dir / filename
    if (
        target.exists()
        and target.stat().st_size == entry["size"]
        and (sha256_file(target) == entry["sha256"])
    ):
        return target

    part = target.with_name(target.name + ".part")
    last_error: Exception | None = None
    for url in urls:
        try:
            _fetch(url, part, expected_size=int(entry["size"]))
            actual = sha256_file(part)
            if actual != entry["sha256"]:
                part.unlink(missing_ok=True)
                raise ManifestError(
                    f"{entry['model_id']}: sha256 mismatch "
                    f"(expected {entry['sha256']}, got {actual})"
                )
            os.replace(part, target)
            return target
        except (OSError, urllib.error.URLError, ManifestError) as exc:
            last_error = exc
            part.unlink(missing_ok=True)
    raise ManifestError(f"{entry['model_id']}: download failed: {last_error}")


def _fetch(url: str, part: Path, *, expected_size: int) -> None:
    have = part.stat().st_size if part.exists() else 0
    headers = {"User-Agent": "dsh-voice-assistant/0.1"}
    if have:
        headers["Range"] = f"bytes={have}-"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        if have and getattr(response, "status", 200) != 206:
            have = 0
            part.unlink(missing_ok=True)
        with part.open("ab" if have else "wb") as handle:
            shutil.copyfileobj(response, handle)
    if part.stat().st_size != expected_size:
        raise ManifestError(f"size mismatch: expected {expected_size}, got {part.stat().st_size}")


def verify_local(entry: dict[str, Any], root: Path) -> bool:
    if not entry.get("verified") or not entry.get("sha256"):
        print(f"SKIP {entry['model_id']}: candidate (no sha256)")
        return True
    filename = Path(urllib.parse.urlparse(entry["download_url"][0]).path).name
    target = root / entry["model_id"] / filename
    if not target.exists():
        print(f"MISS {entry['model_id']}: {target}")
        return False
    actual = sha256_file(target)
    ok = actual == entry["sha256"] and target.stat().st_size == entry.get("size")
    print(f"{'OK' if ok else 'FAIL'} {entry['model_id']}: {target}")
    return ok


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect and verify model manifest entries")
    parser.add_argument("--list", action="store_true", help="list every model entry")
    parser.add_argument("--json", action="store_true", help="JSON output for --list")
    parser.add_argument("--verify", action="store_true", help="verify downloaded files")
    parser.add_argument("--download", metavar="MODEL_ID", help="download one verified model")
    parser.add_argument("--all", action="store_true", help="download all verified models")
    parser.add_argument("--dry-run", action="store_true", help="show what would be downloaded")
    parser.add_argument("--models-dir", type=Path, default=DEFAULT_MODELS_DIR)
    parser.add_argument("--accept-license", action="store_true")
    args = parser.parse_args(argv)

    manifest = load_manifest()
    entries = all_entries(manifest)

    if args.list:
        if args.json:
            print(json.dumps([printable(entry) for entry in entries], ensure_ascii=False, indent=2))
        else:
            for entry in entries:
                print(
                    f"{entry['model_id']:<32} {entry['task']:<6} {entry['license']:<14} "
                    f"{'verified' if entry.get('verified') else 'candidate'}"
                )
        return 0

    if args.verify:
        results = [verify_local(entry, args.models_dir) for entry in entries]
        return 0 if all(results) else 1

    targets: list[dict[str, Any]] = []
    if args.all:
        targets = [entry for entry in entries if entry.get("verified")]
    elif args.download:
        targets = [entry for entry in entries if entry.get("model_id") == args.download]
        if not targets:
            print(f"unknown model: {args.download}", file=sys.stderr)
            return 2
    else:
        parser.print_help()
        return 2

    if args.dry_run:
        for entry in targets:
            print(f"would download {entry['model_id']} -> {args.models_dir / entry['model_id']}")
        return 0

    try:
        for entry in targets:
            path = download(
                entry, args.models_dir / entry["model_id"], accept_license=args.accept_license
            )
            print(f"downloaded {entry['model_id']}: {path}")
    except ManifestError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
