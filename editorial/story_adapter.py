"""Convert different newsroom sources into a shared story structure."""

from editorial.utils import clean_text


SUPPORTED_SOURCE_TYPES = {
    "planning",
    "police",
    "fire",
    "council",
    "business",
    "community",
    "events",
    "sport",
    "health",
    "education",
    "generic",
}


def _text(value, fallback=""):
    """Return a cleaned text value."""
    cleaned = clean_text(value)
    return cleaned or fallback


def _list_values(value):
    """Return a clean list of text values."""
    if not value:
        return []

    if isinstance(value, str):
        cleaned = clean_text(value)
        return [cleaned] if cleaned else []

    results = []

    try:
        values = list(value)
    except TypeError:
        values = [value]

    for item in values:
        cleaned = clean_text(item)

        if cleaned:
            results.append(cleaned)

    return results


def detect_source_type(story):
    """Attempt to identify the source type from its available fields."""
    story = story or {}

    explicit_type = _text(
        story.get("source_type")
        or story.get("content_type")
        or story.get("story_type")
    ).lower()

    if explicit_type in SUPPORTED_SOURCE_TYPES:
        return explicit_type

    planning_fields = {
        "reference",
        "proposal",
        "proposal_summary",
        "application_type",
        "planning_authority",
        "decision",
    }

    if len(planning_fields.intersection(story.keys())) >= 2:
        return "planning"

    source_text = " ".join(
        [
            _text(story.get("source")),
            _text(story.get("authority")),
            _text(story.get("organisation")),
            _text(story.get("raw_text")),
            _text(story.get("body")),
        ]
    ).lower()

    if any(
        phrase in source_text
        for phrase in (
            "nottinghamshire police",
            "police officers",
            "detectives",
            "charged with",
            "arrested",
        )
    ):
        return "police"

    if any(
        phrase in source_text
        for phrase in (
            "fire and rescue",
            "firefighters",
            "fire crews",
            "fire service",
        )
    ):
        return "fire"

    if any(
        phrase in source_text
        for phrase in (
            "district council",
            "county council",
            "borough council",
            "councillor",
            "consultation",
        )
    ):
        return "council"

    return "generic"


def _base_story(story, source_type):
    """Create the common structure used by the editorial writer."""
    return {
        "source_type": source_type,
        "headline": _text(story.get("headline")),
        "title": _text(story.get("title")),
        "area": _text(story.get("area"), "Bassetlaw"),
        "location": _text(
            story.get("location")
            or story.get("address")
            or story.get("site_address")
        ),
        "reference": _text(story.get("reference")),
        "status": _text(story.get("status")),
        "decision": _text(story.get("decision")),
        "source": _text(
            story.get("source")
            or story.get("authority")
            or story.get("organisation")
        ),
        "source_url": _text(story.get("source_url")),
        "published_date": _text(story.get("published_date")),
        "raw_text": _text(
            story.get("raw_text")
            or story.get("body")
            or story.get("statement")
        ),
        "quotes": _list_values(story.get("quotes")),
        "tags": _list_values(story.get("tags")),
        "why_news": _list_values(story.get("why_news")),
        "follow_up": _list_values(story.get("follow_up")),
        "editorial_priority": _text(
            story.get("editorial_priority"),
            "WEBSITE STORY",
        ),
        "score": story.get("score", 0),
        "priority_stars": story.get("priority_stars", 1),
    }


def _adapt_planning(story):
    """Convert a planning record into the shared structure."""
    adapted = _base_story(story, "planning")

    adapted.update(
        {
            "proposal": _text(
                story.get("proposal")
                or story.get("proposal_summary"),
                "A planning proposal",
            ),
            "proposal_summary": _text(
                story.get("proposal_summary")
                or story.get("proposal"),
                "A planning proposal",
            ),
            "address": _text(
                story.get("address")
                or story.get("site_address")
                or story.get("location")
                or story.get("area"),
                "Bassetlaw",
            ),
            "site_address": _text(
                story.get("site_address")
                or story.get("address")
                or story.get("location")
            ),
            "applicant": _text(
                story.get("applicant")
                or story.get("applicant_name")
            ),
            "applicant_name": _text(
                story.get("applicant_name")
                or story.get("applicant")
            ),
            "application_type": _text(
                story.get("application_type")
                or story.get("type")
            ),
            "planning_authority": _text(
                story.get("planning_authority")
                or story.get("authority")
            ),
            "authority": _text(
                story.get("authority")
                or story.get("planning_authority")
            ),
        }
    )

    return adapted


def _adapt_generic(story, source_type):
    """Preserve generic newsroom material using the shared structure."""
    adapted = _base_story(story, source_type)

    adapted.update(
        {
            "proposal": _text(
                story.get("proposal")
                or story.get("summary")
                or story.get("headline")
                or story.get("title")
                or story.get("raw_text"),
                "Local news update",
            ),
            "proposal_summary": _text(
                story.get("summary")
                or story.get("headline")
                or story.get("title")
                or story.get("proposal")
                or story.get("raw_text"),
                "Local news update",
            ),
            "address": _text(
                story.get("address")
                or story.get("location")
                or story.get("area"),
                "Bassetlaw",
            ),
            "site_address": _text(
                story.get("site_address")
                or story.get("address")
                or story.get("location")
            ),
            "applicant": "",
            "applicant_name": "",
            "application_type": "",
            "planning_authority": "",
            "authority": _text(
                story.get("authority")
                or story.get("source")
                or story.get("organisation")
            ),
        }
    )

    return adapted


def adapt_story(story, source_type=None):
    """
    Return a normalised story dictionary.

    Planning records are fully supported. Other source types currently use
    the generic structure and can receive specialist adapters later.
    """
    story = story or {}

    detected_type = (
        _text(source_type).lower()
        if source_type
        else detect_source_type(story)
    )

    if detected_type not in SUPPORTED_SOURCE_TYPES:
        detected_type = "generic"

    if detected_type == "planning":
        return _adapt_planning(story)

    return _adapt_generic(story, detected_type)