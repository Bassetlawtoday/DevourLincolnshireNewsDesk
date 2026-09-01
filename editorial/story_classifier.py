"""Editorial story classification shared across NewsDesk modules."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable


@dataclass
class EditorialClassification:
    """Structured editorial classification for a news story."""

    primary_category: str
    secondary_category: str
    crime_type: str
    severity: str
    victim_type: str
    story_type: str
    public_interest: str
    developing: bool
    matched_signals: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Return the classification as a serialisable dictionary."""

        return {
            "primary_category": self.primary_category,
            "secondary_category": self.secondary_category,
            "crime_type": self.crime_type,
            "severity": self.severity,
            "victim_type": self.victim_type,
            "story_type": self.story_type,
            "public_interest": self.public_interest,
            "developing": self.developing,
            "classification_signals": list(self.matched_signals),
        }


def _normalise_text(*values: object) -> str:
    """Combine and normalise story text for classification."""

    return " ".join(
        str(value or "")
        for value in values
    ).lower()


def _contains_phrase(text: str, phrase: str) -> bool:
    """Return True when a complete word or phrase is present."""

    pattern = rf"(?<!\w){re.escape(phrase.lower())}(?!\w)"

    return bool(
        re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        )
    )


def _first_match(
    text: str,
    rules: Iterable[tuple[str, tuple[str, ...]]],
    default: str,
    matched_signals: list[str],
) -> str:
    """
    Return the first classification whose phrases match the story text.

    Rules must be ordered from most specific to least specific.
    """

    for label, phrases in rules:
        for phrase in phrases:
            if _contains_phrase(text, phrase):
                matched_signals.append(phrase)
                return label

    return default


def _classify_primary_category(
    text: str,
    matched_signals: list[str],
) -> str:
    rules = (
        (
            "Homicide",
            (
                "murder",
                "manslaughter",
                "attempted murder",
                "suspicious death",
                "murder investigation",
            ),
        ),
        (
            "Fatal Collision",
            (
                "fatal collision",
                "fatal crash",
                "road death",
                "died following a collision",
                "death of",
                "causing death",
            ),
        ),
        (
            "Missing Person",
            (
                "missing person",
                "missing child",
                "missing teenager",
                "reported missing",
                "help find",
            ),
        ),
        (
            "Sexual Offence",
            (
                "rape",
                "sexual assault",
                "sexual offence",
                "indecent assault",
                "child sexual exploitation",
            ),
        ),
        (
            "Domestic Abuse",
            (
                "domestic abuse",
                "domestic violence",
                "controlling behaviour",
                "coercive behaviour",
            ),
        ),
        (
            "Firearms",
            (
                "firearm",
                "firearms",
                "gun",
                "shooting",
                "armed police",
            ),
        ),
        (
            "Knife Crime",
            (
                "knife",
                "knifepoint",
                "stabbing",
                "bladed article",
            ),
        ),
        (
            "Robbery",
            (
                "robbery",
                "robber",
                "robbed",
            ),
        ),
        (
            "Burglary",
            (
                "burglary",
                "burglar",
                "break-in",
                "broken into",
            ),
        ),
        (
            "Drug Crime",
            (
                "cannabis",
                "cocaine",
                "heroin",
                "class a drugs",
                "drug supply",
                "drugs factory",
                "county lines",
            ),
        ),
        (
            "Fraud",
            (
                "fraud",
                "scam",
                "cyber crime",
                "online fraud",
            ),
        ),
        (
            "Serious Collision",
            (
                "serious collision",
                "serious crash",
                "life-threatening injuries",
                "dangerous driving",
            ),
        ),
        (
            "Public Order",
            (
                "violent disorder",
                "public order",
                "affray",
                "disorder",
            ),
        ),
        (
            "Theft",
            (
                "theft",
                "stolen",
                "stealing",
                "shoplifting",
            ),
        ),
        (
            "Police Operation",
            (
                "operation",
                "crackdown",
                "warrant",
                "raids",
                "day of action",
            ),
        ),
        (
            "Community Policing",
            (
                "community event",
                "engagement event",
                "neighbourhood policing",
                "community engagement",
                "school visit",
            ),
        ),
        (
            "Recruitment",
            (
                "recruitment",
                "join the police",
                "police careers",
                "new officers",
            ),
        ),
        (
            "Award",
            (
                "award",
                "recognised",
                "commendation",
                "honoured",
            ),
        ),
    )

    return _first_match(
        text,
        rules,
        "General Police News",
        matched_signals,
    )


