from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files
import json
import os
from typing import Iterable

from .connectors import (
    AcademyMusicGroupConnector,
    WarwickArtsCentreConnector,
    BlackCountryLivingMuseumConnector,
    ATGConnector,
    CouncilHtmlConnector,
    EnglishHeritageConnector,
    NationalTrustConnector,
    LegacySpektrixEventListConnector,
    RockCityConnector,
    SkiddleConnector,
    SpektrixConnector,
    AutoSpektrixConnector,
    StructuredHtmlConnector,
    PagedStructuredHtmlConnector,
    TicketmasterConnector,
    TourismCalendarConnector,
    TRCHConnector,
    SecondaryVenueIndexConnector,
    PazazProjectsConnector,
    Ents24MidlandsConnector,
    NottsEventsConnector,
    SeeTicketsMidlandsConnector,
    AllEventsApiConnector,
)
from .scheduler import DEFAULT_POLICIES, ScheduledSource


@dataclass(frozen=True, slots=True)
class SourceConfig:
    id: str
    name: str
    url: str
    area: str | None
    type: str | None
    priority: str
    domain: str
    reuse_class: str
    pattern_family: str
    technical_confidence: str
    connector: str
    schedule_profile: str
    activation_state: str
    source_rank: int
    scrape_difficulty: str | None
    api_feed_note: str | None
    batch: int
    enabled_by_default: bool
    rollout_note: str

    @property
    def runnable(self) -> bool:
        return self.activation_state == "ready" and self.connector != "unsupported"


class SourceCatalog:
    """Configuration registry for the 374-source Midlands inventory."""

    def __init__(self, sources: Iterable[SourceConfig]):
        self.sources = tuple(sources)
        self._by_id = {s.id: s for s in self.sources}

    @classmethod
    def load_default(cls) -> "SourceCatalog":
        path = files("eventsdesk").joinpath("data/source_registry.json")
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = list(payload["sources"])
        extension = files("eventsdesk").joinpath("data/lincolnshire_sources.json")
        if extension.is_file():
            additions = json.loads(extension.read_text(encoding="utf-8")).get("sources", [])
            merged = {row["id"]: row for row in rows}
            for row in additions:
                merged[row["id"]] = row
            rows = list(merged.values())
        return cls(SourceConfig(**row) for row in rows)

    def get(self, source_id: str) -> SourceConfig:
        return self._by_id[source_id]

    def batch(self, number: int, *, runnable_only: bool = False) -> list[SourceConfig]:
        rows = [s for s in self.sources if s.batch == number]
        return [s for s in rows if s.runnable] if runnable_only else rows

    def select(
        self,
        *,
        batches: set[int] | None = None,
        priorities: set[str] | None = None,
        states: set[str] | None = None,
        connectors: set[str] | None = None,
        runnable_only: bool = False,
    ) -> list[SourceConfig]:
        rows = list(self.sources)
        if batches:
            rows = [s for s in rows if s.batch in batches]
        if priorities:
            rows = [s for s in rows if s.priority in priorities]
        if states:
            rows = [s for s in rows if s.activation_state in states]
        if connectors:
            rows = [s for s in rows if s.connector in connectors]
        if runnable_only:
            rows = [s for s in rows if s.runnable]
        return rows

    def summary(self) -> dict:
        from collections import Counter
        return {
            "sources": len(self.sources),
            "batches": max((s.batch for s in self.sources), default=0),
            "runnable": sum(1 for s in self.sources if s.runnable),
            "states": dict(Counter(s.activation_state for s in self.sources)),
            "connectors": dict(Counter(s.connector for s in self.sources)),
            "priorities": dict(Counter(s.priority for s in self.sources)),
        }


