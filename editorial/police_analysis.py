"""Police-specific editorial analysis for NewsDesk."""

from editorial.priority_engine import score_story
from editorial.story_classifier import classify_story
from services.models import NewsStory, PoliceArticle


CATEGORY_RULES = (
    (
        "Missing Person",
        (
            "missing person",
            "missing child",
            "missing teenager",
        ),
    ),
    (
        "Sentencing",
        (
            "jailed",
            "sentenced",
            "imprisoned",
        ),
    ),
    (
        "Court",
        (
            "charged",
            "court",
            "convicted",
            "pleaded guilty",
        ),
    ),
    (
        "Appeal",
        (
            "appeal",
            "witnesses",
            "information",
            "cctv",
        ),
    ),
    (
        "Arrest",
        (
            "arrested",
            "detained",
        ),
    ),
    (
        "Drug Crime",
        (
            "drugs",
            "cannabis",
            "cocaine",
            "heroin",
        ),
    ),
    (
        "Knife Crime",
        (
            "knife",
            "bladed article",
            "machete",
        ),
    ),
    (
        "Firearms",
        (
            "firearm",
            "gun",
            "shotgun",
        ),
    ),
    (
        "Burglary",
        (
            "burglary",
            "burglar",
        ),
    ),
    (
        "Robbery",
        (
            "robbery",
            "robbed",
        ),
    ),
    (
        "Fraud",
        (
            "fraud",
            "scam",
        ),
    ),
    (
        "Domestic Abuse",
        (
            "domestic abuse",
            "domestic violence",
        ),
    ),
    (
        "Roads Policing",
        (
            "collision",
            "drink-driving",
            "drug-driving",
            "road closed",
        ),
    ),
    (
        "Neighbourhood Policing",
        (
            "neighbourhood policing",
            "antisocial behaviour",
            "anti-social behaviour",
            "asb",
        ),
    ),
)


ANGLE_RULES = (
    (
        "Court Result",
        (
            "jailed",
            "sentenced",
            "convicted",
            "pleaded guilty",
        ),
    ),
    (
        "Police Appeal",
        (
            "appeal",
            "witnesses",
            "cctv",
            "information",
        ),
    ),
    (
        "Major Investigation",
        (
            "murder",
            "major investigation",
            "detectives",
        ),
    ),
    (
        "Public Safety",
        (
            "missing child",
            "firearm",
            "knife",
            "serious collision",
        ),
    ),
    (
        "Operational Success",
        (
            "seized",
            "dismantled",
            "recovered",
            "arrested",
        ),
    ),
    (
        "Traffic Disruption",
        (
            "road closed",
            "collision",
            "diversion",
        ),
    ),
    (
        "Victim Support",
        (
            "domestic abuse",
            "victim support",
        ),
    ),
)


def _clean_text(value: object) -> str:
    """Return a compact text value."""

    return " ".join(str(value or "").split())


def _article_text(article: PoliceArticle) -> str:
    """Combine the article's searchable text."""

    return " ".join(
        (
            _clean_text(article.headline),
            _clean_text(article.summary),
            _clean_text(article.body),
            _clean_text(article.location),
            _clean_text(article.status),
        )
    ).lower()


def _contains_any(
    text: str,
    phrases: tuple[str, ...],
) -> bool:
    """Return True when the text contains any supplied phrase."""

    return any(phrase in text for phrase in phrases)


def identify_category(article: PoliceArticle) -> str:
    """Return the best matching legacy police category."""

    text = _article_text(article)

    for category, phrases in CATEGORY_RULES:
        if _contains_any(text, phrases):
            return category

    return _clean_text(article.category) or "General Police"


def identify_editorial_angle(article: PoliceArticle) -> str:
    """Return the main editorial angle."""

    text = _article_text(article)

    for angle, phrases in ANGLE_RULES:
        if _contains_any(text, phrases):
            return angle

    return "Community Information"


def build_tags(
    article: PoliceArticle,
    category: str,
) -> list[str]:
    """Build a short list of useful newsroom tags."""

    text = _article_text(article)
    tags = [category]

    tag_rules = (
        (
            "Worksop",
            (
                "worksop",
            ),
        ),
        (
            "Retford",
            (
                "retford",
            ),
        ),
        (
            "Harworth",
            (
                "harworth",
                "bircotes",
            ),
        ),
        (
            "Court",
            (
                "court",
                "charged",
                "jailed",
                "sentenced",
            ),
        ),
        (
            "Appeal",
            (
                "appeal",
                "witnesses",
                "cctv",
            ),
        ),
        (
            "Drugs",
            (
                "drugs",
                "cannabis",
                "cocaine",
                "heroin",
            ),
        ),
        (
            "Road Safety",
            (
                "collision",
                "drink-driving",
                "drug-driving",
            ),
        ),
        (
            "Violence",
            (
                "assault",
                "violence",
                "stabbed",
                "murder",
            ),
        ),
    )

    for tag, phrases in tag_rules:
        if tag not in tags and _contains_any(text, phrases):
            tags.append(tag)

    return tags[:5]