def _classify_secondary_category(
    text: str,
    matched_signals: list[str],
) -> str:
    rules = (
        (
            "Sentencing",
            (
                "sentenced",
                "jailed",
                "imprisoned",
                "prison sentence",
            ),
        ),
        (
            "Court",
            (
                "charged",
                "appeared in court",
                "due to appear",
                "remanded",
                "convicted",
                "found guilty",
            ),
        ),
        (
            "Public Appeal",
            (
                "appeal",
                "witnesses",
                "information",
                "cctv image",
                "recognise",
                "contact police",
            ),
        ),
        (
            "Investigation",
            (
                "investigation",
                "inquiries are ongoing",
                "detectives are investigating",
                "enquiries are ongoing",
            ),
        ),
        (
            "Operation",
            (
                "operation",
                "crackdown",
                "warrant",
                "raid",
            ),
        ),
        (
            "Warning",
            (
                "warning",
                "warned",
                "advice",
                "remain vigilant",
            ),
        ),
        (
            "Community",
            (
                "community",
                "engagement",
                "neighbourhood",
            ),
        ),
    )

    return _first_match(
        text,
        rules,
        "News Update",
        matched_signals,
    )


def _classify_crime_type(
    text: str,
    primary_category: str,
    matched_signals: list[str],
) -> str:
    category_map = {
        "Homicide": "Violence",
        "Fatal Collision": "Road Crime",
        "Serious Collision": "Road Crime",
        "Sexual Offence": "Sexual Crime",
        "Domestic Abuse": "Safeguarding",
        "Firearms": "Weapons",
        "Knife Crime": "Weapons",
        "Robbery": "Violence",
        "Burglary": "Property Crime",
        "Theft": "Property Crime",
        "Drug Crime": "Drug Crime",
        "Fraud": "Fraud and Cyber",
        "Missing Person": "Safeguarding",
        "Public Order": "Public Order",
    }

    mapped_type = category_map.get(primary_category)

    if mapped_type:
        return mapped_type

    rules = (
        (
            "Safeguarding",
            (
                "child exploitation",
                "modern slavery",
                "human trafficking",
                "vulnerable person",
            ),
        ),
        (
            "Violence",
            (
                "assault",
                "attack",
                "violence",
                "injured",
            ),
        ),
        (
            "Road Crime",
            (
                "dangerous driving",
                "drink driving",
                "drug driving",
                "police pursuit",
            ),
        ),
        (
            "Property Crime",
            (
                "criminal damage",
                "vehicle theft",
                "stolen vehicle",
            ),
        ),
    )

    return _first_match(
        text,
        rules,
        "Unknown",
        matched_signals,
    )


def _classify_victim_type(
    text: str,
    matched_signals: list[str],
) -> str:
    rules = (
        (
            "Child",
            (
                "child",
                "young child",
                "boy aged",
                "girl aged",
            ),
        ),
        (
            "Teenager",
            (
                "teenager",
                "teenage boy",
                "teenage girl",
                "17-year-old",
                "16-year-old",
                "15-year-old",
                "14-year-old",
                "13-year-old",
            ),
        ),
        (
            "Elderly",
            (
                "elderly",
                "pensioner",
                "older person",
                "oap",
                "in his 70s",
                "in her 70s",
                "in his 80s",
                "in her 80s",
                "in his 90s",
                "in her 90s",
            ),
        ),
        (
            "Police Officer",
            (
                "police officer",
                "officer assaulted",
                "officer injured",
            ),
        ),
        (
            "Business",
            (
                "business",
                "shop worker",
                "store employee",
                "retailer",
            ),
        ),
        (
            "Community",
            (
                "residents",
                "local community",
                "members of the public",
            ),
        ),
        (
            "Adult",
            (
                "man",
                "woman",
                "victim",
            ),
        ),
    )

    return _first_match(
        text,
        rules,
        "None Identified",
        matched_signals,
    )


