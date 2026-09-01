"""Bounded, atomic and non-secret System Health history."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import tempfile


LOGGER = logging.getLogger(__name__)
DEFAULT_PATH = Path("data") / "system_health_state.json"


class HealthStateStore:
    SCHEMA_VERSION = 1
    HISTORY_LIMIT = 20

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path or DEFAULT_PATH)
        self.corrupt = False

    def load(self) -> dict:
        self.corrupt = False
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            if value.get("schema_version") != self.SCHEMA_VERSION or not isinstance(value.get("history"), list):
                raise ValueError("unsupported health-state schema")
            value["history"] = value["history"][-self.HISTORY_LIMIT:]
            value.setdefault("diagnostics", [])
            value["diagnostics"] = value["diagnostics"][-self.HISTORY_LIMIT:]
            return value
        except FileNotFoundError:
            return {"schema_version": self.SCHEMA_VERSION, "history": [], "diagnostics": []}
        except (OSError, ValueError, TypeError):
            self.corrupt = True
            LOGGER.warning("System Health state is unreadable; preserving it and using empty history.")
            return {"schema_version": self.SCHEMA_VERSION, "history": [], "diagnostics": []}

    def record(self, snapshot) -> None:
        state = self.load()
        state["history"].append({
            "checked_at": snapshot.to_dict()["completed_at"],
            "overall_status": snapshot.overall_status.value,
            "warning_count": snapshot.warning_count,
            "failure_count": snapshot.failure_count,
            "inactive_count": snapshot.inactive_count,
            "duration": snapshot.duration,
            "item_statuses": {item.key: item.status.value for item in snapshot.items},
        })
        state["history"] = state["history"][-self.HISTORY_LIMIT:]
        self._write(state)

    def record_diagnostic(self, result: dict) -> None:
        state = self.load()
        if self.corrupt:
            return
        state.setdefault("diagnostics", []).append(result)
        state["diagnostics"] = state["diagnostics"][-self.HISTORY_LIMIT:]
        self._write(state)

    def _write(self, value):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump(value, stream, indent=2, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        except Exception:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise
