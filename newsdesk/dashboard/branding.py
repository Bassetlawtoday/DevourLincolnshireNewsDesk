"""Configurable NewsDesk product and newsroom identity."""

from __future__ import annotations

import json
from pathlib import Path


DEFAULT_BRANDING = {
    "product_name": "NewsDesk Pro",
    "newsroom_name": "Devour Lincolnshire",
    "newsroom_descriptor": "Local newsroom",
}


def load_branding(path: Path | None = None) -> dict[str, str]:
    target = path or Path(__file__).resolve().parents[2] / "config" / "branding.json"
    branding = dict(DEFAULT_BRANDING)
    try:
        loaded = json.loads(target.read_text(encoding="utf-8"))
        for key in branding:
            value = loaded.get(key)
            if isinstance(value, str) and value.strip():
                branding[key] = value.strip()
    except (OSError, ValueError, TypeError):
        pass
    return branding