def _classify_severity(
    text: str,
    primary_category: str,
    victim_type: str,
    matched_signals: list[str],
) -> str:
    critical_categories = {
        "Homicide",
        "Fatal Collision",
    }

    high_categories = {
        "Serious Collision",
        "Sexual Offence",
        "Firearms",
        "Knife Crime",
        "Domestic Abuse",
        "Missing Person",
    }

    if primary_category in critical_categories:
        return "Critical"

    if _contains_phrase(text, "life-threatening injuries"):
        matched_signals.append("life-threatening injuries")
        return "Critical"

    if primary_category in high_categories:
        return "High"

    if victim_type in {"Child", "Teenager", "Elderly"}:
        return "High"

    if primary_category in {
        "Robbery",
        "Burglary",
        "Drug Crime",
        "Fraud",
        "Public Order",
    }:
        return "Medium"

    return "Low"


def _classify_story_type(
    text: str,
    severity: str,
    secondary_category: str,
    matched_signals: list[str],
) -> str:
    breaking_phrases = (
        "currently at the scene",
        "ongoing incident",
        "road remains closed",
        "just happened",
        "emergency services are at the scene",
    )

    for phrase in breaking_phrases:
        if _contains_phrase(text, phrase):
            matched_signals.append(phrase)
            return "Breaking"

    if severity == "Critical" and secondary_category in {
        "Investigation",
        "Public Appeal",
        "Court",
    }:
        return "Developing"

    if secondary_category in {
        "Investigation",
        "Public Appeal",
    }:
        return "Developing"

    if secondary_category in {
        "Sentencing",
        "Court",
        "Operation",
        "News Update",
    }:
        return "Routine"

    if secondary_category == "Warning":
        return "Evergreen"

    if secondary_category == "Community":
        return "Feature"

    return "Routine"


def _classify_public_interest(
    primary_category: str,
    severity: str,
    victim_type: str,
) -> str:
    if severity == "Critical":
        return "Very High"

    if severity == "High":
        return "High"

    if victim_type in {
        "Child",
        "Teenager",
        "Elderly",
    }:
        return "High"

    if primary_category in {
        "Robbery",
        "Burglary",
        "Drug Crime",
        "Fraud",
        "Police Operation",
    }:
        return "Medium"

    return "Low"



def _classify_fire_story(
    text: str,
    matched_signals: list[str],
) -> tuple[str, str, str, str, str, str]:
    """Return Fire-specific editorial classifications.

    The tuple contains primary category, secondary category, incident type,
    severity, story type and public-interest level.  This helper is only used
    when ``classify_story(module="fire")`` is requested, so existing Police
    classification behaviour remains unchanged.
    """

    primary_rules = (
        ("Fatal Fire", ("fatal fire", "died in the fire", "died following a fire", "person has died")),
        ("Major Fire", ("major fire", "large fire", "significant fire", "multiple fire crews", "ten fire engines", "eight fire engines")),
        ("House Fire", ("house fire", "flat fire", "bungalow fire", "residential fire", "domestic property")),
        ("Industrial Fire", ("industrial fire", "factory fire", "warehouse fire", "commercial building fire", "business premises")),
        ("Wildfire", ("wildfire", "grass fire", "heath fire", "moorland fire", "woodland fire")),
        ("Road Traffic Collision", ("road traffic collision", "rtc", "vehicle collision", "car crash", "road collision")),
        ("Water Rescue", ("water rescue", "river rescue", "flood rescue", "person in the water")),
        ("Animal Rescue", ("animal rescue", "horse rescue", "dog rescue", "cat rescue")),
        ("Shed or Outbuilding Fire", ("shed fire", "garage fire", "outbuilding fire")),
        ("Vehicle Fire", ("vehicle fire", "car fire", "van fire", "lorry fire")),
        ("Chimney Fire", ("chimney fire",)),
        ("Safety Warning", ("safety warning", "fire safety advice", "safety advice", "warning issued")),
        ("Community and Prevention", ("community event", "school visit", "fire prevention", "safe and well visit")),
        ("Recruitment", ("recruitment", "join the fire service", "firefighter careers")),
        ("Award", ("award", "commendation", "recognised", "honoured")),
    )
    primary = _first_match(text, primary_rules, "General Fire and Rescue News", matched_signals)

    secondary_rules = (
        ("Live Incident", ("currently at the scene", "ongoing incident", "crews remain at the scene", "incident is ongoing")),
        ("Investigation", ("fire investigation", "cause of the fire", "investigation is underway", "investigation is ongoing")),
        ("Road Closure", ("road remains closed", "road is closed", "road closure")),
        ("Rescue", ("rescued", "rescue operation", "released from the vehicle")),
        ("Safety Advice", ("safety advice", "warning", "remain vigilant")),
        ("Community", ("community", "engagement", "school visit")),
    )
    secondary = _first_match(text, secondary_rules, "Incident Update", matched_signals)

    critical = primary == "Fatal Fire" or any(
        _contains_phrase(text, phrase)
        for phrase in ("life-threatening injuries", "multiple fatalities", "major incident declared")
    )
    high = primary in {"Major Fire", "House Fire", "Industrial Fire", "Wildfire", "Road Traffic Collision", "Water Rescue"}

    if critical:
        severity = "Critical"
    elif high or any(_contains_phrase(text, phrase) for phrase in ("serious injuries", "evacuated", "six fire engines", "seven fire engines")):
        severity = "High"
    elif primary in {"Vehicle Fire", "Shed or Outbuilding Fire", "Animal Rescue"}:
        severity = "Medium"
    else:
        severity = "Low"

    if secondary == "Live Incident" or any(_contains_phrase(text, phrase) for phrase in ("breaking", "major incident declared")):
        story_type = "Breaking"
    elif secondary in {"Investigation", "Road Closure"} or severity == "Critical":
        story_type = "Developing"
    elif primary in {"Safety Warning", "Community and Prevention"} or secondary in {"Safety Advice", "Community"}:
        story_type = "Evergreen"
    else:
        story_type = "Routine"

    if severity == "Critical":
        public_interest = "Very High"
    elif severity == "High":
        public_interest = "High"
    elif severity == "Medium":
        public_interest = "Medium"
    else:
        public_interest = "Low"

    incident_type = {
        "Fatal Fire": "Fire Incident",
        "Major Fire": "Fire Incident",
        "House Fire": "Fire Incident",
        "Industrial Fire": "Fire Incident",
        "Wildfire": "Fire Incident",
        "Shed or Outbuilding Fire": "Fire Incident",
        "Vehicle Fire": "Fire Incident",
        "Chimney Fire": "Fire Incident",
        "Road Traffic Collision": "Rescue Incident",
        "Water Rescue": "Rescue Incident",
        "Animal Rescue": "Rescue Incident",
        "Safety Warning": "Prevention",
        "Community and Prevention": "Prevention",
        "Recruitment": "Corporate",
        "Award": "Corporate",
    }.get(primary, "Fire and Rescue")

    return primary, secondary, incident_type, severity, story_type, public_interest

