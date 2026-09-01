"""Shared editorial priority scoring for every NewsDesk module."""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Iterable, Mapping

from editorial.settings_manager import load_editorial_settings


LOGGER = logging.getLogger(__name__)


_BASSETLAW_SPORT_ENTITY_ALIASES: dict[str, tuple[str, ...]] = {
    "Worksop Town": (
        "worksop town",
        "worksop town fc",
        "worksop town football club",
        "worksop tigers",
        "wtfc",
        "the tigers",
    ),
    "Retford FC": (
        "retford fc",
        "retford football club",
        "retford choughs",
        "the choughs",
    ),
    "Retford United": (
        "retford united",
        "retford united fc",
        "retford united football club",
        "retford badgers",
        "the badgers",
    ),
    "Harworth Colliery": (
        "harworth colliery",
        "harworth colliery fc",
        "harworth colliery football club",
        "harworth fc",
    ),
    "SJR Worksop": (
        "sjr worksop",
        "sjr worksop fc",
        "sjr worksop football club",
        "sjr",
        "the saints",
    ),
    "Worksop Rugby Club": (
        "worksop rugby club",
        "worksop rugby",
        "worksop rufc",
        "worksop rugby union football club",
    ),
    "East Retford Rugby Club": (
        "east retford rugby club",
        "east retford rugby union football club",
        "east retford rufc",
        "retford rugby club",
        "retford rugby",
    ),
    "Worksop Cricket Club": (
        "worksop cricket club",
        "worksop cricket",
        "worksop cc",
    ),
    "Retford Cricket Club": (
        "retford cricket club",
        "retford cricket",
        "retford cc",
    ),
    "Bassetlaw Cricket": (
        "bassetlaw cricket",
        "bassetlaw cricket club",
        "bassetlaw cricket league",
    ),
    "Worksop Harriers": (
        "worksop harriers",
        "worksop harriers and athletic club",
        "worksop harriers athletic club",
    ),
    "Bassetlaw Bulldogs": (
        "bassetlaw bulldogs",
        "bassetlaw bulldogs rlfc",
    ),
    "Worksop Cricket and Sports Club": (
        "worksop cricket and sports club",
    ),
    "Bassetlaw Swim Squad": (
        "bassetlaw swim squad",
    ),
    "Cuckney Cricket Club": (
        "cuckney cricket club",
        "cuckney cc",
    ),
    "Ordsall Bridon Cricket Club": (
        "ordsall bridon cricket club",
        "ordsall bridon cc",
    ),
    "Rockware Cricket Club": (
        "rockware cricket club",
        "rockware cc",
    ),
    "Welbeck Cricket Club": (
        "welbeck cricket club",
        "welbeck cc",
    ),
    "Worksop Squash Club": (
        "worksop squash club",
    ),
    "Worksop Flat Green Bowls": (
        "worksop flat green bowls",
    ),
    "Worksop Crown Green Bowls": (
        "worksop crown green bowls",
    ),
}

_BASSETLAW_LOCAL_BONUS = 100
_BASSETLAW_LOCALITY_BOOSTS = {
    "club": _BASSETLAW_LOCAL_BONUS,
    "title": 75,
    "source_or_tags": 50,
    "story_text": 25,
}

_BASSETLAW_LOCALITY_TERMS = (
    "bassetlaw",
    "worksop",
    "retford",
    "harworth",
    "bircotes",
    "misterton",
    "carlton-in-lindrick",
    "carlton in lindrick",
    "langold",
    "tuxford",
    "east markham",
    "ordsall",
    "cuckney",
    "welbeck",
)

_SPORT_COMPETITIVE_PATTERNS = (
    (
        "competition report",
        35,
        ("match report", "race report", "competition report"),
    ),
    (
        "squad announcement",
        35,
        (
            "signing",
            "signs",
            "signed",
            "transfer",
            "appointed",
            "appointment",
            "contract",
            "squad announcement",
            "names squad",
        ),
    ),
    (
        "competitive result",
        30,
        (
            "result",
            "victory",
            "defeat",
            "draw",
            "win",
            "wins",
            "won",
            "loss",
            "qualification",
            "qualifies",
            "qualified",
        ),
    ),
    (
        "sporting achievement",
        15,
        (
            "medal",
            "record",
            "personal best",
            "championship",
            "promotion",
            "promoted",
        ),
    ),
)

_SPORT_ADMINISTRATIVE_PATTERNS = (
    (
        "training information",
        -35,
        ("training session", "training timetable", "training schedule"),
    ),
    (
        "club governance",
        -40,
        ("committee", "agm", "annual general meeting", "governance", "constitution"),
    ),
    (
        "membership information",
        -30,
        ("membership", "registration", "how to join", "join the club"),
    ),
    (
        "commercial promotion",
        -30,
        ("merchandise", "club shop", "kit sale", "on sale", "commercial promotion"),
    ),
    (
        "club social event",
        -25,
        ("social event", "fundraiser", "fundraising event", "clubhouse event"),
    ),
    (
        "volunteer recruitment",
        -20,
        ("volunteers wanted", "volunteer recruitment", "volunteer with us"),
    ),
)

_SPORT_SCORE_PATTERN = re.compile(
    r"(?<![\d-])\d{1,3}\s*[-\u2013\u2014]\s*\d{1,2}(?!\s*[-\u2013\u2014]\s*\d)(?!\d)"
)
_SPORT_NAMED_PERSON_PATTERN = re.compile(
    r"(?:\b(?:player|athlete|manager|coach)\s+"
    r"[A-Z][a-z]+(?:[-'][A-Z]?[a-z]+)?\s+"
    r"[A-Z][a-z]+(?:[-'][A-Z]?[a-z]+)?\b|"
    r"\b[A-Z][a-z]+(?:[-'][A-Z]?[a-z]+)?\s+"
    r"[A-Z][a-z]+(?:[-'][A-Z]?[a-z]+)?\s+"
    r"(?:signs|joins|appointed|wins|qualifies|retires)\b)"
)

_SPORT_ADJUSTMENT_MARKERS = {
    "locality": "sport-locality-adjustment:",
    "competitive": "sport-competitive-adjustment:",
    "administrative": "sport-administrative-adjustment:",
    "module4": "sport-module4-adjustment:",
    "relevance": "sport-relevance-adjustment:",
    "content_type": "sport-content-type-adjustment:",
    "local_competitive": "sport-local-competitive-adjustment:",
}

_AMBIGUOUS_BASSETLAW_ALIASES = {
    "the saints", "the tigers", "the badgers", "the choughs",
}
_SPORT_RELEVANCE_ADJUSTMENTS = {
    "bassetlaw": 60,
    "regional": 20,
    "national": -25,
    "international_remote": -90,
}
_SPORT_LOCAL_COMPETITIVE_BONUS = 25
_SPORT_FEATURE_PENALTY = -35
_SPORT_CURRENT_FEATURE_PENALTY = -10
_SPORT_FEATURE_PATTERNS = (
    "club history", "history of", "heritage", "anniversary",
    "celebrates its anniversary", "100 years", "125 years", "centenary",
    "memories", "looking back", "from the archive", "archive",
    "hall of fame", "club legend feature", "former players",
    "where are they now", "why worksop", "why retford",
    "story of the club", "museum", "historical significance",
    "founded in", "our history",
)
_SPORT_HISTORICAL_RETROSPECTIVE_PATTERN = re.compile(
    r"\b(?:19\d{2}|200\d|201\d)\b"
)
_SPORT_HISTORICAL_RETROSPECTIVE_TERMS = (
    "glory", "classic", "archive", "remember", "looking back",
    "highlights from",
)
_SPORT_SPECULATIVE_APPOINTMENT_TERMS = (
    "could be appointed", "could become", "tipped to become",
    "in line to become", "linked with", "favourite for",
    "expected to be appointed",
)
_SPORT_TITLE_ONLY_CONFIG_SIGNALS = {
    "derby", "local derby", "manager appointed", "new manager",
    "record signing", "signs for", "signing", "contract extension",
    "new contract", "title win",
}
_SPORT_CURRENT_FEATURE_PATTERNS = (
    "opens", "launches", "announces", "announced", "unveils",
    "major event", "exhibition opens", "anniversary match",
    "anniversary celebration this weekend",
)
_SPORT_RELEVANCE_RANKS = {
    "international_remote": 0,
    "national": 1,
    "regional": 2,
    "bassetlaw": 3,
}
_REGIONAL_SPORT_TERMS = (
    "nottinghamshire", "south yorkshire", "derbyshire", "lincolnshire",
    "nottingham", "mansfield", "newark", "sheffield", "rotherham",
    "doncaster", "chesterfield", "gainsborough", "scunthorpe",
)
_EXCEPTIONAL_NATIONAL_SPORT_TERMS = (
    "england", "great britain", "team gb", "gb call-up", "olympics",
    "olympic", "paralympics", "paralympic", "commonwealth games",
    "national championship", "national champions", "national governing body",
    "fa cup final", "wimbledon", "six nations",
)
_REMOTE_SPORT_TERMS = (
    "foreign domestic", "overseas club", "serie a", "la liga", "bundesliga",
    "ligue 1",
)
_REMOTE_SPORT_IDENTITY_TERMS = (
    "italian", "spanish", "german", "french", "portuguese", "dutch",
    "belgian", "turkish", "saudi", "american", "australian",
)

