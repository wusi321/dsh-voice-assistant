#!/usr/bin/env python
"""Regenerate config/default.json and config/schema.json from the Pydantic model."""

from __future__ import annotations

import json
from pathlib import Path

from voice_runtime.config.schema import config_json_schema, default_config_dict

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    (ROOT / "config").mkdir(exist_ok=True)
    (ROOT / "config" / "default.json").write_text(
        json.dumps(default_config_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (ROOT / "config" / "schema.json").write_text(
        json.dumps(config_json_schema(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("wrote config/default.json and config/schema.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