def classify_story(
    *,
    title: str = "",
    summary: str = "",
    body: str = "",
    location: str = "",
    module: str = "",
) -> EditorialClassification:
    """
    Classify a story using its headline, summary, body and location.

    The classifier is deliberately independent of scraper models so it can
    later be reused by Police, Fire, Council and social-media modules.
    """

    text = _normalise_text(
        title,
        summary,
        body,
        location,
    )

    matched_signals: list[str] = []

    if str(module or "").strip().casefold() == "fire":
        (
            primary_category,
            secondary_category,
            crime_type,
            severity,
            story_type,
            public_interest,
        ) = _classify_fire_story(text, matched_signals)

        victim_type = _classify_victim_type(text, matched_signals)
        developing = story_type in {"Breaking", "Developing"}

        return EditorialClassification(
            primary_category=primary_category,
            secondary_category=secondary_category,
            crime_type=crime_type,
            severity=severity,
            victim_type=victim_type,
            story_type=story_type,
            public_interest=public_interest,
            developing=developing,
            matched_signals=sorted(set(matched_signals)),
        )

    primary_category = _classify_primary_category(
        text,
        matched_signals,
    )

    secondary_category = _classify_secondary_category(
        text,
        matched_signals,
    )

    crime_type = _classify_crime_type(
        text,
        primary_category,
        matched_signals,
    )

    victim_type = _classify_victim_type(
        text,
        matched_signals,
    )

    severity = _classify_severity(
        text,
        primary_category,
        victim_type,
        matched_signals,
    )

    story_type = _classify_story_type(
        text,
        severity,
        secondary_category,
        matched_signals,
    )

    public_interest = _classify_public_interest(
        primary_category,
        severity,
        victim_type,
    )

    developing = story_type in {
        "Breaking",
        "Developing",
    }

    return EditorialClassification(
        primary_category=primary_category,
        secondary_category=secondary_category,
        crime_type=crime_type,
        severity=severity,
        victim_type=victim_type,
        story_type=story_type,
        public_interest=public_interest,
        developing=developing,
        matched_signals=sorted(set(matched_signals)),
    )