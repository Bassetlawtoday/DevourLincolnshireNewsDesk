"""Load configurable sports website sources from JSON."""

from __future__ import annotations

import json
from pathlib import Path

from newsdesk.sports.websites.source import WebsiteSource


DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parents[3]
    / "config"
    / "sport_websites.json"
)


class WebsiteSourceLoader:
    """Read and validate generic website source definitions."""

    def __init__(self, config_path: str | Path | None = None) -> None:
        self.config_path = Path(config_path or DEFAULT_CONFIG_PATH)

    def load(self, *, enabled_only: bool = True) -> list[WebsiteSource]:
        if not self.config_path.is_file():
            raise FileNotFoundError(self.config_path)

        with self.config_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)

        if isinstance(payload, list):
            raw_sources = payload
        elif isinstance(payload, dict):
            raw_sources = payload.get("sources", [])
        else:
            raise ValueError("sport_websites.json must contain a list or object.")

        if not isinstance(raw_sources, list):
            raise ValueError("The 'sources' value must be a list.")

        sources = [WebsiteSource.from_dict(item) for item in raw_sources]

        if enabled_only:
            sources = [source for source in sources if source.enabled]

        return sources


__all__ = ["DEFAULT_CONFIG_PATH", "WebsiteSourceLoader"]