_SPORT_MODULE4_LOCAL_IMPACT = 30
_SPORT_MODULE4_CATEGORY_CAPS = {
    "derby_rivalry": 80, "cup_stage": 55, "promotion_relegation": 60,
    "championship_trophy": 55, "records_milestones": 35,
    "representative_honours": 45, "management_changes": 35,
    "player_movement": 40, "injuries_availability": 35,
    "retirement_departure": 35, "major_result": 35,
    "fixture_importance": 50,
}

_SPORT_MODULE4_RULES = {
    "promotion_relegation": (
        (60, ("promotion secured", "promotion confirmed", "secure promotion", "secures promotion", "win promotion", "title and promotion", "promotion-clinching")),
        (55, ("relegation confirmed", "relegated")),
        (45, ("play-off final", "playoff final")),
        (40, ("relegation avoided", "survival secured", "secure survival", "stay up")),
        (30, ("play-off qualification", "playoff qualification")),
        (25, ("relegation battle", "must-win")),
    ),
    "championship_trophy": (
        (55, ("crowned national champions", "become national champions", "confirmed national champions", "win national championship", "national title secured")),
        (45, ("crowned regional champions", "crowned county champions", "win regional championship", "win county championship", "championship won", "win league title", "league title secured", "title secured", "trophy won", "cup winners")),
        (30, ("runners-up", "runner-up")),
        (20, ("tournament winners",)),
    ),
    "records_milestones": (
        (35, ("club record", "league record", "competition record", "course record")),
        (30, ("personal best", "season best", "fastest time", "highest score")),
        (25, ("milestone appearance", "landmark appearance", "milestone goal", "hat-trick", "hat trick", "century", "five-wicket haul", "five wicket haul")),
        (15, ("clean sheet", "unbeaten run", "winning streak")),
    ),
    "representative_honours": (
        (45, ("england call-up", "selected for england", "great britain call-up", "selected for great britain", "gb call-up", "international debut", "international selection", "international appearance")),
        (35, ("national selection", "national medal", "representative squad")),
        (30, ("county selection", "county call-up", "regional selection", "academy selection")),
        (25, ("gold medal",)), (20, ("silver medal", "bronze medal", "medal winner")),
        (15, ("sporting award", "sports award")),
    ),
    "management_changes": (
        (35, ("appointed manager", "new manager", "manager appointed", "head coach appointed", "coaching appointment", "named as manager", "named as head coach", "becomes manager", "becomes head coach", "confirmed as manager", "confirmed as head coach", "takes charge", "joins as head coach")),
        (30, ("manager leaves", "manager departs", "manager resigns", "manager sacked")),
        (20, ("interim manager", "captain appointed", "vice-captain appointed", "vice captain appointed", "contract extension")),
    ),
    "player_movement": (
        (40, ("signing", "sign", "signs", "signed", "transfer", "joins", "returns to club", "go for experience")),
        (30, ("loan", "contract renewal", "contract extension", "retained list")),
        (25, ("released", "departure", "leaves")),
        (20, ("trialist", "squad announcement")),
    ),
    "injuries_availability": (
        (35, ("season-ending injury", "season ending injury", "long-term injury", "long term injury", "ruled out for season")),
        (25, ("serious injury", "ruled out", "surgery", "player suspended", "match suspension", "disciplinary suspension", "sidelined")),
        (20, ("injury return", "returns from injury")), (10, ("fitness doubt",)),
    ),
    "retirement_departure": (
        (35, ("announces retirement", "player retires", "athlete retires", "manager retires", "coach retires")),
        (30, ("final appearance", "farewell appearance")),
        (25, ("testimonial", "club legend departs", "long-serving player leaves", "steps down")),
    ),
    "major_result": (
        (35, ("title-deciding", "promotion-clinching", "survival-clinching", "qualification secured")),
        (30, ("upset", "shock win", "comeback", "remarkable comeback", "penalty shoot-out win", "penalty shootout win")),
        (25, ("record win", "record defeat", "heavy defeat", "emphatic win")),
        (20, ("last-minute winner", "late winner", "extra-time victory")),
        (15, ("unbeaten run", "winning streak", "losing streak")),
    ),
}

_SPORT_MODULE4_CONFIG_GROUPS = {
    "derby_rivalry": {"derby", "local derby"},
    "promotion_relegation": {"promotion", "promoted", "relegation", "relegated", "play-off final", "playoff final"},
    "championship_trophy": {"champions", "title win"},
    "management_changes": {"manager appointed", "new manager", "manager sacked", "manager dismissed", "contract extension", "new contract"},
    "player_movement": {"record signing", "signing", "signs for", "contract extension", "new contract"},
    "injuries_availability": {"serious injury", "career-ending injury"},
}

_SPORT_EDITORIAL_CLASSES = {
    "international_remote": -1,
    "national": 0,
    "surrounding": 1,
    "bassetlaw_area": 2,
    "bassetlaw_event": 3,
    "bassetlaw_person": 4,
    "bassetlaw_club": 5,
}

_SPORT_EDITORIAL_LABELS = {
    -1: "International / Remote",
    0: "National / International",
    1: "Surrounding Area",
    2: "Bassetlaw Area",
    3: "Bassetlaw Event",
    4: "Bassetlaw Person",
    5: "Bassetlaw Club",
}


# Module defaults are used only when a profile is not present in
# data/editorial_settings.json. Existing configured profiles always win.
_DEFAULT_MODULE_PROFILES: dict[str, dict] = {
    "fire": {
        "inherit_global_signals": True,
        "zone_scores": {
            "bassetlaw": 70,
            "surrounding": 20,
            "county": 5,
            "other": 0,
        },
        "signals": {
            "fatal fire": 40,
            "fatality": 35,
            "serious injury": 30,
            "house fire": 25,
            "flat fire": 25,
            "building fire": 20,
            "industrial fire": 20,
            "large fire": 20,
            "major incident": 30,
            "explosion": 30,
            "evacuation": 25,
            "rescued": 20,
            "rescue": 15,
            "persons reported": 25,
            "road traffic collision": 20,
            "rtc": 20,
            "road closed": 15,
            "road closure": 15,
            "wildfire": 15,
            "flooding": 15,
            "hazardous materials": 20,
            "chemical incident": 20,
            "multiple crews": 10,
            "six appliances": 15,
            "five appliances": 12,
            "four appliances": 10,
            "three appliances": 7,
            "school": 15,
            "hospital": 20,
            "care home": 20,
            "business premises": 10,
        },
    },
    "sport": {
        "inherit_global_signals": False,
        "zone_scores": {
            "bassetlaw": 25,
            "surrounding": 10,
            "county": 5,
            "other": 0,
        },
        "thresholds": {
            "front_page": 80,
            "high_priority": 60,
            "newsworthy": 35,
            "monitor": 20,
        },
        "signals": {
            "club folds": 75,
            "club folded": 75,
            "liquidation": 70,
            "administration": 65,
            "points deduction": 55,
            "promotion": 55,
            "promoted": 55,
            "relegation": 50,
            "relegated": 50,
            "title win": 50,
            "play-off final": 45,
            "playoff final": 45,
            "fa cup draw": 40,
            "cup draw": 30,
            "manager sacked": 50,
            "manager dismissed": 50,
            "manager appointed": 45,
            "new manager": 40,
            "record signing": 45,
            "signs for": 30,
            "signing": 25,
            "contract extension": 15,
            "new contract": 15,
            "derby": 25,
            "local derby": 30,
            "match abandoned": 35,
            "fixture postponed": 20,
            "match postponed": 20,
            "serious injury": 30,
            "career-ending": 45,
            "international call-up": 25,
            "international call up": 25,
            "fa trophy": 25,
            "fa vase": 25,
            "county cup": 15,
            "women's team": 15,
            "ladies team": 15,
            "girls team": 15,
            "youth team": 12,
            "academy": 10,
            "grassroots": 15,
            "community": 8,
            "charity": 10,
            "q&a": -15,
            "question and answer": -15,
            "ticket information": -20,
            "tickets on sale": -15,
            "hospitality": -20,
            "sponsorship": -15,
            "sponsor": -10,
            "commercial partnership": -20,
            "club shop": -20,
            "merchandise": -20,
            "season tickets": -10,
            "fixture list": -10,
            "match preview": -5,
            "interview": -5,
        },
        "source_weights": {
            "worksop town": 25,
            "retford united": 25,
            "retford fc": 25,
            "harworth colliery": 25,
            "sjr worksop": 25,
            "doncaster rovers": 10,
            "gainsborough trinity": 8,
            "mansfield town": 8,
            "nottingham forest": 6,
            "notts county": 6,
            "sheffield united": 5,
            "sheffield wednesday": 5,
            "scunthorpe united": 4,
            "lincoln city": 4,
            "lincoln united": 3,
            "boston united": 3,
            "alfreton town": 3,
            "bbc football": 0,
            "bbc cricket": -3,
            "bbc rugby union": -3,
            "bbc rugby league": -3,
            "bbc motorsport": -3,
        },
    },
}


