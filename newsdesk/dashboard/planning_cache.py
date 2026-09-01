"""Versioned atomic persistence for the last successful Planning briefing."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any


SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class CachedPlanningResult:
    report_data: dict[str, Any]
    completed_at: datetime
    count: int


class PlanningResultCache:
    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(
            path or Path("data") / "planning_results_cache.json"
        )
        self.backup_path = self.path.with_suffix(".backup.json")

    def save(self, report_data: dict[str, Any], completed_at: datetime) -> None:
        count = self._validate_report_data(report_data)
        timestamp = completed_at
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        document = {
            "schema_version": SCHEMA_VERSION,
            "successful_at": timestamp.astimezone(timezone.utc).isoformat(),
            "count": count,
            "report_data": report_data,
        }
        # Validate serialisability before touching the successful cache.
        encoded = json.dumps(document, ensure_ascii=False, indent=2)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent
        )
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            if self.path.exists():
                shutil.copy2(self.path, self.backup_path)
            os.replace(temporary_name, self.path)
        except Exception:
            try:
                os.unlink(temporary_name)
            except OSError:
                pass
            raise

    def load(self) -> CachedPlanningResult | None:
        try:
            document = json.loads(self.path.read_text(encoding="utf-8"))
            if document.get("schema_version") != SCHEMA_VERSION:
                return None
            report_data = document.get("report_data")
            count = self._validate_report_data(report_data)
            if int(document.get("count", -1)) != count:
                return None
            completed_at = datetime.fromisoformat(
                str(document["successful_at"]).replace("Z", "+00:00")
            )
            if completed_at.tzinfo is None:
                completed_at = completed_at.replace(tzinfo=timezone.utc)
            return CachedPlanningResult(report_data, completed_at, count)
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            return None

    @staticmethod
    def _validate_report_data(report_data: object) -> int:
        if not isinstance(report_data, dict):
            raise ValueError("Planning report payload must be a dictionary.")
        applications = report_data.get("all_applications")
        if not isinstance(applications, list):
            raise ValueError("Planning report payload has no application list.")
        count = int(report_data.get("applications_processed", len(applications)))
        if count != len(applications):
            raise ValueError("Planning payload count does not match its application list.")
        return count