def build_extra_signals(article: PoliceArticle) -> list[str]:
    """Return police-profile signals for the shared priority engine."""

    text = _article_text(article)
    signals: list[str] = []

    if "appeal" in text or "witnesses" in text:
        signals.append("public appeal")

    if article.images:
        signals.append("image available")

    if "repeat offender" in text:
        signals.append("repeat offender")

    if any(
        phrase in text
        for phrase in (
            "large seizure",
            "thousands of pounds",
            "millions of pounds",
            "hundreds of plants",
            "thousands of plants",
        )
    ):
        signals.append("large seizure")

    return signals


def build_why_news(
    article: PoliceArticle,
    category: str,
    priority,
) -> list[str]:
    """Explain the editorial value in plain newsroom language."""

    text = _article_text(article)
    reasons: list[str] = []

    if priority.matched_place:
        reasons.append(
            f"The story directly affects {priority.matched_place}."
        )

    if category == "Appeal":
        reasons.append(
            "Police are asking the public for information or evidence."
        )

    if category == "Missing Person":
        reasons.append(
            "The story may require urgent public awareness."
        )

    if category in {"Sentencing", "Court"}:
        reasons.append(
            "The case has reached an important stage in the justice process."
        )

    if category in {
        "Drug Crime",
        "Knife Crime",
        "Firearms",
        "Burglary",
        "Robbery",
        "Domestic Abuse",
    }:
        reasons.append(
            f"The incident concerns {category.lower()} and may affect "
            "local community safety."
        )

    if "cctv" in text:
        reasons.append(
            "CCTV footage or images may help readers identify someone involved."
        )

    if not reasons:
        reasons.append(
            "The story provides relevant local policing information."
        )

    return reasons


def build_follow_up(
    article: PoliceArticle,
    category: str,
) -> list[str]:
    """Suggest useful newsroom follow-up actions."""

    text = _article_text(article)
    actions: list[str] = []

    if category == "Appeal":
        actions.append(
            "Check whether Nottinghamshire Police has issued an update."
        )
        actions.append(
            "Check whether anyone has been arrested or charged."
        )

    if "cctv" in text:
        actions.append(
            "Check whether CCTV images are available for publication."
        )

    if category in {"Court", "Sentencing"}:
        actions.append(
            "Check court records for the full result and sentence."
        )

    if category == "Missing Person":
        actions.append(
            "Confirm whether the missing person has been found before "
            "publication."
        )

    if category in {
        "Roads Policing",
        "Traffic Disruption",
    }:
        actions.append(
            "Check whether the road has reopened and whether delays remain."
        )

    if not actions:
        actions.append(
            "Monitor Nottinghamshire Police for further updates."
        )

    return actions


def analyse_police_article(
    article: PoliceArticle,
) -> NewsStory:
    """Convert a raw police article into a fully analysed NewsStory."""

    category = identify_category(article)
    editorial_angle = identify_editorial_angle(article)
    tags = build_tags(article, category)

    classification = classify_story(
        title=article.headline,
        summary=article.summary,
        body=article.body,
        location=article.location,
    )

    priority = score_story(
        module="police",
        title=article.headline,
        summary=article.summary,
        body=article.body,
        location=article.location,
        extra_signals=build_extra_signals(article),
    )

    return NewsStory(
        source_type="police",
        headline=_clean_text(article.headline),
        summary=_clean_text(article.summary),
        body=_clean_text(article.body),
        location=_clean_text(article.location),
        area=(
            priority.matched_place
            or _clean_text(article.location)
            or "Bassetlaw"
        ),
        published_date=_clean_text(article.published_date),
        source=(
            _clean_text(article.source)
            or "Nottinghamshire Police"
        ),
        source_url=_clean_text(article.source_url),
        score=int(priority.score),
        rating=int(priority.rating),
        category=category,
        editorial_angle=editorial_angle,
        matched_place=priority.matched_place or "",
        priority_level=priority.level,
        editorial_zone=priority.zone_label,
        tags=tags,
        why_news=build_why_news(
            article,
            category,
            priority,
        ),
        follow_up=build_follow_up(
            article,
            category,
        ),
        priority_reasons=list(priority.reasons),
        matched_signals=list(priority.matched_signals),
        primary_category=classification.primary_category,
        secondary_category=classification.secondary_category,
        crime_type=classification.crime_type,
        severity=classification.severity,
        victim_type=classification.victim_type,
        story_type=classification.story_type,
        public_interest=classification.public_interest,
        developing=classification.developing,
        classification_signals=list(
            classification.matched_signals
        ),
    )