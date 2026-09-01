"""Editorial analysis rules for explaining why a story matters."""

import re

from editorial.utils import clean_text, contains_any, numbers_in_text


KNOWN_AREAS = (
    "Carlton-in-Lindrick",
    "Gringley on the Hill",
    "Dunham-on-Trent",
    "North Leverton",
    "South Leverton",
    "East Markham",
    "West Markham",
    "Harworth and Bircotes",
    "Harworth",
    "Bircotes",
    "Worksop",
    "Retford",
    "Tuxford",
    "Misterton",
    "Bawtry",
    "Blyth",
    "Langold",
    "Rhodesia",
    "Shireoaks",
    "Gateford",
    "Manton",
    "Beckingham",
    "Walkeringham",
    "Everton",
    "Mattersey",
    "Ranskill",
    "Rampton",
    "Bole",
    "Clarborough",
    "Hayton",
    "Gamston",
    "Elkesley",
    "Barnby Moor",
    "Scrooby",
    "Sutton cum Lound",
    "Sturton le Steeple",
    "Saundby",
    "Babworth",
    "Cuckney",
    "Welbeck",
)


def _extract_area(address):
    address_text = clean_text(address)

    if not address_text:
        return "Unknown area"

    for area in KNOWN_AREAS:
        if re.search(rf"\b{re.escape(area)}\b", address_text, re.IGNORECASE):
            return area

    parts = [part.strip() for part in address_text.split(",") if part.strip()]

    if len(parts) > 1:
        candidate = parts[-1]
        candidate = re.sub(
            r"\b(Nottinghamshire|Notts)\b",
            "",
            candidate,
            flags=re.IGNORECASE,
        )
        candidate = clean_text(candidate)

        if candidate:
            return candidate

    return "Other / not identified"


def why_is_it_news(app):
    """Return concise reasons why an application may be newsworthy."""
    text = f"{app.proposal} {app.category} {app.address}".lower()
    reasons = []

    housing_words = (
        "dwelling",
        "dwellings",
        "homes",
        "housing",
        "residential",
        "apartment",
        "apartments",
        "flat",
        "flats",
    )

    numbers = numbers_in_text(text)

    if contains_any(text, housing_words):
        dwelling_numbers = [value for value in numbers if 2 <= value <= 2000]
        largest = max(dwelling_numbers, default=0)

        if largest >= 100:
            reasons.append(
                f"Major housing proposal involving around {largest} homes"
            )
        elif largest >= 10:
            reasons.append(
                f"Significant residential proposal involving around {largest} homes"
            )
        else:
            reasons.append(
                "Residential development with local community interest"
            )

    if contains_any(text, ("battery", "energy storage", "bess")):
        reasons.append(
            "Strategic battery-storage or energy-infrastructure proposal"
        )

    if contains_any(
        text,
        ("solar", "photovoltaic", "renewable", "wind turbine"),
    ):
        reasons.append(
            "Renewable-energy development with environmental interest"
        )

    if contains_any(
        text,
        (
            "commercial",
            "employment",
            "industrial",
            "warehouse",
            "retail",
            "business unit",
            "factory",
        ),
    ):
        reasons.append(
            "Potential impact on jobs, investment, traffic or local business"
        )

    if contains_any(
        text,
        (
            "listed building",
            "heritage",
            "conservation area",
            "scheduled monument",
        ),
    ):
        reasons.append(
            "Affects a heritage asset or protected setting"
        )

    if contains_any(text, ("telecom", "mast", "antenna", "5g")):
        reasons.append(
            "Communications infrastructure likely to attract local interest"
        )

    if contains_any(
        text,
        (
            "school",
            "hospital",
            "medical centre",
            "health centre",
            "care home",
            "community centre",
        ),
    ):
        reasons.append(
            "Could affect an important local public or community service"
        )

    if contains_any(
        text,
        ("demolition", "outline application", "change of use"),
    ):
        reasons.append(
            "Represents a notable change to the use or appearance of the site"
        )

    area = _extract_area(app.address)

    if area not in ("Unknown area", "Other / not identified"):
        reasons.append(f"Direct relevance to residents in {area}")

    score = int(app.score or 0)

    if score >= 45:
        reasons.append(
            "Highest editorial priority based on the planning news score"
        )
    elif score >= 35:
        reasons.append(
            "Strong public-interest indicators in the planning news score"
        )
    elif score >= 25:
        reasons.append(
            "Meets the threshold for a standalone planning story"
        )

    unique_reasons = []
    seen = set()

    for reason in reasons:
        key = reason.lower()

        if key not in seen:
            seen.add(key)
            unique_reasons.append(reason)

    if not unique_reasons:
        unique_reasons.append(
            "Worth monitoring for local impact or public interest"
        )

    return unique_reasons[:5]