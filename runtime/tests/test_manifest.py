import json
import subprocess
import sys
from pathlib import Path

import jsonschema

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MANIFEST = PROJECT_ROOT / "models" / "manifest.json"
SCHEMA = PROJECT_ROOT / "models" / "manifest.schema.json"
DOWNLOADER = PROJECT_ROOT / "scripts" / "download_models.py"


def test_manifest_matches_schema() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    jsonschema.validate(manifest, schema)


def test_verified_models_have_hash_and_size() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for entry in manifest["models"]:
        assert entry["verified"] is True
        assert len(entry["sha256"]) == 64
        assert entry["size"] > 0
        assert entry["license"]


def test_candidates_are_not_auto_downloadable() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for entry in manifest.get("candidates", []):
        assert entry["verified"] is False
        digest = entry.get("sha256")
        if digest is not None:
            assert len(digest) == 64


def test_downloader_list_and_dry_run() -> None:
    listing = subprocess.run(
        [sys.executable, str(DOWNLOADER), "--list", "--json"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert listing.returncode == 0, listing.stderr
    entries = json.loads(listing.stdout)
    assert any(entry["model_id"] == "silero-vad-v4" for entry in entries)

    dry_run = subprocess.run(
        [sys.executable, str(DOWNLOADER), "--download", "silero-vad-v4", "--dry-run"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert dry_run.returncode == 0, dry_run.stderr
    assert "would download" in dry_run.stdout
