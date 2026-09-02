"""Durable last-successful snapshots for live intelligence feeds."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime
import json
import logging
import os
from pathlib import Path
import tempfile
from typing import Any

from newsdesk.publish_result import PublishResult
from newsdesk.story import Story


LOGGER = logging.getLogger(__name__)
PERSISTED_MODULES = frozenset({"police", "fire", "sport", "council"})


class FeedSnapshotStore:
    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or Path("data") / "feed_snapshots"

    def save(self, module_key: str, payload: dict[str, Any], completed_at: datetime) -> None:
        primary, backup = self._paths(module_key)
        primary.parent.mkdir(parents=True, exist_ok=True)
        document = {"schema_version": 1, "module_key": module_key,
                    "completed_at": completed_at.isoformat(),
                    "payload": self._serialise(payload)}
        handle, temporary = tempfile.mkstemp(prefix=f".{primary.name}.", suffix=".tmp", dir=primary.parent)
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump(document, stream, ensure_ascii=False, indent=2, default=self._json_default)
                stream.flush(); os.fsync(stream.fileno())
            if primary.is_file():
                os.replace(primary, backup)
            os.replace(temporary, primary)
        except Exception:
            try: os.unlink(temporary)
            except OSError: pass
            raise

    def load(self, module_key: str) -> tuple[dict[str, Any], datetime] | None:
        for candidate in self._paths(module_key):
            try:
                document = json.loads(candidate.read_text(encoding="utf-8"))
                if document.get("schema_version") != 1 or document.get("module_key") != module_key:
                    raise ValueError("invalid feed snapshot")
                return self._deserialise(document["payload"]), datetime.fromisoformat(document["completed_at"])
            except FileNotFoundError:
                continue
            except Exception:
                LOGGER.warning("Ignored invalid feed snapshot: %s", candidate)
        return None

    def _paths(self, module_key: str) -> tuple[Path, Path]:
        primary = self.directory / f"{module_key}.json"
        return primary, primary.with_suffix(".json.bak")

    @staticmethod
    def _json_default(value: Any):
        if isinstance(value, datetime): return value.isoformat()
        if isinstance(value, Path): return str(value)
        if isinstance(value, (set, tuple)): return list(value)
        if is_dataclass(value): return asdict(value)
        return str(value)

    @staticmethod
    def _serialise(payload: dict[str, Any]) -> dict[str, Any]:
        stories = list(payload.get("stories") or [])
        positions = {id(story): index for index, story in enumerate(stories)}
        results = []
        for story_id, result in dict(payload.get("publish_results") or {}).items():
            position = positions.get(story_id)
            if position is None: continue
            data = asdict(result) if isinstance(result, PublishResult) or is_dataclass(result) else result
            if isinstance(data, dict): results.append({"story_index": position, "result": data})
        return {"stories": [item.to_dict() if isinstance(item, Story) else dict(item) for item in stories],
                "publish_results": results, "errors": payload.get("errors") or [],
                "source_health": payload.get("source_health") or {}}

    @staticmethod
    def _deserialise(payload: dict[str, Any]) -> dict[str, Any]:
        stories = [Story.from_dict(item) for item in payload.get("stories") or []]
        allowed = set(PublishResult.__dataclass_fields__)
        results = {}
        for row in payload.get("publish_results") or []:
            position = int(row["story_index"])
            if not 0 <= position < len(stories): continue
            data = row.get("result") or {}
            results[id(stories[position])] = PublishResult(**{key: value for key, value in data.items() if key in allowed})
        return {"stories": stories, "publish_results": results,
                "errors": list(payload.get("errors") or []),
                "source_health": dict(payload.get("source_health") or {})}


def hydrate_feed_window(module_key: str, window: Any) -> bool:
    """Load the latest successful snapshot into any direct module launch."""
    restored = FeedSnapshotStore().load(module_key)
    if not restored:
        return False
    payload, _completed_at = restored
    arguments = [payload["stories"], payload["publish_results"], payload["errors"]]
    if module_key == "council":
        arguments.append(payload["source_health"])
    window.load_stories(*arguments)
    return True


def persist_feed_payload(module_key: str, payload: dict[str, Any]) -> None:
    """Persist a successful refresh even when a module was launched directly."""
    FeedSnapshotStore().save(module_key, payload, datetime.now().astimezone())
