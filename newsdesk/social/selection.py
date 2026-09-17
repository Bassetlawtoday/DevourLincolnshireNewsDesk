"""Shared direct Add to Social Desk action for NewsDesk modules."""

from __future__ import annotations

from datetime import datetime, timedelta
from tkinter import messagebox

from newsdesk.social.store import SocialDraft, SocialDraftStore, SocialSettingsStore
from newsdesk.social.text import clean_social_text, repair_ldrs_draft


def _show_sent_status(parent) -> None:
    """Show a successful hand-off in each module's existing status control."""
    for attribute in ("status_label", "status", "editor_status"):
        widget = getattr(parent, attribute, None)
        if widget is None or not hasattr(widget, "configure"):
            continue
        try:
            widget.configure(text="Status: Sent to Social Desk")
            return
        except Exception:
            continue


def _rights_status(image_url: str, credit: str, module_key: str) -> str:
    if not image_url:
        return "no image"
    evidence = credit.casefold()
    if module_key == "newsletter" or "approved for use" in evidence or "permission" in evidence:
        return "approved"
    return "not reviewed"


def _real_image(value: str) -> str:
    image_url = str(value or "").strip()
    return "" if "ldrs.org.uk/assets/images/placeholder.png" in image_url.casefold() else image_url


def social_workflow_status(story) -> str:
    """Return the persisted Social Desk stage for a newsroom story."""
    source_url = str(getattr(story, "url", "") or "").strip()
    if not source_url:
        return ""
    store = SocialDraftStore()
    draft = store.find_by_source_url(store.load(), source_url)
    if draft is None:
        return ""
    delivered = bool(
        str(draft.metricool_id or "").strip()
        or str(draft.status or "").strip().casefold()
        == "sent to metricool as draft"
    )
    return "SENT TO METRICOOL" if delivered else "SENT TO SOCIAL DESK"


def add_story_to_social_desk(parent, story, *, module_key: str) -> SocialDraft | None:
    """Stage a Story directly in Social Desk without using Newsletter Desk."""

    title = str(getattr(story, "title", "") or "").strip()
    source_url = str(getattr(story, "url", "") or "").strip()
    text = clean_social_text(
        getattr(story, "body", "") or getattr(story, "summary", ""),
        source_url=source_url,
    )
    author = str(getattr(story, "author", "") or "").strip()
    if module_key == "police" and author:
        attribution = f"Posted by {author}"
        if attribution.casefold() not in text.casefold():
            text = f"{text}\n\n{attribution}".strip()
    image_url = _real_image(getattr(story, "image_url", ""))
    image_caption = str(getattr(story, "image_caption", "") or getattr(story, "image_alt_text", "") or "").strip() if image_url else ""
    image_credit = str(getattr(story, "image_credit", "") or "").strip() if image_url else ""
    if not title or not text:
        messagebox.showwarning(
            "Add to Socials",
            "The selected content needs a title and text before it can be staged.",
            parent=parent,
        )
        return None
    settings = SocialSettingsStore().load()
    store = SocialDraftStore()
    drafts = store.load()
    draft = store.find_by_source_url(drafts, source_url) or SocialDraft()
    existed = any(item.draft_id == draft.draft_id for item in drafts)
    draft.title = title
    draft.text = text
    draft.source_url = source_url
    # LDRS Content Explorer URLs require newsroom authentication and are not
    # suitable public links. Keep them for provenance/deduplication only.
    draft.include_source_url = module_key != "content"
    if module_key == "content":
        draft.internal_source_url = source_url
        draft.source_url = ""
    draft.image_url = image_url
    draft.image_caption = image_caption
    draft.image_credit = image_credit
    draft.image_rights_status = _rights_status(image_url, image_credit, module_key)
    draft.source_kind = module_key
    if not draft.publication_datetime:
        draft.publication_datetime = (datetime.now() + timedelta(minutes=20)).strftime("%Y-%m-%dT%H:%M:%S")
    draft.timezone = draft.timezone or settings.get("timezone") or "Europe/London"
    draft.status = {
        "content": "Local Democracy draft",
        "events": "Events draft",
        "newsletter": "Newsletter selection draft",
        "planning": "Planning draft",
        "police": "Police draft",
        "fire": "Fire draft",
        "sport": "Sport draft",
        "council": "Council draft",
    }.get(module_key, "Blank social draft")
    if module_key == "content":
        repair_ldrs_draft(draft)
    draft.updated_at = datetime.now().astimezone().isoformat()
    if not existed:
        drafts.append(draft)
    store.save(drafts)
    _show_sent_status(parent)
    messagebox.showinfo(
        "Added to Socials",
        "The existing social draft was updated without creating a duplicate."
        if existed else "The content, source link and available source image have been staged for social media.",
        parent=parent,
    )
    return draft


__all__ = ["add_story_to_social_desk", "social_workflow_status"]
