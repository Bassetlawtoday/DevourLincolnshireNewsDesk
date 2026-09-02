from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

COUNTIES = ("Lincolnshire",)

AREA_TOKENS = {
    "Lincolnshire": (
        "lincolnshire", "lincoln", "grantham", "east lindsey", "boston",
        "market rasen", "south kesteven", "north kesteven", "west lindsey",
        "south holland", "skegness", "spalding", "north lincolnshire",
        "north east lincolnshire", "scunthorpe", "grimsby", "cleethorpes",
        "barton-upon-humber", "barton upon humber", "brigg", "epworth",
        "immingham", "louth", "sleaford", "bourne", "stamford", "gainsborough",
        "horncastle", "mablethorpe", "alford", "spilsby", "woodhall spa",
        "tattershall", "wragby", "caistor", "crowland", "holbeach",
        "long sutton", "market deeping", "kirton in lindsey", "the wash",
    ),
}


def counties_for_area(area: str | None) -> tuple[str, ...]:
    value = (area or "").casefold()
    if "fringe" in value:
        return ()
    return tuple(
        county for county, tokens in AREA_TOKENS.items()
        if any(token in value for token in tokens)
    )


def source_is_in_enabled_geography(source) -> bool:
    return bool(counties_for_area(getattr(source, "area", None)))


def event_is_in_enabled_geography(event, source_area: str | None = None) -> bool:
    """Return True only for Greater Lincolnshire event records.

    A trusted Lincolnshire-wide source area is sufficient. Mixed regional feeds
    must provide Lincolnshire evidence in the event's own location fields.
    """
    area = (source_area or "").strip()
    if area and "fringe" not in area.casefold() and counties_for_area(area):
        return True
    evidence = " ".join(
        str(getattr(event, field, "") or "")
        for field in ("county", "town", "venue", "address", "postcode")
    )
    return bool(counties_for_area(evidence))


def event_is_allowed(event) -> bool:
    """Apply product-wide EventsDesk exclusions after enrichment."""
    category = str(getattr(event, "category", "") or "").strip().casefold()
    return category not in {"film", "cinema", "movie", "event cinema"}


def preference_path(data_dir: str | Path) -> Path:
    return Path(data_dir) / "source_preferences.json"


def load_disabled_source_ids(data_dir: str | Path) -> set[str]:
    path = preference_path(data_dir)
    if not path.exists():
        return set()
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        return {str(x) for x in payload.get("disabled_source_ids", [])}
    except (OSError, ValueError, TypeError):
        return set()


def save_disabled_source_ids(data_dir: str | Path, disabled_ids: Iterable[str]) -> None:
    path = preference_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "enabled_counties": list(COUNTIES),
        "disabled_source_ids": sorted({str(x) for x in disabled_ids}),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def eligible_sources(catalog) -> list:
    rows = [
        source for source in catalog.select(runnable_only=True)
        if source_is_in_enabled_geography(source)
    ]
    rows.sort(key=lambda s: (s.source_rank, s.priority, s.name.casefold()))
    return rows


def enabled_sources(catalog, data_dir: str | Path, county: str | None = None) -> list:
    disabled = load_disabled_source_ids(data_dir)
    rows = [s for s in eligible_sources(catalog) if s.id not in disabled]
    if county and county != "All enabled sources":
        rows = [s for s in rows if county in counties_for_area(s.area)]
    return rows
