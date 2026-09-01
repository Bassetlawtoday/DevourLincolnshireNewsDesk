from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import datetime
from hashlib import sha1
from typing import Any, Iterable

from .html_utils import parse_datetime
from .models import EventRecord, slug_text

_OCCURRENCE_KEYS = ("occurrences", "performances", "sessions", "dates", "instances")


def _series_key(event: EventRecord, parent_id: str | None = None) -> str:
    if event.series_key:
        return event.series_key
    identity = "|".join([
        event.source or "",
        parent_id or event.source_event_id or "",
        slug_text(event.title),
        slug_text(event.venue),
        slug_text(event.town),
    ])
    return sha1(identity.encode("utf-8")).hexdigest()


def _value(item: dict[str, Any], *names: str) -> Any:
    for name in names:
        if item.get(name) not in (None, ""):
            return item.get(name)
    return None


def _occurrence_times(item: Any) -> tuple[datetime | None, datetime | None, str | None, str | None]:
    if isinstance(item, str):
        return parse_datetime(item), None, None, None
    if not isinstance(item, dict):
        return None, None, None, None
    start = parse_datetime(_value(item, "start", "startDate", "start_time", "date", "datetime", "from"))
    end = parse_datetime(_value(item, "end", "endDate", "end_time", "to"))
    occ_id = _value(item, "id", "instanceId", "instance_id", "performanceId", "performance_id")
    status = _value(item, "status", "eventStatus", "availability")
    return start, end, str(occ_id) if occ_id is not None else None, str(status) if status is not None else None


class OccurrenceExpander:
    """Expand explicit multi-occurrence source records into EventRecord rows.

    Expansion is intentionally evidence-based. Date ranges alone are not split;
    a source must provide an explicit list under one of the supported occurrence
    keys. Connectors that already emit one EventRecord per performance can set
    ``occurrence_key`` and are passed through unchanged.
    """

    @classmethod
    def expand(cls, event: EventRecord) -> list[EventRecord]:
        if event.occurrence_key:
            return [event]
        raw = event.raw or {}
        # Spektrix and similar connectors may retain a full parent payload in
        # raw while already emitting individual instances. Do not double-expand.
        if raw.get("instance"):
            return [event]

        values = None
        key_used = None
        for key in _OCCURRENCE_KEYS:
            candidate = raw.get(key)
            if isinstance(candidate, list) and candidate:
                values = candidate
                key_used = key
                break
        if not values:
            return [event]

        parent_id = event.source_event_id
        series_key = _series_key(event, parent_id)
        out: list[EventRecord] = []
        seen: set[str] = set()
        for index, item in enumerate(values, start=1):
            start, end, occurrence_id, status = _occurrence_times(item)
            if start is None:
                continue
            identity = occurrence_id or start.isoformat()
            occurrence_key = f"{series_key}:{identity}"
            if occurrence_key in seen:
                continue
            seen.add(occurrence_key)
            child_raw = deepcopy(raw)
            child_raw["parent_source_event_id"] = parent_id
            child_raw["occurrence_source_key"] = key_used
            child_raw["occurrence_index"] = index
            child_raw["occurrence_payload"] = item
            child_id = f"{parent_id}:{occurrence_id or index}" if parent_id else occurrence_id
            out.append(replace(
                event,
                source_event_id=child_id or event.source_event_id,
                start=start,
                end=end or (event.end if event.start and event.end and event.start.date() == start.date() else None),
                status=status or event.status,
                series_key=series_key,
                occurrence_key=occurrence_key,
                raw=child_raw,
            ))
        return out or [event]

    @classmethod
    def expand_many(cls, events: Iterable[EventRecord]) -> list[EventRecord]:
        out: list[EventRecord] = []
        for event in events:
            out.extend(cls.expand(event))
        return out