@dataclass
class PriorityResult:
    """The complete priority assessment returned by :func:`score_story`."""

    score: int
    rating: int
    level: str
    zone_key: str
    zone_label: str
    matched_place: str | None
    reasons: list[str] = field(default_factory=list)
    matched_signals: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Return the established story-extras mapping used by NewsDesk."""

        return {
            "priority_score": self.score,
            "priority_rating": self.rating,
            "priority_level": self.level,
            "editorial_zone": self.zone_key,
            "editorial_zone_label": self.zone_label,
            "matched_place": self.matched_place,
            "priority_reasons": list(self.reasons),
            "matched_signals": list(self.matched_signals),
        }


def _normalise_text(*values: object) -> str:
    return " ".join(str(value or "") for value in values).casefold()


def _contains_phrase(text: str, phrase: str) -> bool:
    phrase = str(phrase or "").strip().casefold()
    if not phrase:
        return False

    return bool(
        re.search(
            rf"(?<!\w){re.escape(phrase)}(?!\w)",
            text,
            flags=re.IGNORECASE,
        )
    )


def _as_mapping(value: object) -> Mapping:
    return value if isinstance(value, Mapping) else {}


def _as_int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _module_profile(settings: dict, module: str) -> dict:
    module_key = str(module or "default").strip().casefold() or "default"
    profiles = _as_mapping(settings.get("module_profiles"))

    configured = profiles.get(module_key)
    if isinstance(configured, Mapping):
        return dict(configured)

    built_in = _DEFAULT_MODULE_PROFILES.get(module_key)
    if built_in is not None:
        default_profile = _as_mapping(profiles.get("default"))
        merged = dict(default_profile)
        merged.update(built_in)
        return merged

    default_profile = profiles.get("default")
    return dict(default_profile) if isinstance(default_profile, Mapping) else {}


def _identify_zone(
    text: str,
    settings: dict,
    profile: dict,
) -> tuple[str, str, str | None, int]:
    zones = _as_mapping(settings.get("zones"))
    zone_scores = _as_mapping(profile.get("zone_scores"))

    for zone_key, raw_zone in zones.items():
        zone = _as_mapping(raw_zone)
        places = zone.get("places", ())
        if not isinstance(places, (list, tuple, set)):
            continue

        # Prefer the most specific place name where names overlap.
        ordered_places = sorted(
            (str(place).strip() for place in places if str(place).strip()),
            key=len,
            reverse=True,
        )

        for place in ordered_places:
            if _contains_phrase(text, place):
                score = _as_int(
                    zone_scores.get(zone_key, zone.get("score", 0))
                )
                label = str(zone.get("label", str(zone_key).title()))
                return str(zone_key), label, place, score

    return (
        "other",
        "Outside Priority Area",
        None,
        _as_int(zone_scores.get("other", 0)),
    )


def _thresholds(settings: dict, profile: dict) -> dict[str, int]:
    source = _as_mapping(profile.get("thresholds"))
    if not source:
        source = _as_mapping(settings.get("thresholds"))

    return {
        "front_page": _as_int(source.get("front_page"), 80),
        "high_priority": _as_int(source.get("high_priority"), 60),
        "newsworthy": _as_int(source.get("newsworthy"), 35),
        "monitor": _as_int(source.get("monitor"), 20),
    }


def _priority_level(score: int, thresholds: Mapping[str, int]) -> str:
    if score >= thresholds["front_page"]:
        return "Front Page"
    if score >= thresholds["high_priority"]:
        return "High Priority"
    if score >= thresholds["newsworthy"]:
        return "Newsworthy"
    if score >= thresholds["monitor"]:
        return "Monitor"
    return "Low Priority"


def _star_rating(score: int, thresholds: Mapping[str, int]) -> int:
    if score >= thresholds["front_page"]:
        return 5
    if score >= thresholds["high_priority"]:
        return 4
    if score >= thresholds["newsworthy"]:
        return 3
    if score >= thresholds["monitor"]:
        return 2
    return 1


def _source_weight(profile: dict, source: str) -> tuple[int, str | None]:
    """Return the most specific configured source weight."""

    source_text = str(source or "").strip().casefold()
    if not source_text:
        return 0, None

    rules = _as_mapping(profile.get("source_weights"))
    matches: list[tuple[str, int]] = []

    for name, raw_weight in rules.items():
        key = str(name or "").strip().casefold()
        if key and key in source_text:
            matches.append((key, _as_int(raw_weight)))

    if not matches:
        return 0, None

    name, weight = max(matches, key=lambda item: len(item[0]))
    return weight, name


def _signal_rules(settings: dict, profile: dict, module: str) -> dict[str, int]:
    inherit_global = bool(profile.get("inherit_global_signals", True))
    global_rules = (
        _as_mapping(settings.get("global_signals")) if inherit_global else {}
    )

    profile_rules = _as_mapping(profile.get("signals"))
    if not profile_rules:
        legacy_modules = _as_mapping(settings.get("modules"))
        profile_rules = _as_mapping(legacy_modules.get(module.casefold()))

    combined: dict[str, int] = {}
    for phrase, weight in global_rules.items():
        key = str(phrase).strip().casefold()
        if key:
            combined[key] = _as_int(weight)

    for phrase, weight in profile_rules.items():
        key = str(phrase).strip().casefold()
        if key:
            combined[key] = _as_int(weight)

    return combined



@dataclass
class _BassetlawLocalityAssessment:
    is_bassetlaw: bool = False
    club: str | None = None
    place: str | None = None
    evidence: list[str] = field(default_factory=list)
    weak_aliases_ignored: list[str] = field(default_factory=list)


@dataclass
class _SportRelevanceAssessment:
    zone: str
    adjustment: int
    reason: str
    exceptional_national_interest: bool = False


@dataclass
class _SportContentAssessment:
    content_type: str
    feature_penalty: int = 0
    feature_signal: str | None = None
    current_signal: str | None = None


def _sport_content_assessment(
    *, title: object, summary: object, module4_high_value: bool,
    genuine_competitive_signal: bool, routine_administrative: bool,
) -> _SportContentAssessment:
    """Classify timeliness without treating evergreen features as breaking news."""

    text = _normalise_text(title, summary)
    if routine_administrative:
        return _SportContentAssessment("administrative_promotional")

    historical_retrospective = (
        _SPORT_HISTORICAL_RETROSPECTIVE_PATTERN.search(_normalise_text(title))
        and _matched_pattern(_normalise_text(title), _SPORT_HISTORICAL_RETROSPECTIVE_TERMS)
    )
    feature_signal = (
        f"historical retrospective ({historical_retrospective})"
        if historical_retrospective
        else _matched_pattern(text, _SPORT_FEATURE_PATTERNS)
    )
    current_feature_signal = _matched_pattern(text, _SPORT_CURRENT_FEATURE_PATTERNS)
    if feature_signal:
        if current_feature_signal:
            return _SportContentAssessment(
                "current_club_news", _SPORT_CURRENT_FEATURE_PENALTY,
                feature_signal, current_feature_signal,
            )
        return _SportContentAssessment(
            "feature_heritage", _SPORT_FEATURE_PENALTY, feature_signal,
        )

    if module4_high_value or genuine_competitive_signal:
        return _SportContentAssessment("current_competitive")
    return _SportContentAssessment("current_club_news")


def _sport_editorial_precedence(*, relevance_zone: str, content_type: str) -> int:
    """Return a close-score tie-breaker led by publishability."""

    if content_type == "administrative_promotional":
        return 1
    if content_type == "feature_heritage":
        return 2
    if relevance_zone == "bassetlaw":
        return 7 if content_type == "current_competitive" else 6
    return {"regional": 5, "national": 4, "international_remote": 3}.get(
        relevance_zone, 0
    )


def _exact_bassetlaw_club(*values: object) -> str | None:
    """Match a source or organisation that exactly names a local club."""

    normalised_values = {_normalise_text(value) for value in values if _normalise_text(value)}
    for canonical_name, aliases in _BASSETLAW_SPORT_ENTITY_ALIASES.items():
        approved = {_normalise_text(canonical_name)} | {
            _normalise_text(alias)
            for alias in aliases
            if alias not in _AMBIGUOUS_BASSETLAW_ALIASES
        }
        if normalised_values & approved:
            return canonical_name
    return None


def _title_bassetlaw_clubs(title: object, *, supporting_identifier: bool) -> set[str]:
    """Return title clubs, ignoring unsupported generic nicknames."""

    title_text = _normalise_text(title)
    clubs: set[str] = set()
    for canonical_name, aliases in _BASSETLAW_SPORT_ENTITY_ALIASES.items():
        for alias in aliases:
            if alias in _AMBIGUOUS_BASSETLAW_ALIASES and not supporting_identifier:
                continue
            if _contains_phrase(title_text, alias):
                clubs.add(canonical_name)
                break
    return clubs


def _assess_bassetlaw_locality(
    *, title: object, source: object, organisation: object = "",
    tags: object = (), location: object = "", summary: object = "", body: object = "",
) -> _BassetlawLocalityAssessment:
    """Return the authoritative strong-evidence Bassetlaw assessment."""

    assessment = _BassetlawLocalityAssessment()
    source_club = _exact_bassetlaw_club(source, organisation)
    title_place = _matched_bassetlaw_locality(title)
    context_place = _matched_bassetlaw_locality(source, organisation, tags, location)
    supporting_identifier = bool(source_club or title_place or context_place)
    title_clubs = _title_bassetlaw_clubs(title, supporting_identifier=supporting_identifier)

    for alias in _AMBIGUOUS_BASSETLAW_ALIASES:
        if _contains_phrase(title, alias) and not supporting_identifier:
            assessment.weak_aliases_ignored.append(alias)

    if source_club:
        assessment.club = source_club
        assessment.evidence.append(f"exact source/organisation: {source_club}")
    elif title_clubs:
        assessment.club = sorted(title_clubs)[0]
        assessment.evidence.append(f"recognised club in title: {assessment.club}")

    if title_place:
        assessment.place = title_place
        assessment.evidence.append(f"locality in title: {title_place}")
    elif context_place:
        assessment.place = context_place
        assessment.evidence.append(f"explicit source/tag/location: {context_place}")

    assessment.is_bassetlaw = bool(assessment.club or assessment.place)
    # Summary/body matches are diagnostic context only and never establish locality.
    if not assessment.is_bassetlaw and _matched_bassetlaw_locality(summary, body):
        assessment.evidence.append("summary/body locality ignored without strong evidence")
    return assessment


def _matched_bassetlaw_club(*values: object) -> str | None:
    """Compatibility helper for strong exact or unambiguous club evidence."""

    exact = _exact_bassetlaw_club(*values)
    if exact:
        return exact
    clubs = _title_bassetlaw_clubs(_normalise_text(*values), supporting_identifier=False)
    return sorted(clubs)[0] if clubs else None


def _matched_bassetlaw_locality(*values: object) -> str | None:
    """Return the most specific Bassetlaw locality found in supplied text."""

    text = _normalise_text(*values)
    matches = [
        term
        for term in _BASSETLAW_LOCALITY_TERMS
        if _contains_phrase(text, term)
    ]
    return max(matches, key=len) if matches else None


def _sport_locality_adjustment(
    *,
    title: object,
    source: object,
    tags: object,
    summary: object,
    body: object,
    location: object,
    organisation: object = "",
    assessment: _BassetlawLocalityAssessment | None = None,
) -> tuple[int, str | None, str | None]:
    """Apply only the strongest available Bassetlaw locality signal."""

    assessment = assessment or _assess_bassetlaw_locality(
        title=title, source=source, organisation=organisation, tags=tags,
        summary=summary, body=body, location=location,
    )
    if assessment.club:
        return (
            _BASSETLAW_LOCALITY_BOOSTS["club"],
            assessment.club,
            f"Bassetlaw sports organisation: {assessment.club}",
        )

    if assessment.place and _matched_bassetlaw_locality(title):
        return (
            _BASSETLAW_LOCALITY_BOOSTS["title"],
            None,
            f"Bassetlaw locality in title: {assessment.place}",
        )

    if assessment.place:
        return (
            _BASSETLAW_LOCALITY_BOOSTS["source_or_tags"],
            None,
            f"Bassetlaw locality in source or tags: {assessment.place}",
        )
    return 0, None, None


def _matched_pattern(text: str, patterns: Iterable[str]) -> str | None:
    """Return the longest matching phrase from one editorial signal group."""

    matches = [phrase for phrase in patterns if _contains_phrase(text, phrase)]
    return max(matches, key=len) if matches else None


@dataclass
class _SportModule4Result:
    adjustments: dict[str, int] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)
    caps_applied: list[str] = field(default_factory=list)
    duplicates_suppressed: list[str] = field(default_factory=list)
    suppressed_module2: set[str] = field(default_factory=set)
    suppressed_config_signals: set[str] = field(default_factory=set)
    local_impact: int = 0

    @property
    def total(self) -> int:
        return sum(self.adjustments.values()) + self.local_impact

    @property
    def is_high_value(self) -> bool:
        return bool(self.adjustments)


def _matched_bassetlaw_clubs_in_title(title: str) -> set[str]:
    """Return distinct recognised clubs conservatively identified in a title."""

    strong_clubs = _title_bassetlaw_clubs(title, supporting_identifier=False)
    return _title_bassetlaw_clubs(
        title,
        supporting_identifier=bool(strong_clubs or _matched_bassetlaw_locality(title)),
    )


def _strongest_module4_rule(text: str, rules: Iterable[tuple[int, Iterable[str]]]) -> tuple[int, str | None, int]:
    matches = [
        (weight, phrase)
        for weight, phrases in rules
        for phrase in phrases
        if _contains_phrase(text, phrase)
    ]
    if not matches:
        return 0, None, 0
    weight, phrase = max(matches, key=lambda match: (match[0], len(match[1])))
    return weight, phrase, len(matches)


def _sport_module4_adjustment(*, title: str, summary: str, locality_adjustment: int) -> _SportModule4Result:
    """Return one capped adjustment per advanced sport-news category."""

    result = _SportModule4Result()
    title_text = _normalise_text(title)
    text = _normalise_text(title, summary)
    historical_retrospective = bool(
        _SPORT_HISTORICAL_RETROSPECTIVE_PATTERN.search(title_text)
        and _matched_pattern(title_text, _SPORT_HISTORICAL_RETROSPECTIVE_TERMS)
    )
    speculative_appointment = bool(
        _matched_pattern(text, _SPORT_SPECULATIVE_APPOINTMENT_TERMS)
    )

    def add(category: str, weight: int, phrase: str, match_count: int = 1) -> None:
        weight = min(weight, _SPORT_MODULE4_CATEGORY_CAPS[category])
        result.adjustments[category] = weight
        result.reasons.append(f"Module 4 {category.replace('_', ' ')} ({phrase}): +{weight}")
        if match_count > 1:
            result.caps_applied.append(category)
            result.duplicates_suppressed.append(f"{category}:{match_count - 1}")
        result.suppressed_config_signals.update(_SPORT_MODULE4_CONFIG_GROUPS.get(category, ()))

    clubs = _matched_bassetlaw_clubs_in_title(title)
    rivalry = _matched_pattern(title_text, ("all-bassetlaw clash", "cross-town clash", "local derby", "local rivals", "derby"))
    if len(clubs) >= 2 and rivalry:
        add("derby_rivalry", 80, f"{rivalry}; two Bassetlaw clubs", 2)
    elif len(clubs) >= 2:
        add("derby_rivalry", 65, "two Bassetlaw clubs")
    elif rivalry:
        add("derby_rivalry", 45, rivalry)

    non_sporting_final = _matched_pattern(text, ("final training session", "final reminder", "final details", "final agm"))
    cup_rules = (
        (55, ("cup final", "play-off final", "playoff final", "championship final", "tournament final", "grand final")),
        (40, ("semi-final", "semi final")), (30, ("quarter-final", "quarter final")),
        (20, ("cup tie", "cup match", "knockout", "qualifier", "qualifying round", "preliminary round", "first round", "second round", "third round", "replay", "extra time", "penalty shoot-out", "penalty shootout")),
    )
    weight, phrase, count = _strongest_module4_rule(text, cup_rules)
    if weight and not non_sporting_final and not historical_retrospective:
        add("cup_stage", weight, phrase or "cup stage", count)

    for category, rules in _SPORT_MODULE4_RULES.items():
        rule_text = (
            title_text
            if category in {"player_movement", "management_changes"}
            else text
        )
        if category == "records_milestones":
            rule_text = re.sub(r"\bhalf[- ]century\b", "", rule_text)
        weight, phrase, count = _strongest_module4_rule(rule_text, rules)
        if category == "promotion_relegation" and _matched_pattern(text, ("promotion offer", "commercial promotion")):
            weight = 0
            result.duplicates_suppressed.append("promotion_relegation:commercial-language")
            result.suppressed_module2.add("sporting achievement")
            result.suppressed_config_signals.update(("promotion", "promoted"))
        if (
            category == "championship_trophy"
            and phrase in {"national championship", "regional championship", "county championship"}
            and not _matched_pattern(text, ("win", "wins", "won", "champion", "secured", "claimed", "takes", "lands"))
        ):
            weight = 0
            result.duplicates_suppressed.append("championship_trophy:preview-or-entry")
        if category == "management_changes" and _matched_pattern(text, ("volunteer coach", "volunteer coaching")):
            weight = 0
        if category == "management_changes" and speculative_appointment:
            weight = 0
            result.suppressed_module2.add("squad announcement")
            result.suppressed_config_signals.update(
                ("manager appointed", "new manager")
            )
            result.duplicates_suppressed.append(
                "management_changes:speculative-language"
            )
        if historical_retrospective and category in {
            "championship_trophy", "major_result"
        }:
            weight = 0
        if weight:
            add(category, weight, phrase or category, count)

    suspension = re.search(r"\bsuspended for \d+ matches?\b", title_text)
    if suspension and result.adjustments.get("injuries_availability", 0) < 25:
        add("injuries_availability", 25, suspension.group(0))

    milestone = re.search(r"\b(?:50th|100th|200th) appearance\b|\b(?:50|100) goals\b", text)
    if milestone and result.adjustments.get("records_milestones", 0) < 25:
        add("records_milestones", 25, milestone.group(0))

    fixture_context = _matched_pattern(text, ("match preview", "fixture", "upcoming", "ahead of", "set to face", "fixture reminder"))
    if fixture_context and not _contains_phrase(text, "routine fixture reminder"):
        fixture_rules = (
            (50, ("cup final", "play-off final", "playoff final", "championship final")),
            (40, ("semi-final", "semi final")),
            (35, ("play-off", "playoff", "promotion decider", "relegation decider", "title decider")),
            (25, ("derby", "cup tie")), (20, ("final home game",)), (15, ("season opener",)),
        )
        weight, phrase, count = _strongest_module4_rule(text, fixture_rules)
        if weight and not non_sporting_final:
            add("fixture_importance", weight, phrase or fixture_context, count)

    suppression = {
        "player_movement": "squad announcement",
        "management_changes": "squad announcement",
        "major_result": "competitive result",
        "promotion_relegation": "sporting achievement",
        "championship_trophy": "sporting achievement",
        "records_milestones": "sporting achievement",
        "representative_honours": "sporting achievement",
    }
    for category in result.adjustments:
        if category in suppression:
            result.suppressed_module2.add(suppression[category])
    if historical_retrospective:
        result.suppressed_module2.update(
            ("competitive result", "sporting achievement")
        )
        result.suppressed_config_signals.update(
            ("champions", "title win")
        )
        result.duplicates_suppressed.append("historical-retrospective")
    result.duplicates_suppressed.extend(f"module2:{label}" for label in sorted(result.suppressed_module2))

    if result.is_high_value and locality_adjustment:
        result.local_impact = _SPORT_MODULE4_LOCAL_IMPACT
        result.reasons.append(f"Module 4 Bassetlaw high-value story: +{result.local_impact}")
    return result


def _sport_competitive_adjustment(
    *,
    title: str,
    summary: str,
    suppressed_categories: set[str] | None = None,
) -> tuple[int, list[str], bool]:
    """Return conservative high-value sports journalism adjustments."""

    text = _normalise_text(title, summary)
    adjustment = 0
    reasons: list[str] = []
    genuine_competitive_signal = False

    suppressed_categories = suppressed_categories or set()
    for label, weight, patterns in _SPORT_COMPETITIVE_PATTERNS:
        if label in suppressed_categories:
            continue
        pattern_text = _normalise_text(title) if label == "squad announcement" else text
        phrase = _matched_pattern(pattern_text, patterns)
        if not phrase:
            continue
        adjustment += weight
        reasons.append(f"{label.title()} ({phrase}): +{weight}")
        genuine_competitive_signal = True

    if _SPORT_SCORE_PATTERN.search(_normalise_text(title)):
        adjustment += 25
        reasons.append("Recognisable sport score: +25")
        genuine_competitive_signal = True

    if _SPORT_NAMED_PERSON_PATTERN.search(str(title or "")):
        adjustment += 20
        reasons.append("Named sportsperson or coach in title: +20")

    return adjustment, reasons, genuine_competitive_signal


def _sport_administrative_adjustment(
    *,
    title: str,
    summary: str,
    genuine_competitive_signal: bool,
) -> tuple[int, list[str], bool]:
    """Return title/summary penalties for routine club administration."""

    text = _normalise_text(title, summary)
    adjustment = 0
    reasons: list[str] = []

    for label, weight, patterns in _SPORT_ADMINISTRATIVE_PATTERNS:
        phrase = _matched_pattern(text, patterns)
        if not phrase:
            continue
        adjustment += weight
        reasons.append(f"{label.title()} ({phrase}): {weight}")

    fixture_phrase = _matched_pattern(
        text,
        ("fixture reminder", "fixture information", "upcoming fixture", "next fixture"),
    )
    if fixture_phrase and not genuine_competitive_signal:
        adjustment -= 20
        reasons.append(f"Generic fixture reminder ({fixture_phrase}): -20")

    return adjustment, reasons, adjustment < 0


def _stored_sport_adjustment(
    signals: Iterable[object],
    adjustment_type: str,
) -> int | None:
    """Read an internal sport adjustment marker from existing metadata."""

    prefix = _SPORT_ADJUSTMENT_MARKERS[adjustment_type]
    for signal in signals:
        text = str(signal or "").strip().casefold()
        if text.startswith(prefix):
            return _as_int(text[len(prefix):])
    return None


def _replace_sport_adjustment_markers(
    signals: Iterable[object],
    *,
    locality: int,
    competitive: int,
    administrative: int,
    module4: int,
    relevance: int,
    content_type: int,
    local_competitive: int,
) -> list[str]:
    """Replace internal adjustment markers while retaining public reasons."""

    prefixes = tuple(_SPORT_ADJUSTMENT_MARKERS.values())
    result = [
        str(signal)
        for signal in signals
        if not str(signal or "").strip().casefold().startswith(prefixes)
    ]
    result.extend(
        (
            f"{_SPORT_ADJUSTMENT_MARKERS['locality']}{locality}",
            f"{_SPORT_ADJUSTMENT_MARKERS['competitive']}{competitive}",
            f"{_SPORT_ADJUSTMENT_MARKERS['administrative']}{administrative}",
            f"{_SPORT_ADJUSTMENT_MARKERS['module4']}{module4}",
            f"{_SPORT_ADJUSTMENT_MARKERS['relevance']}{relevance}",
            f"{_SPORT_ADJUSTMENT_MARKERS['content_type']}{content_type}",
            f"{_SPORT_ADJUSTMENT_MARKERS['local_competitive']}{local_competitive}",
        )
    )
    return sorted(set(result))


def _sport_relevance_assessment(
    *, locality: _BassetlawLocalityAssessment, title: object, source: object,
    organisation: object = "", tags: object = (), location: object = "",
) -> _SportRelevanceAssessment:
    """Classify publication relevance independently of sporting excitement."""

    if locality.is_bassetlaw:
        return _SportRelevanceAssessment(
            "bassetlaw", _SPORT_RELEVANCE_ADJUSTMENTS["bassetlaw"],
            "strong Bassetlaw evidence",
        )

    context = _normalise_text(title, source, organisation, tags, location)
    regional_term = _matched_pattern(context, _REGIONAL_SPORT_TERMS)
    if regional_term:
        return _SportRelevanceAssessment(
            "regional", _SPORT_RELEVANCE_ADJUSTMENTS["regional"],
            f"regional interest: {regional_term}",
        )

    exceptional = _matched_pattern(context, _EXCEPTIONAL_NATIONAL_SPORT_TERMS)
    if exceptional:
        return _SportRelevanceAssessment(
            "national", 0, f"exceptional national interest: {exceptional}", True,
        )

    remote_term = _matched_pattern(context, _REMOTE_SPORT_TERMS)
    if not remote_term:
        remote_term = _matched_pattern(
            _normalise_text(organisation, tags, location),
            _REMOTE_SPORT_IDENTITY_TERMS,
        )
    if remote_term:
        return _SportRelevanceAssessment(
            "international_remote",
            _SPORT_RELEVANCE_ADJUSTMENTS["international_remote"],
            f"remote foreign domestic sport: {remote_term}",
        )

    return _SportRelevanceAssessment(
        "national", _SPORT_RELEVANCE_ADJUSTMENTS["national"],
        "UK-wide or non-local sport without exceptional national interest",
    )



def _sport_editorial_class(
    *,
    zone_key: str,
    local_club: str | None,
) -> tuple[int, str, str]:
    """
    Return the deterministic Sport Intelligence editorial classification.

    Pass 1 deliberately uses only evidence already produced by the current
    engine: recognised Bassetlaw clubs and the configured editorial zone.
    Later passes can refine Bassetlaw Person and Bassetlaw Event detection
    without changing the public ranking API.
    """

    if local_club:
        rank = _SPORT_EDITORIAL_CLASSES["bassetlaw_club"]
        return (
            rank,
            _SPORT_EDITORIAL_LABELS[rank],
            f"Recognised Bassetlaw sports entity: {local_club}",
        )

    zone = str(zone_key or "other").strip().casefold()

    if zone == "international_remote":
        rank = _SPORT_EDITORIAL_CLASSES["international_remote"]
        return rank, _SPORT_EDITORIAL_LABELS[rank], "Remote international story"

    if zone == "bassetlaw":
        rank = _SPORT_EDITORIAL_CLASSES["bassetlaw_area"]
        return (
            rank,
            _SPORT_EDITORIAL_LABELS[rank],
            "Story has a Bassetlaw location connection",
        )

    if zone in {"surrounding", "county"}:
        rank = _SPORT_EDITORIAL_CLASSES["surrounding"]
        return (
            rank,
            _SPORT_EDITORIAL_LABELS[rank],
            "Story is connected to the surrounding editorial area",
        )

    rank = _SPORT_EDITORIAL_CLASSES["national"]
    return (
        rank,
        _SPORT_EDITORIAL_LABELS[rank],
        "No Bassetlaw or surrounding-area connection detected",
    )


def _published_datetime(value: object) -> datetime | None:
    """Convert common RSS and ISO publication values to an aware datetime."""

    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value or "").strip()

        if not text:
            return None

        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except (TypeError, ValueError):
            try:
                parsed = parsedate_to_datetime(text)
            except (TypeError, ValueError, OverflowError):
                return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


def _recency_adjustment(value: object) -> tuple[int, str]:
    """Return a modest ranking adjustment based on publication age."""

    published = _published_datetime(value)

    if published is None:
        return -5, "Publication date unavailable: -5"

    age_days = max(
        0,
        (datetime.now(timezone.utc) - published).days,
    )

    if age_days == 0:
        return 10, "Published today: +10"
    if age_days == 1:
        return 8, "Published yesterday: +8"
    if age_days == 2:
        return 6, "Published 2 days ago: +6"
    if age_days == 3:
        return 4, "Published 3 days ago: +4"
    if age_days <= 7:
        return 0, "Published within 7 days: +0"
    if age_days <= 14:
        return -10, "Published 8–14 days ago: -10"

    return -25, "Published more than 14 days ago: -25"


def score_story(
    *,
    module: str,
    title: str = "",
    summary: str = "",
    body: str = "",
    location: str = "",
    source: str = "",
    extra_signals: Iterable[str] | None = None,
    base_score: int = 0,
) -> PriorityResult:
    """Score one story while preserving the established public API.

    Configured module profiles remain authoritative. Built-in Fire and Sport
    profiles are used only when the settings file does not define those modules.
    The optional ``source`` argument is backward-compatible and allows local
    sports sources to receive an editorial relevance weighting.
    """

    settings = load_editorial_settings()
    if not isinstance(settings, dict):
        settings = {}

    module_key = str(module or "default").strip().casefold() or "default"
    profile = _module_profile(settings, module_key)
    text = _normalise_text(title, summary, body, location)
    extra_signal_values = tuple(extra_signals or ())

    starting_score = _as_int(base_score)
    score = starting_score
    reasons: list[str] = []
    matched_signals: list[str] = []
    applied_signals: set[str] = set()

    zone_key, zone_label, matched_place, zone_score = _identify_zone(
        text,
        settings,
        profile,
    )
    score += zone_score

    if zone_score:
        reasons.append(f"{zone_label}: +{zone_score}")
        if matched_place:
            reasons.append(f"Location matched: {matched_place}")

    source_score, matched_source = _source_weight(profile, source)
    score += source_score
    if matched_source and source_score:
        reasons.append(
            f"Source: {matched_source.title()}: {source_score:+d}"
        )

    locality_adjustment = 0
    competitive_adjustment = 0
    administrative_penalty = 0
    module4_result = _SportModule4Result()
    locality_assessment = _BassetlawLocalityAssessment()
    relevance = _SportRelevanceAssessment("national", 0, "not assessed")
    content = _SportContentAssessment("current_club_news")
    local_competitive_bonus = 0
    final_cap: str | None = None
    routine_administrative = False
    genuine_competitive_signal = False

    if module_key == "sport":
        locality_assessment = _assess_bassetlaw_locality(
            title=title, source=source, tags=extra_signal_values,
            summary=summary, body=body, location=location,
        )
        relevance = _sport_relevance_assessment(
            locality=locality_assessment, title=title, source=source,
            tags=extra_signal_values, location=location,
        )
        if zone_key == "bassetlaw" and not locality_assessment.is_bassetlaw:
            score -= zone_score
            zone_score = 0
        zone_key = {
            "bassetlaw": "bassetlaw", "regional": "surrounding",
            "national": "other", "international_remote": "other",
        }[relevance.zone]
        zone_label = {
            "bassetlaw": "Bassetlaw", "regional": "Regional",
            "national": "National", "international_remote": "International / Remote",
        }[relevance.zone]
        matched_place = locality_assessment.place
        (
            locality_adjustment,
            local_club,
            locality_reason,
        ) = _sport_locality_adjustment(
            title=title,
            source=source,
            tags=extra_signal_values,
            summary=summary,
            body=body,
            location=location,
            assessment=locality_assessment,
        )
        if locality_adjustment and zone_key == "bassetlaw" and zone_score:
            score -= zone_score
            reasons.append(
                "Configured Bassetlaw zone score absorbed into locality boost: "
                f"-{zone_score}"
            )
        if (
            locality_adjustment
            and source_score
            and (
                _matched_bassetlaw_club(source)
                or _matched_bassetlaw_locality(source)
            )
        ):
            score -= source_score
            reasons.append(
                "Configured local source score absorbed into locality boost: "
                f"{-source_score:+d}"
            )
        score += locality_adjustment
        if locality_reason:
            reasons.append(f"{locality_reason}: +{locality_adjustment}")
            matched_signals.append("bassetlaw locality priority")

        module4_result = _sport_module4_adjustment(
            title=title,
            summary=summary,
            locality_adjustment=locality_adjustment,
        )
        score += module4_result.total
        reasons.extend(module4_result.reasons)

        (
            competitive_adjustment,
            competitive_reasons,
            genuine_competitive_signal,
        ) = _sport_competitive_adjustment(
            title=title,
            summary=summary,
            suppressed_categories=module4_result.suppressed_module2,
        )
        score += competitive_adjustment
        reasons.extend(competitive_reasons)
        if competitive_adjustment:
            matched_signals.append("competitive sports journalism")

        (
            administrative_penalty,
            administrative_reasons,
            routine_administrative,
        ) = _sport_administrative_adjustment(
            title=title,
            summary=summary,
            genuine_competitive_signal=(
                genuine_competitive_signal or module4_result.is_high_value
            ),
        )
        score += administrative_penalty
        reasons.extend(administrative_reasons)
        if administrative_penalty:
            matched_signals.append("routine club administration")

    signal_rules = _signal_rules(settings, profile, module_key)

    # Longer phrases are checked first so the reasons are easier to understand.
    for phrase in sorted(signal_rules, key=len, reverse=True):
        if module_key == "sport" and phrase == "champions":
            continue
        if module_key == "sport" and phrase in module4_result.suppressed_config_signals:
            signal_text = (
                _normalise_text(title)
                if phrase in _SPORT_TITLE_ONLY_CONFIG_SIGNALS
                else text
            )
            if _contains_phrase(signal_text, phrase):
                module4_result.duplicates_suppressed.append(f"configured:{phrase}")
            continue
        signal_text = (
            _normalise_text(title)
            if module_key == "sport" and phrase in _SPORT_TITLE_ONLY_CONFIG_SIGNALS
            else text
        )
        if phrase in applied_signals or not _contains_phrase(signal_text, phrase):
            continue

        weight = signal_rules[phrase]
        if not weight:
            continue

        score += weight
        applied_signals.add(phrase)
        matched_signals.append(phrase)
        reasons.append(f"{phrase.title()}: {weight:+d}")

    for signal in extra_signal_values:
        phrase = str(signal or "").strip().casefold()
        if not phrase or phrase in applied_signals:
            continue
        if module_key == "sport" and phrase == "champions":
            continue
        if module_key == "sport" and phrase in module4_result.suppressed_config_signals:
            module4_result.duplicates_suppressed.append(f"configured-extra:{phrase}")
            continue

        weight = signal_rules.get(phrase, 0)
        if not weight:
            continue

        score += weight
        applied_signals.add(phrase)
        matched_signals.append(phrase)
        reasons.append(f"{phrase.title()}: {weight:+d}")

    thresholds = _thresholds(settings, profile)

    if module_key == "sport":
        content = _sport_content_assessment(
            title=title,
            summary=summary,
            module4_high_value=module4_result.is_high_value,
            genuine_competitive_signal=genuine_competitive_signal,
            routine_administrative=routine_administrative,
        )
        score += content.feature_penalty
        if content.feature_penalty:
            reasons.append(
                f"Feature/heritage ({content.feature_signal}): "
                f"{content.feature_penalty:+d}"
            )
        if (
            relevance.zone == "bassetlaw"
            and content.content_type == "current_competitive"
            and (module4_result.is_high_value or genuine_competitive_signal)
        ):
            local_competitive_bonus = _SPORT_LOCAL_COMPETITIVE_BONUS
            score += local_competitive_bonus
            reasons.append(
                f"Local competitive priority: +{local_competitive_bonus}"
            )
        score += relevance.adjustment
        if relevance.adjustment:
            reasons.append(
                f"Publication relevance ({relevance.reason}): {relevance.adjustment:+d}"
            )

    if (
        module_key == "sport"
        and routine_administrative
        and not (genuine_competitive_signal or module4_result.is_high_value)
    ):
        administrative_cap = thresholds["monitor"] - 1
        if score > administrative_cap:
            score = administrative_cap
            final_cap = "routine-administrative"
            reasons.append(
                "Routine administrative story capped at Low Priority"
            )

    if module_key == "sport" and content.content_type == "feature_heritage":
        feature_cap = thresholds["high_priority"] - 1
        if score > feature_cap:
            score = feature_cap
            final_cap = "feature-heritage"
            reasons.append("Feature/heritage story capped at Routine")

    if (
        module_key == "sport"
        and relevance.zone == "national"
        and not relevance.exceptional_national_interest
    ):
        national_cap = thresholds["front_page"] - 1
        if score > national_cap:
            score = national_cap
            final_cap = "ordinary-national-club"
            reasons.append("Ordinary national story capped below Front Page")

    if module_key == "sport" and relevance.zone == "international_remote":
        remote_cap = thresholds["newsworthy"] - 1
        if score > remote_cap:
            score = remote_cap
            final_cap = "international-remote"
            reasons.append("International/remote story capped below Newsworthy")

    rating = _star_rating(score, thresholds)
    level = _priority_level(score, thresholds)

    if module_key == "sport":
        matched_signals = _replace_sport_adjustment_markers(
            matched_signals,
            locality=locality_adjustment,
            competitive=competitive_adjustment,
            administrative=administrative_penalty,
            module4=module4_result.total,
            relevance=relevance.adjustment,
            content_type=content.feature_penalty,
            local_competitive=local_competitive_bonus,
        )
        LOGGER.debug(
            "sport editorial scoring title=%r source=%r organisation=%r "
            "base_score=%d authoritative_local_source_match=%r "
            "title_locality_match=%r strong_bassetlaw_evidence=%s "
            "weak_aliases_ignored=%s relevance_zone=%s "
            "locality_adjustment=%+d competitive_adjustment=%+d "
            "administrative_penalty=%+d module4_adjustments=%s "
            "module4_local_impact=%+d category_caps=%s "
            "duplicates_suppressed=%s content_type=%s sporting_adjustment=%+d "
            "relevance_adjustment=%+d local_competitive_bonus=%+d "
            "feature_penalty=%+d final_cap=%s "
            "final_score=%d final_priority=%s",
            title,
            source,
            "",
            starting_score,
            _exact_bassetlaw_club(source),
            _matched_bassetlaw_locality(title),
            locality_assessment.evidence,
            locality_assessment.weak_aliases_ignored,
            relevance.zone,
            locality_adjustment,
            competitive_adjustment,
            administrative_penalty,
            module4_result.adjustments,
            module4_result.local_impact,
            module4_result.caps_applied,
            module4_result.duplicates_suppressed,
            content.content_type,
            competitive_adjustment + module4_result.total,
            relevance.adjustment,
            local_competitive_bonus,
            content.feature_penalty,
            final_cap,
            score,
            level,
        )

    return PriorityResult(
        score=score,
        rating=rating,
        level=level,
        zone_key=zone_key,
        zone_label=zone_label,
        matched_place=matched_place,
        reasons=reasons,
        matched_signals=sorted(set(matched_signals)),
    )

def get_module_queue_settings(module: str, *, settings: dict | None = None) -> dict[str, int]:
    """Return queue presentation settings for a NewsDesk module."""
    loaded = settings if isinstance(settings, dict) else load_editorial_settings()
    if not isinstance(loaded, dict):
        loaded = {}
    profile = _module_profile(loaded, str(module or "default").strip().casefold() or "default")
    queue = _as_mapping(profile.get("queue"))
    return {
        "visible_limit": max(1, _as_int(queue.get("visible_limit"), 40)),
        "local_pin_limit": max(0, _as_int(queue.get("local_pin_limit"), 10)),
    }


def rank_stories(
    stories: Iterable[object],
    *,
    module: str,
    visible_limit: int | None = None,
) -> tuple[list[object], list[object]]:
    """
    Rank scored stories and split them into shown and overflow queues.

    Sport Intelligence uses a deterministic editorial class as its first sort
    key. Bassetlaw clubs therefore remain above every non-club sport story,
    while stories with any configured Bassetlaw place connection rank above
    surrounding-area and national stories.
    """

    settings = load_editorial_settings()
    queue_settings = get_module_queue_settings(module, settings=settings)
    limit = (
        queue_settings["visible_limit"]
        if visible_limit is None
        else max(1, int(visible_limit))
    )
    module_key = str(module or "default").strip().casefold() or "default"
    profile = _module_profile(settings, module_key)
    thresholds = _thresholds(settings, profile)

    ranked_stories = list(stories)

    for story in ranked_stories:
        extras = getattr(story, "extras", None)

        if not isinstance(extras, dict):
            extras = {}
            try:
                story.extras = extras
            except AttributeError:
                pass

        base_score = _as_int(extras.get("priority_score"), 0)
        ranking_base_score = base_score
        adjustment, recency_reason = _recency_adjustment(
            getattr(story, "published", "")
        )

        local_club = None
        editorial_rank = 0
        editorial_label = "National / International"
        editorial_reason = "Standard module ranking"

        if module_key == "sport":
            organisation = (
                extras.get("source_organisation", "")
                or extras.get("organisation", "")
            )
            locality_assessment = _assess_bassetlaw_locality(
                title=getattr(story, "title", ""),
                source=getattr(story, "source", ""),
                organisation=organisation,
                tags=getattr(story, "tags", ()),
                location=getattr(story, "location", ""),
                summary=getattr(story, "summary", ""),
                body=getattr(story, "body", ""),
            )
            local_club = locality_assessment.club
            relevance = _sport_relevance_assessment(
                locality=locality_assessment,
                title=getattr(story, "title", ""),
                source=getattr(story, "source", ""),
                organisation=organisation,
                tags=getattr(story, "tags", ()),
                location=getattr(story, "location", ""),
            )
            zone_key = {
                "bassetlaw": "bassetlaw", "regional": "surrounding",
                "national": "other", "international_remote": "international_remote",
            }[relevance.zone]

            (
                editorial_rank,
                editorial_label,
                editorial_reason,
            ) = _sport_editorial_class(
                zone_key=zone_key,
                local_club=local_club,
            )

            stored_signals = extras.get("matched_signals", ())
            if not isinstance(stored_signals, (list, tuple, set)):
                stored_signals = ()

            locality_adjustment, _, locality_reason = (
                _sport_locality_adjustment(
                    title=getattr(story, "title", ""),
                    source=(
                        getattr(story, "source", ""),
                        extras.get("source_organisation", ""),
                        extras.get("organisation", ""),
                    ),
                    tags=getattr(story, "tags", ()),
                    summary=getattr(story, "summary", ""),
                    body=getattr(story, "body", ""),
                    location=getattr(story, "location", ""),
                    organisation=organisation,
                    assessment=locality_assessment,
                )
            )
            module4_result = _sport_module4_adjustment(
                title=str(getattr(story, "title", "") or ""),
                summary=str(getattr(story, "summary", "") or ""),
                locality_adjustment=locality_adjustment,
            )
            (
                competitive_adjustment,
                _,
                genuine_competitive_signal,
            ) = _sport_competitive_adjustment(
                title=str(getattr(story, "title", "") or ""),
                summary=str(getattr(story, "summary", "") or ""),
                suppressed_categories=module4_result.suppressed_module2,
            )
            (
                administrative_penalty,
                _,
                routine_administrative,
            ) = _sport_administrative_adjustment(
                title=str(getattr(story, "title", "") or ""),
                summary=str(getattr(story, "summary", "") or ""),
                genuine_competitive_signal=(
                    genuine_competitive_signal or module4_result.is_high_value
                ),
            )
            content = _sport_content_assessment(
                title=str(getattr(story, "title", "") or ""),
                summary=str(getattr(story, "summary", "") or ""),
                module4_high_value=module4_result.is_high_value,
                genuine_competitive_signal=genuine_competitive_signal,
                routine_administrative=routine_administrative,
            )
            local_competitive_bonus = (
                _SPORT_LOCAL_COMPETITIVE_BONUS
                if relevance.zone == "bassetlaw"
                and content.content_type == "current_competitive"
                and (module4_result.is_high_value or genuine_competitive_signal)
                else 0
            )

            existing_locality = _stored_sport_adjustment(
                stored_signals,
                "locality",
            )
            existing_competitive = _stored_sport_adjustment(
                stored_signals,
                "competitive",
            )
            existing_administrative = _stored_sport_adjustment(
                stored_signals,
                "administrative",
            )
            existing_module4 = _stored_sport_adjustment(
                stored_signals,
                "module4",
            )
            existing_relevance = _stored_sport_adjustment(
                stored_signals,
                "relevance",
            )
            existing_content_type = _stored_sport_adjustment(
                stored_signals,
                "content_type",
            )
            existing_local_competitive = _stored_sport_adjustment(
                stored_signals,
                "local_competitive",
            )
            score_delta = (
                locality_adjustment - (existing_locality or 0)
                + competitive_adjustment - (existing_competitive or 0)
                + administrative_penalty - (existing_administrative or 0)
                + module4_result.total - (existing_module4 or 0)
                + relevance.adjustment - (existing_relevance or 0)
                + content.feature_penalty - (existing_content_type or 0)
                + local_competitive_bonus - (existing_local_competitive or 0)
            )
            base_score += score_delta

            final_cap = None
            if routine_administrative and not (
                genuine_competitive_signal or module4_result.is_high_value
            ):
                base_score = min(base_score, thresholds["monitor"] - 1)
                final_cap = "routine-administrative"

            if relevance.zone == "international_remote":
                remote_cap = thresholds["newsworthy"] - 1
                if base_score > remote_cap:
                    base_score = remote_cap
                    final_cap = "international-remote"

            if content.content_type == "feature_heritage":
                feature_cap = thresholds["high_priority"] - 1
                if base_score > feature_cap:
                    base_score = feature_cap
                    final_cap = "feature-heritage"

            if (
                relevance.zone == "national"
                and not relevance.exceptional_national_interest
            ):
                national_cap = thresholds["front_page"] - 1
                if base_score > national_cap:
                    base_score = national_cap
                    final_cap = "ordinary-national-club"

            extras["priority_score"] = base_score
            extras["priority_rating"] = _star_rating(base_score, thresholds)
            extras["priority_level"] = _priority_level(base_score, thresholds)
            extras["matched_signals"] = _replace_sport_adjustment_markers(
                stored_signals,
                locality=locality_adjustment,
                competitive=competitive_adjustment,
                administrative=administrative_penalty,
                module4=module4_result.total,
                relevance=relevance.adjustment,
                content_type=content.feature_penalty,
                local_competitive=local_competitive_bonus,
            )
            if locality_reason and existing_locality != locality_adjustment:
                stored_reasons = extras.get("priority_reasons", [])
                if not isinstance(stored_reasons, list):
                    stored_reasons = list(stored_reasons or ())
                stored_reasons.append(
                    f"{locality_reason}: {locality_adjustment:+d}"
                )
                extras["priority_reasons"] = stored_reasons

            LOGGER.debug(
                "sport editorial scoring title=%r source=%r organisation=%r "
                "base_score=%d authoritative_local_source_match=%r "
                "title_locality_match=%r strong_bassetlaw_evidence=%s "
                "weak_aliases_ignored=%s relevance_zone=%s "
                "locality_adjustment=%+d competitive_adjustment=%+d "
                "administrative_penalty=%+d module4_adjustments=%s "
                "module4_local_impact=%+d category_caps=%s "
                "duplicates_suppressed=%s content_type=%s "
                "sporting_adjustment=%+d "
                "relevance_adjustment=%+d local_competitive_bonus=%+d "
                "feature_penalty=%+d final_cap=%s final_score=%d "
                "final_priority=%s",
                getattr(story, "title", ""),
                getattr(story, "source", ""),
                organisation,
                ranking_base_score,
                _exact_bassetlaw_club(getattr(story, "source", ""), organisation),
                _matched_bassetlaw_locality(getattr(story, "title", "")),
                locality_assessment.evidence,
                locality_assessment.weak_aliases_ignored,
                relevance.zone,
                locality_adjustment,
                competitive_adjustment,
                administrative_penalty,
                module4_result.adjustments,
                module4_result.local_impact,
                module4_result.caps_applied,
                module4_result.duplicates_suppressed,
                content.content_type,
                competitive_adjustment + module4_result.total,
                relevance.adjustment,
                local_competitive_bonus,
                content.feature_penalty,
                final_cap,
                base_score,
                extras["priority_level"],
            )

        extras["recency_adjustment"] = adjustment
        extras["recency_reason"] = recency_reason
        extras["ranking_score"] = base_score + adjustment

        extras["sport_editorial_class"] = editorial_rank
        extras["sport_editorial_class_label"] = editorial_label
        extras["sport_editorial_reason"] = editorial_reason
        if module_key == "sport":
            extras["editorial_zone"] = (
                "bassetlaw" if relevance.zone == "bassetlaw"
                else "surrounding" if relevance.zone == "regional"
                else "other"
            )
            extras["editorial_zone_label"] = {
                "bassetlaw": "Bassetlaw",
                "regional": "Regional",
                "national": "National",
                "international_remote": "International / Remote",
            }[relevance.zone]
            extras["sport_relevance_zone"] = relevance.zone
            extras["sport_relevance_adjustment"] = relevance.adjustment
            extras["sport_content_type"] = content.content_type
            extras["sport_local_competitive_bonus"] = local_competitive_bonus
            if locality_assessment.place:
                extras["matched_place"] = locality_assessment.place
            else:
                extras.pop("matched_place", None)

        # Preserve the previous extras fields for compatibility with any
        # existing UI or diagnostic code.
        extras["local_club_priority"] = bool(local_club)

        if local_club:
            extras["matched_local_club"] = local_club
            extras["matched_local_sport_entity"] = local_club
        else:
            extras.pop("matched_local_club", None)
            extras.pop("matched_local_sport_entity", None)

    def story_key(story: object) -> tuple[int, int, int, int, float]:
        extras = getattr(story, "extras", {}) or {}
        published = _published_datetime(getattr(story, "published", ""))

        ranking_score = _as_int(extras.get("ranking_score"), 0)
        precedence = _sport_editorial_precedence(
            relevance_zone=str(extras.get("sport_relevance_zone", "national")),
            content_type=str(extras.get("sport_content_type", "current_club_news")),
        )
        return (
            int(ranking_score / 5),
            precedence,
            ranking_score,
            _as_int(extras.get("priority_rating"), 0),
            published.timestamp() if published is not None else 0.0,
        )

    ranked = sorted(ranked_stories, key=story_key, reverse=True)
    return ranked[:limit], ranked[limit:]


__all__ = ["PriorityResult", "get_module_queue_settings", "rank_stories", "score_story"]
