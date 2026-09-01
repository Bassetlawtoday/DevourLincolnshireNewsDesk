"""Pure newsletter preview composition with no publishing side effects."""

from __future__ import annotations

from .models import NewsletterEdition, NewsletterItem


def preview_structure(
    edition: NewsletterEdition,
) -> tuple[NewsletterItem | None, list[tuple[str, list[NewsletterItem]]]]:
    """Return the lead and ordered section groups without duplicating the lead."""

    lead = next(
        (item for item in edition.items if item.item_id == edition.lead_item_id),
        None,
    )
    remaining = [item for item in edition.items if lead is None or item.item_id != lead.item_id]
    sections: list[tuple[str, list[NewsletterItem]]] = []
    known_sections = list(edition.section_order)
    for item in remaining:
        if item.section not in known_sections:
            known_sections.append(item.section)
    for section in known_sections:
        items = [item for item in remaining if item.section == section]
        if items:
            sections.append((section, items))
    return lead, sections


__all__ = ["preview_structure"]
