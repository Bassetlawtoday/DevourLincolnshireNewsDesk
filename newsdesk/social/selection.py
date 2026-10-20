"""Shared direct Social Desk staging for NewsDesk modules."""

from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
from tkinter import messagebox

from newsdesk.social.store import SocialDraft, SocialDraftStore, SocialHandoffStore, SocialSettingsStore
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


def _add_ldrs_author_credit(text: str, author: str) -> str:
    """Prepend the LDRS author credit once, preserving the supplied copy."""
    clean_author = str(author or "").strip()
    if not clean_author:
        return str(text or "").strip()
    byline = f"By: {clean_author}, LDRS."
    clean_text = str(text or "").strip()
    if byline.casefold() in clean_text.casefold():
        return clean_text
    return f"{byline}\n\n{clean_text}".strip()


def _story_identity(story, module_key: str) -> str:
    """Return a permanent, non-public identity for refresh deduplication."""
    parts = (
        module_key,
        getattr(story, "story_id", ""),
        getattr(story, "url", ""),
        getattr(story, "source", ""),
        getattr(story, "title", ""),
        getattr(story, "published", ""),
    )
    normalised = "|".join(" ".join(str(value or "").split()).casefold() for value in parts)
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()


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


def stage_story_for_social_desk(
    story,
    *,
    module_key: str,
    updates_item_id: str = "",
    update_existing: bool = False,
) -> tuple[SocialDraft, bool]:
    """Persist one local Social Desk draft without opening any UI.

    Returns a draft and a created flag. Automated refreshes leave an existing
    draft untouched so editorial changes cannot be overwritten.
    """

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
    if not title or not text:
        raise ValueError("The content needs a title and text before it can be staged.")

    identity = _story_identity(story, module_key)
    store = SocialDraftStore()
    drafts = store.load()
    draft = (
        store.find_by_source_identity(drafts, identity)
        or store.find_by_source_url(drafts, source_url)
    )
    existed = draft is not None
    if existed and not update_existing:
        SocialHandoffStore().mark(identity, module_key)
        return draft, False
    draft = draft or SocialDraft()

    image_url = _real_image(getattr(story, "image_url", ""))
    image_caption = (
        str(
            getattr(story, "image_caption", "")
            or getattr(story, "image_alt_text", "")
            or ""
        ).strip()
        if image_url
        else ""
    )
    image_credit = (
        str(getattr(story, "image_credit", "") or "").strip() if image_url else ""
    )
    # Unknown image ownership must not stop the story entering Social Desk.
    # Stage the copy without that image; an editor may add an approved image.
    if image_url and not image_credit:
        image_url = ""
        image_caption = ""

    settings = SocialSettingsStore().load()
    draft.title = title
    draft.text = text
    draft.source_identity = identity
    draft.source_url = source_url
    draft.include_source_url = module_key != "content"
    if module_key == "content":
        draft.internal_source_url = source_url
        draft.source_url = ""
    draft.image_url = image_url
    draft.image_caption = image_caption
    draft.image_credit = image_credit if image_url else ""
    draft.image_rights_status = _rights_status(
        draft.image_url, draft.image_credit, module_key
    )
    draft.source_kind = module_key
    if updates_item_id:
        draft.origin_updates_id = updates_item_id
    if not draft.publication_datetime:
        draft.publication_datetime = (
            datetime.now() + timedelta(minutes=20)
        ).strftime("%Y-%m-%dT%H:%M:%S")
    draft.timezone = draft.timezone or settings.get("timezone") or "Europe/London"
    draft.status = {
        "content": "Local Democracy draft",
        "newsletter": "Newsletter selection draft",
        "police": "Police draft",
        "sport": "Sport draft",
        "council": "Council draft",
    }.get(module_key, "Blank social draft")
    if module_key == "content":
        repair_ldrs_draft(draft)
        draft.text = _add_ldrs_author_credit(draft.text, author)
    draft.updated_at = datetime.now().astimezone().isoformat()
    if not existed:
        drafts.append(draft)
    store.save(drafts)
    SocialHandoffStore().mark(identity, module_key)
    return draft, not existed


def add_story_to_social_desk(
    parent, story, *, module_key: str, updates_item_id: str = ""
) -> SocialDraft | None:
    """Stage a selected Story in Social Desk and report the UI result."""
    try:
        draft, created = stage_story_for_social_desk(
            story,
            module_key=module_key,
            updates_item_id=updates_item_id,
            update_existing=True,
        )
    except ValueError as exc:
        messagebox.showwarning("Add to Socials", str(exc), parent=parent)
        return None
    _show_sent_status(parent)
    messagebox.showinfo(
        "Added to Socials",
        "The existing social draft was updated without creating a duplicate."
        if not created
        else "The content, source link and any credited source image have been staged for social media.",
        parent=parent,
    )
    return draft


__all__ = [
    "add_story_to_social_desk",
    "social_workflow_status",
    "stage_story_for_social_desk",
    "_story_identity",
]

# NewsDesk Reel Builder extension
from newsdesk.reels.integration import install_selection as _install_reel_selection
_install_reel_selection(globals())
