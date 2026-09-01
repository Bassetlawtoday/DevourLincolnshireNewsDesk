from __future__ import annotations

from dataclasses import dataclass
from .connectors import (
    AcademyMusicGroupConnector,
    ATGConnector,
    EnglishHeritageConnector,
    NationalTrustConnector,
    RockCityConnector,
    TRCHConnector,
    VisitNottinghamshireConnector,
)


@dataclass(frozen=True)
class VenueSource:
    name: str
    url: str
    connector: type
    rank: int = 20
    kwargs: dict | None = None


SOURCES = [
    VenueSource("O2 Academy Leicester", "https://www.academymusicgroup.com/o2academyleicester/events", AcademyMusicGroupConnector),
    VenueSource("O2 Academy Birmingham", "https://www.academymusicgroup.com/o2academybirmingham/events", AcademyMusicGroupConnector),
    VenueSource("O2 Institute Birmingham", "https://www.academymusicgroup.com/o2institutebirmingham/events", AcademyMusicGroupConnector),
    VenueSource("Regent Theatre Stoke", "https://www.atgtickets.com/venues/regent-theatre/whats-on/", ATGConnector),
    VenueSource("Victoria Hall Stoke", "https://www.atgtickets.com/venues/victoria-hall/whats-on/", ATGConnector),
    VenueSource("Theatre Royal & Royal Concert Hall Nottingham", "https://www.trch.co.uk/whats-on", TRCHConnector, 10),
    VenueSource("Rock City Nottingham", "https://rock-city.co.uk/gig-guide/", RockCityConnector, 10),
]

NETWORK_SOURCES = [
    VenueSource("Visit Nottinghamshire", "https://www.visit-nottinghamshire.co.uk/whats-on", VisitNottinghamshireConnector, 24),
    VenueSource(
        "National Trust - Clumber Park",
        "https://www.nationaltrust.org.uk/visit/nottinghamshire-lincolnshire/clumber-park/events",
        NationalTrustConnector,
        15,
        {"venue_name": "Clumber Park", "town": "Worksop", "county": "Nottinghamshire"},
    ),
    VenueSource(
        "English Heritage - Midlands",
        "https://www.english-heritage.org.uk/visit/region/midlands/",
        EnglishHeritageConnector,
        18,
        {"region": "Midlands"},
    ),
]


def _build(source: VenueSource):
    kwargs = dict(source.kwargs or {})
    kwargs.setdefault("source_name", source.name)
    kwargs.setdefault("source_rank", source.rank)
    return source.connector(source.url, **kwargs)


def build_venue_connectors():
    return [_build(s) for s in SOURCES]


def build_network_connectors():
    return [_build(s) for s in NETWORK_SOURCES]
