"""Current-process payload sharing between Home and module windows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import logging
import threading
from typing import Any

from .feed_snapshot_store import FeedSnapshotStore, PERSISTED_MODULES

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DashboardStoredResult:
    payload: Any
    completed_at: datetime


class DashboardResultRepository:
    """Thread-safe repository with durable last-successful feed snapshots."""

    def __init__(self, snapshot_dir=None) -> None:
        self._results: dict[str, DashboardStoredResult] = {}
        self._lock = threading.RLock()
        self._snapshots = FeedSnapshotStore(snapshot_dir)
        for module_key in PERSISTED_MODULES:
            restored = self._snapshots.load(module_key)
            if restored:
                payload, completed_at = restored
                self._results[module_key] = DashboardStoredResult(payload, completed_at)

    def set_result(self, module_key: str, payload: Any, completed_at: datetime) -> None:
        with self._lock:
            self._results[module_key] = DashboardStoredResult(payload, completed_at)
            if module_key in PERSISTED_MODULES:
                try:
                    self._snapshots.save(module_key, payload, completed_at)
                except Exception:
                    LOGGER.exception("Could not persist %s feed snapshot", module_key)

    def get_result(self, module_key: str) -> DashboardStoredResult | None:
        with self._lock:
            return self._results.get(module_key)

    def has_result(self, module_key: str) -> bool:
        with self._lock:
            return module_key in self._results

    def clear_result(self, module_key: str) -> None:
        with self._lock:
            self._results.pop(module_key, None)
