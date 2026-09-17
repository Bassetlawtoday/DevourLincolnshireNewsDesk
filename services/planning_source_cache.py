"""Atomic per-source cache for resilient Planning refreshes."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile

from services.models import PlanningApplication


SCHEMA_VERSION = 1
DEFAULT_PATH = Path(__file__).resolve().parents[1] / "data" / "planning_source_cache.json"
APPLICATION_FIELDS = (
    "reference",
    "alt_reference",
    "planning_authority",
    "planning_source_key",
    "address",
    "locality",
    "parish",
    "ward",
    "proposal",
    "status",
    "decision",
    "received_date",
    "validated_date",
    "decision_date",
    "appeal_status",
    "appeal_decision",
    "category",
    "url",
    "score",
    "tags",
    "notes",
)
UNAVAILABLE_AREAS = {"", "unknown area", "other / not identified", "area unavailable"}


def application_to_cache_dict(application):
    return {
        field: getattr(application, field, "")
        for field in APPLICATION_FIELDS
    }


def application_from_cache_dict(payload):
    values = {
        field: payload.get(field, [] if field == "tags" else "")
        for field in APPLICATION_FIELDS
    }
    if not values["locality"]:
        previous_area = str(payload.get("area") or "").strip()
        if previous_area.casefold() not in UNAVAILABLE_AREAS:
            values["locality"] = previous_area
    try:
        values["score"] = int(values["score"] or 0)
    except (TypeError, ValueError):
        values["score"] = 0
    if not isinstance(values["tags"], list):
        values["tags"] = []
    return PlanningApplication(**values)


class PlanningSourceCache:
    def __init__(self, path=DEFAULT_PATH, briefing_path=None):
        self.path = Path(path)
        self.briefing_path = Path(
            briefing_path
            or self.path.parent / "planning_results_cache.json"
        )

    def _empty_document(self):
        return {"schema_version": SCHEMA_VERSION, "sources": {}}

    def _load_document(self):
        try:
            document = json.loads(self.path.read_text(encoding="utf-8"))
            if document.get("schema_version") == SCHEMA_VERSION:
                sources = document.get("sources")
                if isinstance(sources, dict):
                    return document
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass
        return self._bootstrap_from_briefing()

    def _bootstrap_from_briefing(self):
        document = self._empty_document()
        try:
            briefing = json.loads(self.briefing_path.read_text(encoding="utf-8"))
            report = briefing.get("report_data") or {}
            applications = report.get("all_applications") or []
            completed_at = str(briefing.get("successful_at") or "")
            grouped = {}
            for application in applications:
                source_key = str(application.get("planning_source_key") or "").strip()
                if source_key:
                    grouped.setdefault(source_key, []).append(application)
            for source_key, source_applications in grouped.items():
                document["sources"][source_key] = {
                    "successful_at": completed_at,
                    "applications": source_applications,
                }
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass
        return document

    def load(self, source_key):
        source = self._load_document()["sources"].get(str(source_key), {})
        applications = source.get("applications") or []
        return [
            application_from_cache_dict(item)
            for item in applications
            if isinstance(item, dict)
        ]

    def save(self, source_key, applications, completed_at=None):
        document = self._load_document()
        timestamp = completed_at or datetime.now(timezone.utc)
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        document["sources"][str(source_key)] = {
            "successful_at": timestamp.astimezone(timezone.utc).isoformat(),
            "applications": [
                application_to_cache_dict(application)
                for application in applications
            ],
        }
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
            os.replace(temporary_name, self.path)
        except Exception:
            try:
                os.unlink(temporary_name)
            except OSError:
                pass
            raise

