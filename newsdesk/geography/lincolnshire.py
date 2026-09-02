"""Central Lincolnshire geography boundary used across NewsDesk modules."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable


LINCOLNSHIRE_PLACES = (
    "Lincolnshire", "Lincoln", "Boston", "Grantham", "Spalding", "Skegness",
    "Gainsborough", "Sleaford", "Stamford", "Louth", "Horncastle", "Bourne",
    "Market Rasen", "Mablethorpe", "Alford", "Holbeach", "Long Sutton",
    "Woodhall Spa", "North Hykeham", "South Hykeham", "North Kesteven",
    "South Kesteven", "East Lindsey", "West Lindsey", "South Holland",
    "Lincoln Crown Court", "Lincoln Magistrates Court", "Boston Magistrates Court",
    "Lincoln Central", "Grantham station", "Sleaford station", "Spalding station",
    "Skegness station", "Boston station", "Gainsborough station", "Stamford station",
    "Cleethorpes", "Grimsby", "Scunthorpe", "Immingham", "Barton-upon-Humber",
    "Brigg", "Market Deeping", "The Deepings", "Caistor", "Wragby", "Coningsby",
    "Tattershall", "Metheringham", "Ruskington", "Heckington", "Billinghay",
    "Mablethorpe and Sutton", "Sutton on Sea", "Chapel St Leonards", "Ingoldmells",
    "Wainfleet", "Burgh le Marsh", "Woodhall", "Tetford", "Spilsby", "Donington",
    "Crowland", "Deeping St James", "Market Deeping", "Pinchbeck", "Gosberton",
    "Kirton", "Swineshead", "Frampton", "Wrangle", "Sibsey", "Tattershall",
    "Coningsby", "Navenby", "Bracebridge Heath", "Waddington", "Saxilby",
    "Skellingthorpe", "Welton", "Nettleham", "Dunholme", "Cherry Willingham",
    "Washingborough", "Bardney", "Sutton Bridge", "Gedney", "Moulton",
    "Crowle", "Epworth", "Kirton in Lindsey", "Barrow upon Humber", "New Holland",
    "Peaks Lane", "Waltham", "Winterton", "Immingham East", "Immingham West",
)


def _place_pattern(place: str) -> str:
    escaped = re.escape(place)
    return escaped.replace(r"\ ", r"[\s-]+")


_PATTERNS = tuple(
    (place, re.compile(r"(?<![A-Za-z0-9])" + _place_pattern(place) + r"(?![A-Za-z0-9])", re.I))
    for place in sorted(set(LINCOLNSHIRE_PLACES), key=len, reverse=True)
)


@dataclass(frozen=True, slots=True)
class LincolnshireMatch:
    matched: bool
    places: tuple[str, ...] = ()


def match_lincolnshire(values: Iterable[object]) -> LincolnshireMatch:
    """Return positive, explainable Lincolnshire place evidence."""

    text = " ".join(str(value or "") for value in values)
    matches = tuple(place for place, pattern in _PATTERNS if pattern.search(text))
    return LincolnshireMatch(bool(matches), matches)


def story_matches_lincolnshire(story) -> LincolnshireMatch:
    """Match the useful textual and structured fields of a Story-like object."""

    extras = getattr(story, "extras", {}) or {}
    return match_lincolnshire(
        (
            getattr(story, "title", ""),
            getattr(story, "summary", ""),
            getattr(story, "body", ""),
            getattr(story, "source", ""),
            getattr(story, "location", ""),
            " ".join(getattr(story, "tags", ()) or ()),
            extras.get("location", ""),
            extras.get("area", ""),
            extras.get("matched_place", ""),
            extras.get("source_description", ""),
            extras.get("source_organisation", ""),
            extras.get("organisation", ""),
        )
    )
