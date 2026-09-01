from __future__ import annotations

import json
from pathlib import Path


class SourceLoader:
    """Loads sources.json."""

    def __init__(self, config_path: str = "config/sources.json") -> None:
        self.config_path = Path(config_path)

    def load(self) -> list[dict]:
        if not self.config_path.exists():
            raise FileNotFoundError(self.config_path)

        with self.config_path.open(
            "r",
            encoding="utf-8",
        ) as fp:
            config = json.load(fp)

        return [
            source
            for source in config.get("sources", [])
            if source.get("enabled", True)
        ]