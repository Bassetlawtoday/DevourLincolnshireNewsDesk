from __future__ import annotations

from collections import defaultdict
from difflib import SequenceMatcher
from typing import Iterable

from .models import EventRecord, slug_text


def _similar(a: str | None, b: str | None) -> float:
    return SequenceMatcher(None, slug_text(a), slug_text(b)).ratio()


def _same_day(a: EventRecord, b: EventRecord) -> bool:
    if not a.start or not b.start:
        return True
    return a.start.date() == b.start.date()


def likely_duplicate(a: EventRecord, b: EventRecord) -> bool:
    # Explicit performances in the same series are separate events even when
    # title, venue and calendar date are identical.
    if a.occurrence_key and b.occurrence_key and a.occurrence_key != b.occurrence_key:
        return False
    if a.series_key and b.series_key and a.series_key == b.series_key and a.start and b.start and a.start != b.start:
        return False
    if not _same_day(a, b):
        return False
    if _similar(a.title, b.title) < 0.84:
        return False
    venue_score = _similar(a.venue, b.venue)
    town_score = _similar(a.town, b.town)
    return venue_score >= 0.72 or town_score >= 0.90 or (not a.venue and not b.venue)


def _merge(best: EventRecord, other: EventRecord) -> EventRecord:
    fields = [
        "start", "end", "venue", "room", "address", "town", "county", "postcode",
        "latitude", "longitude", "category", "description", "image_url", "event_url",
        "ticket_url", "price_text", "status", "age_restriction",
    ]
    for field in fields:
        if getattr(best, field) in (None, "") and getattr(other, field) not in (None, ""):
            setattr(best, field, getattr(other, field))
    sources = best.raw.setdefault("merged_sources", [])
    if other.source not in sources:
        sources.append(other.source)
    return best


def deduplicate(events: Iterable[EventRecord]) -> list[EventRecord]:
    records = list(events)
    records.sort(key=lambda e: e.source_rank)
    output: list[EventRecord] = []
    for event in records:
        match = next((existing for existing in output if likely_duplicate(existing, event)), None)
        if match is None:
            output.append(event)
        else:
            _merge(match, event)
    return output
