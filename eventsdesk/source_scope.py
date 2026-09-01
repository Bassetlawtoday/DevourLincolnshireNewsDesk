from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

COUNTIES = ("Nottinghamshire", "Derbyshire", "Lincolnshire", "Leicestershire")

AREA_TOKENS = {
    "Nottinghamshire": (
        "nottinghamshire", "nottingham", "bassetlaw", "ashfield", "gedling",
        "broxtowe", "rushcliffe", "southwell", "sherwood forest", "worksop",
        "mansfield", "newark",
    ),
    "Derbyshire": (
        "derbyshire", "derby", "buxton", "chesterfield", "peak district",
        "bakewell", "matlock bath", "crich", "amber valley", "high peak",
        "derbyshire dales", "erewash", "north east derbyshire", "bolsover",
    ),
    "Lincolnshire": (
        "lincolnshire", "lincoln", "grantham", "east lindsey", "boston",
        "market rasen", "south kesteven", "north kesteven", "west lindsey",
        "south holland", "skegness", "spalding",
    ),
    "Leicestershire": (
        "leicestershire", "leicester", "charnwood", "harborough", "hinckley",
        "melton", "north west leicestershire", "blaby", "oadby", "loughborough",
    ),
}


def counties_for_area(area: str | None) -> tuple[str, ...]:
    value = (area or "").casefold()
    return tuple(
        county for county, tokens in AREA_TOKENS.items()
        if any(token in value for token in tokens)
    )


def source_is_in_enabled_geography(source) -> bool:
    return bool(counties_for_area(getattr(source, "area", None)))


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
