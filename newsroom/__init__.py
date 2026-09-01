"""Editorial story-tagging rules for NewsDesk."""

def _clean_text(value):
    return " ".join(str(value or "").split())


def _normalise_category(value):
    category = _clean_text(value)
    return category if category else "Uncategorised"


def _contains_any(text, keywords):
    return any(keyword in text for keyword in keywords)


def story_tags(app):
    """Return concise editorial tags for a planning application."""
    text = f"{app.proposal} {app.category} {app.address}".lower()
    tags = []

    rules = (
        ("Housing", ("dwelling", "dwellings", "housing", "residential", "apartment", "flat", "homes")),
        ("Battery Storage", ("battery", "energy storage", "bess")),
        ("Renewable Energy", ("solar", "photovoltaic", "renewable", "wind turbine")),
        ("Commercial", ("commercial", "employment", "industrial", "warehouse", "retail", "factory", "business unit")),
        ("Heritage", ("listed building", "heritage", "conservation area", "scheduled monument")),
        ("Telecoms", ("telecom", "mast", "antenna", "5g")),
        ("Community", ("school", "hospital", "medical centre", "health centre", "care home", "community centre")),
        ("Agriculture", ("agricultural", "farm", "barn", "livestock")),
        ("Trees", ("tree", "trees", "tpo", "arboricultural")),
        ("Transport", ("highway", "road", "access", "car park", "parking", "traffic")),
        ("Demolition", ("demolition", "demolish")),
        ("Change of Use", ("change of use",)),
    )

    for label, keywords in rules:
        if _contains_any(text, keywords):
            tags.append(label)

    category = _normalise_category(app.category)
    if category != "Uncategorised" and category not in tags:
        tags.append(category)

    if not tags:
        tags.append("General Planning")

    return tags[:4]