"""Validated source catalogue for Lincolnshire planning registers."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin


DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parent.parent
    / "config"
    / "planning_websites.json"
)


@dataclass(frozen=True)
class PlanningSource:
    key: str
    name: str
    authorities: tuple[str, ...]
    platform: str
    base_url: str
    enabled: bool
    disabled_reason: str = ""
    transition_note: str = ""
    weekly_list_url: str = ""

    @property
    def weekly_url(self) -> str:
        return urljoin(
            self.base_url,
            "search.do?action=weeklyList&searchType=Application",
        )

    @property
    def authority_label(self) -> str:
        return " and ".join(self.authorities)


def _required_text(record: dict, field: str, key: str) -> str:
    value = str(record.get(field, "")).strip()
    if not value:
        raise ValueError(f"Planning source {key!r} has no {field!r} value.")
    return value


def load_planning_sources(
    path: str | Path = DEFAULT_CONFIG_PATH,
    *,
    enabled_only: bool = False,
    platforms: Iterable[str] | None = None,
) -> list[PlanningSource]:
    """Load planning sources while rejecting unsafe or incomplete entries."""
    config_path = Path(path)
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    records = payload.get("sources")
    if not isinstance(records, list):
        raise ValueError("Planning source configuration must contain a sources list.")

    platform_filter = {
        str(value).strip() for value in (platforms or ()) if str(value).strip()
    }
    sources: list[PlanningSource] = []
    seen_keys: set[str] = set()

    for record in records:
        if not isinstance(record, dict):
            raise ValueError("Each planning source must be an object.")

        key = _required_text(record, "key", "unknown")
        if key in seen_keys:
            raise ValueError(f"Duplicate planning source key: {key}")
        seen_keys.add(key)

        authorities_value = record.get("authorities")
        if not isinstance(authorities_value, list):
            raise ValueError(f"Planning source {key!r} must list its authorities.")
        authorities = tuple(
            str(authority).strip()
            for authority in authorities_value
            if str(authority).strip()
        )
        if not authorities:
            raise ValueError(f"Planning source {key!r} has no authorities.")

        base_url = _required_text(record, "base_url", key)
        if not base_url.startswith("https://"):
            raise ValueError(f"Planning source {key!r} must use HTTPS.")
        if not base_url.endswith("/") and record.get("platform") == "idox_public_access":
            base_url += "/"

        source = PlanningSource(
            key=key,
            name=_required_text(record, "name", key),
            authorities=authorities,
            platform=_required_text(record, "platform", key),
            base_url=base_url,
            enabled=bool(record.get("enabled", False)),
            disabled_reason=str(record.get("disabled_reason", "")).strip(),
            transition_note=str(record.get("transition_note", "")).strip(),
            weekly_list_url=str(record.get("weekly_list_url", "")).strip(),
        )

        if enabled_only and not source.enabled:
            continue
        if platform_filter and source.platform not in platform_filter:
            continue
        sources.append(source)

    return sources


def enabled_idox_sources(
    path: str | Path = DEFAULT_CONFIG_PATH,
) -> list[PlanningSource]:
    return load_planning_sources(
        path,
        enabled_only=True,
        platforms=("idox_public_access",),
    )


def enabled_additional_sources(
    path: str | Path = DEFAULT_CONFIG_PATH,
) -> list[PlanningSource]:
    """Return enabled, explicitly supported non-Idox collectors."""
    return load_planning_sources(
        path,
        enabled_only=True,
        platforms=(
            "south_holland_weekly_pdf",
            "statmap_weekly",
            "north_lincs_weekly",
            "lincolnshire_county_register",
        ),
    )