def connector_factory(config: SourceConfig):
    """Return a zero-argument connector factory for a registry row.

    Rows in probe/hold state deliberately raise ValueError instead of silently
    pretending to be production-ready.
    """
    if not config.runnable:
        raise ValueError(f"Source is not runnable: {config.name} ({config.activation_state})")

    def make():
        defaults = {
            "Rock City": ("Rock City", "Nottingham", "NG1 5GG"),
            "Theatre Royal & Royal Concert Hall": ("Theatre Royal & Royal Concert Hall", "Nottingham", "NG1 5ND"),
            "Birmingham Rep": ("Birmingham Rep", "Birmingham", "B1 2EP"),
            "Buxton Opera House": ("Buxton Opera House", "Buxton", "SK17 6XN"),
            "Derby Theatre": ("Derby Theatre", "Derby", "DE1 2NF"),
            "New Vic Theatre": ("New Vic Theatre", "Newcastle-under-Lyme", "ST5 0JG"),
            "Nottingham Playhouse": ("Nottingham Playhouse", "Nottingham", "NG1 5AF"),
            "O2 Academy Birmingham": ("O2 Academy Birmingham", "Birmingham", "B1 1DB"),
            "O2 Academy Leicester": ("O2 Academy Leicester", "Leicester", "LE1 7RH"),
            "O2 Institute Birmingham": ("O2 Institute Birmingham", "Birmingham", "B5 6DY"),
            "Regent Theatre Stoke": ("Regent Theatre", "Stoke-on-Trent", "ST1 1AP"),
            "Warwick Arts Centre": ("Warwick Arts Centre", "Coventry", "CV4 7AL"),
            "Mansfield Palace Theatre": ("Mansfield Palace Theatre", "Mansfield", "NG18 1NG"),
            "Pavilion Arts Centre Buxton": ("Pavilion Arts Centre", "Buxton", "SK17 6BE"),
            "Town Hall Birmingham": ("Town Hall", "Birmingham", "B3 3DQ"),
            "Symphony Hall Birmingham": ("Symphony Hall", "Birmingham", "B1 2EA"),
            "Rugeley Rose Theatre": ("Rugeley Rose Theatre", "Rugeley", "WS15 2AA"),
            "Nottingham Arts Theatre": ("Nottingham Arts Theatre", "Nottingham", "NG1 3BE"),
            "Déda": ("Chapel Street Arts Centre", "Derby", "DE1 3GU"),
        }
        filters = {
            "Pavilion Arts Centre Buxton": "Pavilion Arts Centre",
            "Town Hall Birmingham": "Town Hall",
            "Symphony Hall Birmingham": "Symphony Hall",
            "Cadwell Park": "Cadwell Park",
        }
        dv, dt, dp = defaults.get(config.name, (None, None, None))
        common = {"source_name": config.name, "source_rank": config.source_rank}
        quality = {"default_venue": dv, "default_town": dt, "default_postcode": dp, "venue_filter": filters.get(config.name)}
        if config.connector == "ticketmaster":
            c = TicketmasterConnector(os.getenv("TICKETMASTER_API_KEY"), country_code="GB")
            c.source_name = config.name
            return c
        if config.connector == "skiddle":
            c = SkiddleConnector(
                os.getenv("SKIDDLE_API_KEY"),
                latitude=52.9548,
                longitude=-1.1581,
                radius_miles=110,
            )
            c.source_name = config.name
            return c
        if config.connector == "academy_music_group":
            return AcademyMusicGroupConnector(config.url, **common, **quality)
        if config.connector == "warwick_arts":
            return WarwickArtsCentreConnector(config.url, area=config.area, **common, **quality)
        if config.connector == "atg":
            return ATGConnector(config.url, **common)
        if config.connector == "trch":
            return TRCHConnector(config.url, **common)
        if config.connector == "rock_city":
            return RockCityConnector(config.url, **common)
        if config.connector == "national_trust":
            return NationalTrustConnector(
                config.url,
                venue_name=config.name,
                county=config.area,
                **common,
            )
        if config.connector == "english_heritage":
            return EnglishHeritageConnector(config.url, region=config.area or "Midlands", **common)
        if config.connector == "council_html":
            return CouncilHtmlConnector(config.url, area=config.area, **common)
        if config.connector == "tourism_calendar":
            return TourismCalendarConnector(config.url, area=config.area, **common)
        if config.connector == "structured_html":
            return StructuredHtmlConnector(config.url, area=config.area, **common, **quality)
        if config.connector == "paged_structured_html":
            return PagedStructuredHtmlConnector(config.url, area=config.area, **common, **quality)
        if config.connector == "ents24":
            return Ents24MidlandsConnector(config.url, **common)
        if config.connector == "notts":
            return NottsEventsConnector(config.url, **common)
        if config.connector == "see_tickets":
            return SeeTicketsMidlandsConnector(config.url, **common)
        if config.connector == "allevents_api":
            return AllEventsApiConnector(os.getenv("ALLEVENTS_API_KEY"), api_url=os.getenv("ALLEVENTS_API_URL"), **common)
        if config.connector == "secondary_venue_index":
            provider = "Artspod" if "New Theatre Royal" in config.name else "Gigantic"
            venue_name = "New Theatre Royal Lincoln" if "New Theatre Royal" in config.name else "The Engine Shed Lincoln"
            return SecondaryVenueIndexConnector(config.url, venue_name=venue_name, discovery_provider=provider, area=config.area, **common)
        if config.connector == "pazaz_projects":
            return PazazProjectsConnector(config.url, area=config.area, **common)
        if config.connector == "auto_spektrix":
            hints = []
            if "worcester" in config.domain.casefold():
                hints = ["worcestertheatres", "worcesterlive", "worcestertheatre"]
            return AutoSpektrixConnector(
                config.url, candidate_client_names=hints, **common
            )
        if config.connector == "bclm":
            return BlackCountryLivingMuseumConnector(config.url, area=config.area, **common)
        if config.connector == "legacy_spektrix":
            return LegacySpektrixEventListConnector(config.url, area=config.area, **common)
        if config.connector == "spektrix":
            # Spektrix rows remain in probe state until a live client name is validated.
            raise ValueError(f"Spektrix client name not validated for {config.name}")
        raise ValueError(f"Unsupported connector: {config.connector}")

    return make


def scheduled_source(config: SourceConfig) -> ScheduledSource:
    policy = DEFAULT_POLICIES.get(config.schedule_profile, DEFAULT_POLICIES["venue"])
    return ScheduledSource(config.name, connector_factory(config), policy)
