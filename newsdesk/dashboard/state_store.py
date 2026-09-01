"""Atomic lightweight persistence for dashboard state."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from typing import Any


DEFAULT_STATE = {
    "version": 1,
    "modules": {},
    "recent_runs": [],
    "scheduler": {
        "module_policies": {
            "planning": {"mode": "Off", "daily_time": "06:15"},
            "police": {"mode": "Off"},
            "fire": {"mode": "Off"},
            "sport": {"mode": "Off"},
            "council": {"mode": "Off"},
            "government": {"mode": "Off"},
            "events": {"mode": "Off"},
            "content": {"mode": "Off"}
        },
        "refresh_on_startup": False,
        "max_heavy_collectors": 2,
    },
}


class DashboardStateStore:
    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path or Path("data") / "dashboard_state.json")

    def load(self) -> dict[str, Any]:
        state = json.loads(json.dumps(DEFAULT_STATE))
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return state
        if isinstance(loaded, dict):
            state.update(loaded)
            state["scheduler"] = {
                **DEFAULT_STATE["scheduler"],
                **(loaded.get("scheduler") or {}),
            }
            configured = (loaded.get("scheduler") or {}).get("module_policies") or {}
            state["scheduler"]["module_policies"] = {
                key: {**value, **(configured.get(key) or {})}
                for key, value in DEFAULT_STATE["scheduler"]["module_policies"].items()
            }
        return state

    def save(self, state: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent
        )
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump(state, stream, indent=2, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_name, self.path)
        except Exception:
            try:
                os.unlink(temporary_name)
            except OSError:
                pass
            raise
