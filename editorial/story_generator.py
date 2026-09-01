"""Generate publication-ready draft copy from planning intelligence data."""

from editorial.utils import clean_text
from editorial.story_adapter import adapt_story

DEFAULT_AREA = "Bassetlaw"
DEFAULT_SOURCE = "the relevant local planning authority"


def _text(value, fallback=""):
    """Return a cleaned string value or a fallback."""
    cleaned = clean_text(value)
    return cleaned or fallback


def _list_values(value):
    """Return a clean list of non-empty strings."""
    if not value:
        return []

    if isinstance(value, str):
        cleaned = clean_text(value)
        return [cleaned] if cleaned else []

    results = []

    for item in value:
        cleaned = clean_text(item)
        if cleaned:
            results.append(cleaned)

    return results


def _first(values, fallback=""):
    """Return the first useful value from a list-like object."""
    cleaned = _list_values(values)
    return cleaned[0] if cleaned else fallback


def _sentence(text):
    """Ensure text ends with suitable punctuation."""
    cleaned = _text(text)

    if not cleaned:
        return ""

    if cleaned.endswith((".", "!", "?")):
        return cleaned

    return f"{cleaned}."


def _lower_first(text):
    """Lowercase the first letter without altering the rest of the text."""
    cleaned = _text(text)

    if not cleaned:
        return ""

    return cleaned[:1].lower() + cleaned[1:]


def _area(story):
    return _text(story.get("area"), DEFAULT_AREA)


def _proposal(story):
    return (
        _text(story.get("proposal_summary"))
        or _text(story.get("proposal"))
        or "A planning proposal"
    )


def _reference(story):
    return _text(story.get("reference"), "Not recorded")


def _address(story):
    return (
        _text(story.get("address"))
        or _text(story.get("site_address"))
        or _area(story)
    )


def _decision(story):
    return (
        _text(story.get("decision"))
        or _text(story.get("status"))
        or "No formal decision has been recorded"
    )


def _applicant(story):
    return (
        _text(story.get("applicant"))
        or _text(story.get("applicant_name"))
    )


def _application_type(story):
    return (
        _text(story.get("application_type"))
        or _text(story.get("type"))
    )


def _source(story):
    return (
        _text(story.get("authority"))
        or _text(story.get("planning_authority"))
        or DEFAULT_SOURCE
    )


def _priority(story):
    return _text(
        story.get("editorial_priority"),
        "WEBSITE STORY",
    )


def _score(story):
    try:
        return int(story.get("score", 0))
    except (TypeError, ValueError):
        return 0


def _why_news(story):
    return _list_values(story.get("why_news"))


def _follow_up(story):
    return _list_values(story.get("follow_up"))


def _tags(story):
    return _list_values(story.get("tags"))


def _decision_wording(decision):
    """Return wording suitable for a headline."""
    lowered = decision.lower()

    if any(word in lowered for word in ("approved", "granted", "permitted")):
        return "approved"

    if any(word in lowered for word in ("refused", "rejected", "declined")):
        return "refused"

    if "withdrawn" in lowered:
        return "withdrawn"

    if "pending" in lowered or "awaiting" in lowered:
        return "under consideration"

    return ""


def _headline(story):
    """Build a clear local-news headline."""
    area = _area(story)
    proposal = _proposal(story)
    decision = _decision_wording(_decision(story))

    proposal_clean = proposal.rstrip(". ")

    if decision:
        return f"{proposal_clean} in {area} {decision}"

    if "application" in proposal_clean.lower():
        return f"{proposal_clean} submitted in {area}"

    return f"Plans submitted for {_lower_first(proposal_clean)} in {area}"


def _subheading(story):
    """Build a supporting summary line."""
    reference = _reference(story)
    address = _address(story)
    decision = _decision(story)

    return (
        f"The application relates to {address} and is listed under "
        f"reference {reference}. Its current status is: {decision}."
    )


def _opening_paragraph(story):
    """Create the article lead."""
    proposal = _proposal(story).rstrip(". ")
    address = _address(story)
    area = _area(story)
    decision_wording = _decision_wording(_decision(story))

    if decision_wording == "approved":
        return (
            f"Plans for {_lower_first(proposal)} at {address} have been "
            f"approved."
        )

    if decision_wording == "refused":
        return (
            f"Plans for {_lower_first(proposal)} at {address} have been "
            f"refused."
        )

    if decision_wording == "withdrawn":
        return (
            f"An application concerning {_lower_first(proposal)} at "
            f"{address} has been withdrawn."
        )

    return (
        f"A planning application concerning {_lower_first(proposal)} has "
        f"been recorded at {address}, {area}."
    )


