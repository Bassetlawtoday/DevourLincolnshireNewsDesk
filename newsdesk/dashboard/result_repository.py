"""Current-process payload sharing between Home and module windows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import threading
from typing import Any


@dataclass(frozen=True, slots=True)
class DashboardStoredResult:
    payload: Any
    completed_at: datetime


class DashboardResultRepository:
    """Thread-safe in-memory repository; full payloads are never persisted."""

    def __init__(self) -> None:
        self._results: dict[str, DashboardStoredResult] = {}
        self._lock = threading.RLock()

    def set_result(self, module_key: str, payload: Any, completed_at: datetime) -> None:
        with self._lock:
            self._results[module_key] = DashboardStoredResult(payload, completed_at)

    def get_result(self, module_key: str) -> DashboardStoredResult | None:
        with self._lock:
            return self._results.get(module_key)

    def has_result(self, module_key: str) -> bool:
        with self._lock:
            return module_key in self._results

    def clear_result(self, module_key: str) -> None:
        with self._lock:
            self._results.pop(module_key, None)
