"""Conservative, editable Instagram hashtag suggestions for newsroom copy."""

from __future__ import annotations

import re


_PLACES = (
    "Gainsborough", "Lincoln", "Scunthorpe", "Grimsby", "Cleethorpes",
    "Boston", "Skegness", "Spalding", "Grantham", "Sleaford", "Stamford",
    "Louth", "Horncastle", "Market Rasen", "Mablethorpe", "Bourne",
    "Woodhall Spa", "Brigg", "Barton upon Humber", "Immingham",
)

_AUTHORITY_FOR_PLACE = {
    "gainsborough": "WestLindsey",
    "market rasen": "WestLindsey",
    "lincoln": "Lincoln",
    "scunthorpe": "NorthLincolnshire",
    "brigg": "NorthLincolnshire",
    "barton upon humber": "NorthLincolnshire",
    "grimsby": "NorthEastLincolnshire",
    "cleethorpes": "NorthEastLincolnshire",
    "immingham": "NorthEastLincolnshire",
    "boston": "Boston",
    "skegness": "EastLindsey",
    "louth": "EastLindsey",
    "horncastle": "EastLindsey",
    "mablethorpe": "EastLindsey",
    "spalding": "SouthHolland",
    "grantham": "SouthKesteven",
    "stamford": "SouthKesteven",
    "bourne": "SouthKesteven",
    "sleaford": "NorthKesteven",
}

_TOPICS = (
    (("cinema", "film"), "Cinema"),
    (("planning", "development", "housing"), "Planning"),
    (("council", "councillor"), "LocalDemocracy"),
    (("business", "shop", "retail"), "Business"),
    (("event", "festival", "concert", "show"), "WhatsOn"),
    (("police", "crime", "court"), "LincolnshirePolice"),
    (("fire", "firefighter"), "LincolnshireFire"),
    (("football", "sport", "match"), "LincolnshireSport"),
    (("heritage", "history", "historic"), "LincolnshireHistory"),
)

_VENUE_ENDINGS = (
    "Cinema", "Theatre", "Museum", "Gallery", "Market", "Hospital",
    "University", "College", "School", "Academy", "Club", "Centre",
    "Center", "Hall", "Castle", "Cathedral", "Park", "Stadium",
)


def _tag(value: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", str(value or ""))
    return "#" + "".join(word[:1].upper() + word[1:] for word in words) if words else ""


def _append(tags: list[str], value: str) -> None:
    tag = _tag(value)
    if tag and len(tag) <= 40 and tag.casefold() not in {item.casefold() for item in tags}:
        tags.append(tag)


def suggest_instagram_hashtags(title: str, text: str, *, limit: int = 8) -> str:
    """Suggest a small set of location, organisation and subject hashtags."""
    headline = str(title or "").strip()
    content = f"{headline}\n{text or ''}"
    folded = content.casefold()
    tags: list[str] = []

    ending_pattern = "|".join(re.escape(value) for value in _VENUE_ENDINGS)
    venue_pattern = re.compile(
        rf"\b(?:[A-Z][A-Za-z0-9'’-]*\s+){{0,4}}(?:{ending_pattern})\b"
    )
    for match in venue_pattern.finditer(headline):
        candidate = match.group(0).strip()
        if len(candidate.split()) >= 2:
            _append(tags, candidate)

    matched_places: list[str] = []
    for place in _PLACES:
        if re.search(rf"\b{re.escape(place.casefold())}\b", folded):
            matched_places.append(place)
            _append(tags, place)
    for place in matched_places:
        authority = _AUTHORITY_FOR_PLACE.get(place.casefold())
        if authority:
            _append(tags, authority)

    for keywords, tag in _TOPICS:
        if any(re.search(rf"\b{re.escape(keyword)}\b", folded) for keyword in keywords):
            _append(tags, tag)

    _append(tags, "Lincolnshire")
    _append(tags, "Lincolnshire News")
    _append(tags, "Local News")
    return " ".join(tags[: max(1, limit)])


def normalise_hashtags(value: str, *, limit: int = 12) -> str:
    """Return unique valid hashtags from an editor-controlled field."""
    tags: list[str] = []
    for raw in re.findall(r"#?[A-Za-z0-9][A-Za-z0-9_-]*", str(value or "")):
        _append(tags, raw.lstrip("#").replace("_", " ").replace("-", " "))
    return " ".join(tags[:limit])


__all__ = ["normalise_hashtags", "suggest_instagram_hashtags"]
