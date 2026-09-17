"""Planning-only locality and authority reporting helpers."""

from __future__ import annotations

import re
from collections import Counter

from editorial.priority_engine import score_story


UNAVAILABLE_AREAS = {
    "",
    "unknown area",
    "other / not identified",
    "area unavailable",
}


def clean_text(value):
    return " ".join(str(value or "").split())


def clean_area_candidate(value):
    candidate = clean_text(value)
    if not candidate:
        return ""
    candidate = re.sub(
        r"\b(Lincolnshire|North Lincolnshire|North East Lincolnshire)\b",
        "",
        candidate,
        flags=re.I,
    )
    candidate = re.sub(
        r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b",
        "",
        candidate,
        flags=re.I,
    )
    candidate = re.sub(r"^[\s,;\-]+|[\s,;\-]+$", "", candidate)
    if not candidate or candidate.casefold() in UNAVAILABLE_AREAS:
        return ""
    return candidate


def extract_area(address, *, locality="", parish="", ward=""):
    """Resolve a defensible locality from structured fields then the address."""
    for value in (locality, parish, ward):
        candidate = clean_area_candidate(value)
        if candidate:
            return candidate

    address_text = clean_text(address)
    if not address_text:
        return "Area unavailable"

    try:
        priority = score_story(module="planning", title="", summary=address_text)
        matched = clean_area_candidate(priority.matched_place)
        if matched:
            return matched
    except Exception:
        # Address parsing remains available if editorial settings are absent
        # during diagnostics or a standalone test.
        pass

    parts = [part.strip() for part in address_text.split(",") if part.strip()]
    if len(parts) > 1:
        for part in reversed(parts[1:]):
            candidate = clean_area_candidate(part)
            if candidate:
                return candidate
    return "Area unavailable"


def resolved_area(app, matched_place=""):
    matched = clean_area_candidate(matched_place)
    if matched:
        return matched
    return extract_area(
        app.address,
        locality=getattr(app, "locality", ""),
        parish=getattr(app, "parish", ""),
        ward=getattr(app, "ward", ""),
    )


def area_breakdown(applications):
    counts = Counter(resolved_area(app) for app in applications)
    return [
        {"name": name, "count": count}
        for name, count in counts.most_common()
        if name.casefold() not in UNAVAILABLE_AREAS
    ]


def unavailable_area_count(applications):
    return sum(
        1
        for app in applications
        if resolved_area(app).casefold() in UNAVAILABLE_AREAS
    )


def authority_breakdown(applications, configured_sources):
    counts = Counter(
        clean_text(getattr(app, "planning_source_key", ""))
        for app in applications
    )
    return [
        {
            "key": source.key,
            "name": source.authority_label,
            "count": counts.get(source.key, 0),
        }
        for source in configured_sources
    ]