def _details_paragraph(story):
    """Create the factual planning-details paragraph."""
    reference = _reference(story)
    decision = _decision(story)
    application_type = _application_type(story)
    applicant = _applicant(story)
    source = _source(story)

    details = [
        f"The application is listed under reference {reference}",
    ]

    if application_type:
        details.append(f"and is recorded as {application_type}")

    if applicant:
        details.append(f"The applicant is listed as {applicant}")

    details.append(f"The current status or decision is recorded as {decision}")

    first_sentence = " ".join(details[:2])
    remaining = details[2:]

    paragraph = _sentence(first_sentence)

    for item in remaining:
        paragraph += f" {_sentence(item)}"

    return f"{paragraph} Details have been published by {source}."


def _news_value_paragraph(story):
    """Explain why NewsDesk selected the application."""
    priority = _priority(story)
    score = _score(story)
    reasons = _why_news(story)

    if reasons:
        reason_text = " ".join(_sentence(reason) for reason in reasons[:3])
    else:
        reason_text = (
            "The proposal may have implications for residents, local "
            "services or the surrounding area."
        )

    if score:
        return (
            f"Devour Lincolnshire NewsDesk has classified the application as "
            f"{priority}, with a news value score of {score}. {reason_text}"
        )

    return (
        f"Devour Lincolnshire NewsDesk has classified the application as "
        f"{priority}. {reason_text}"
    )


def _follow_up_paragraph(story):
    """Create a useful closing paragraph."""
    follow_up = _follow_up(story)

    if follow_up:
        suggestions = " ".join(
            _sentence(item) for item in follow_up[:2]
        )

        return (
            f"Further reporting may examine the following points: "
            f"{suggestions}"
        )

    return (
        "Residents can view the application documents and any public "
        "consultation information through the relevant planning records."
    )


def _website_article(story, headline):
    """Build a polished website draft."""
    paragraphs = [
        headline,
        "",
        _opening_paragraph(story),
        "",
        _details_paragraph(story),
        "",
        _news_value_paragraph(story),
        "",
        _follow_up_paragraph(story),
        "",
        (
            "The information above is based on the planning record available "
            "at the time of writing. Application details and decisions may "
            "subsequently change."
        ),
    ]

    return "\n".join(paragraphs)


def _facebook_post(story, headline):
    """Build a professional Facebook post."""
    reference = _reference(story)
    area = _area(story)
    address = _address(story)
    decision = _decision(story)
    reasons = _why_news(story)

    why_it_matters = (
        _first(
            reasons,
            "The proposal may have a notable impact on the local area.",
        )
    )

    return (
        f"🏗️ {headline}\n\n"
        f"A planning application relating to {address} has been highlighted "
        f"by Devour Lincolnshire NewsDesk.\n\n"
        f"📍 Area: {area}\n"
        f"📄 Reference: {reference}\n"
        f"📌 Current status: {decision}\n\n"
        f"Why it matters: {_sentence(why_it_matters)}\n\n"
        f"Further information can be found in the published planning records."
    )


def _newsletter_copy(story, headline):
    """Build a concise newsletter item."""
    proposal = _proposal(story)
    area = _area(story)
    decision = _decision(story)
    reason = _first(
        _why_news(story),
        "The proposal may have a local impact and is worth monitoring.",
    )

    return (
        f"{headline}\n\n"
        f"{_sentence(proposal)} The application is located in {area}, "
        f"with its current status recorded as {decision}. "
        f"{_sentence(reason)}"
    )


def _image_caption(story):
    """Build a suggested image caption."""
    address = _address(story)
    proposal = _proposal(story)

    return (
        f"The site at {address}, where plans concerning "
        f"{_lower_first(proposal.rstrip('. '))} have been recorded."
    )


def _meta_title(headline):
    """Return a search-friendly title."""
    if len(headline) <= 60:
        return headline

    return headline[:57].rstrip() + "..."


def _meta_description(story):
    """Return a concise search description."""
    proposal = _proposal(story).rstrip(". ")
    area = _area(story)
    reference = _reference(story)

    description = (
        f"Details of plans for {_lower_first(proposal)} in {area}, "
        f"including application reference {reference} and the latest status."
    )

    if len(description) <= 155:
        return description

    return description[:152].rstrip() + "..."


def generate_story(story):
    """Return all generated editorial formats for one newsroom story."""
    story = adapt_story(story)
    headline = _headline(story)

    return {
        "headline": headline,
        "subheading": _subheading(story),
        "website_article": _website_article(story, headline),
        "facebook_post": _facebook_post(story, headline),
        "newsletter_copy": _newsletter_copy(story, headline),
        "image_caption": _image_caption(story),
        "meta_title": _meta_title(headline),
        "meta_description": _meta_description(story),
        "keywords": _tags(story),
        "category": "Planning",
    }