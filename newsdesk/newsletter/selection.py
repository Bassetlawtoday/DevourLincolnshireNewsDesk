"""Shared Add to Newsletter workflow for every intelligence module."""

from __future__ import annotations

from datetime import date, datetime
import hashlib
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk

from newsdesk.story import Story
from newsdesk.image_preview_cache import IMAGE_PREVIEW_CACHE
from newsdesk.theme import (
    ACCENT, APP_BG, BORDER, CARD_BG, HEADER_BG, SUCCESS,
    TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY,
)

from .images import ImageLibrary
from .models import EditionStatus, ImageRights, RightsStatus, story_identity
from .service import DuplicateNewsletterItemError, NewsletterService


TENANT_KEY = "devour_lincolnshire"
EDITABLE_STATUSES = {
    EditionStatus.DRAFT,
    EditionStatus.IN_PREPARATION,
    EditionStatus.CHANGED_SINCE_SYNC,
}


def _source_image_path(story: Story) -> Path | None:
    """Return a genuine downloaded source image, never a fallback placeholder."""
    if bool(getattr(story, "image_is_fallback", False)):
        return None
    value = str(getattr(story, "image_local_path", "") or "").strip()
    if not value:
        return None
    path = Path(value)
    return path if path.is_file() else None


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _attach_approved_asset(service, images, edition, item, asset, *, actor):
    derivative = images.create_derivative(asset.asset_id, tenant_key=TENANT_KEY)
    service.set_item_image(
        edition.edition_id,
        item.item_id,
        asset_id=asset.asset_id,
        rights=asset.rights,
        credit=derivative.credit,
        alt_text=derivative.alt_text,
        derivative_path=derivative.path,
        derivative_sha256=derivative.sha256,
        branded=derivative.branded,
        actor=actor,
    )


def _open_source_image_review(parent, story, edition, item, service, *, actor, on_changed=None):
    """Review a downloaded source image through the central rights-controlled library."""
    source_path = _source_image_path(story)
    if source_path is None:
        return None
    images = ImageLibrary()
    try:
        source_hash = _file_sha256(source_path)
        duplicate = next(
            (
                asset for asset in images.list_assets(tenant_key=TENANT_KEY)
                if asset.master_sha256 == source_hash
                and asset.rights.usable(tenant_key=TENANT_KEY)
            ),
            None,
        )
    except OSError as exc:
        messagebox.showerror("Image review", f"The downloaded image could not be read: {exc}", parent=parent)
        return None
    if duplicate is not None:
        if messagebox.askyesno(
            "Approved image found",
            f"This image is already approved as ‘{duplicate.title}’.\n\nAttach the approved image to this newsletter story?",
            parent=parent,
        ):
            try:
                _attach_approved_asset(service, images, edition, item, duplicate, actor=actor)
            except (KeyError, ValueError, OSError) as exc:
                messagebox.showerror("Image not attached", str(exc), parent=parent)
                return None
            messagebox.showinfo("Image attached", "The existing approved image was attached to the newsletter story.", parent=parent)
            if on_changed is not None:
                on_changed()
        return duplicate

    dialog = ctk.CTkToplevel(parent)
    dialog.title("Review source image rights")
    dialog.geometry("760x790")
    dialog.minsize(680, 620)
    dialog.configure(fg_color=APP_BG)
    dialog.transient(parent)
    dialog.grab_set()
    outer = ctk.CTkScrollableFrame(dialog, fg_color=HEADER_BG)
    outer.pack(fill="both", expand=True, padx=20, pady=20)
    ctk.CTkLabel(
        outer, text="REVIEW SOURCE IMAGE RIGHTS", font=("Arial", 20, "bold"),
        text_color=TEXT_PRIMARY, anchor="w",
    ).pack(fill="x", padx=16, pady=(14, 4))
    ctk.CTkLabel(
        outer,
        text=("The image has been downloaded from the original story. Complete the rights record below before it can be added to the newsletter."),
        text_color=TEXT_SECONDARY, anchor="w", justify="left", wraplength=680,
    ).pack(fill="x", padx=16, pady=(0, 12))
    ctk.CTkLabel(
        outer, text=f"Downloaded file: {source_path.name}", text_color=TEXT_MUTED,
        anchor="w", wraplength=680,
    ).pack(fill="x", padx=16, pady=(0, 12))
    preview = IMAGE_PREVIEW_CACHE.get(source_path, (660, 230))
    if preview is not None:
        dialog._source_image_preview = ctk.CTkImage(
            light_image=preview, dark_image=preview, size=preview.size,
        )
        ctk.CTkLabel(
            outer, text="", image=dialog._source_image_preview,
        ).pack(padx=16, pady=(0, 14))

    fields = {}
    defaults = {
        "title": str((story.extras or {}).get("image_title") or story.title or "").strip(),
        "owner": "",
        "supplier": str(story.source or "").strip(),
        "source": str(story.image_url or story.url or "").strip(),
        "licence": "",
        "evidence": "",
        "credit": str(story.image_credit or story.source or "").strip(),
        "alt": str(story.image_alt_text or story.title or "").strip(),
        "topics": str(story.category or "").strip(),
        "locations": str(story.location or "").strip(),
    }
    for key, label in (
        ("title", "Image title"), ("owner", "Copyright owner"),
        ("supplier", "Supplier"), ("source", "Original image/source URL"),
        ("licence", "Licence type"), ("evidence", "Licence evidence/reference"),
        ("credit", "Required credit"), ("alt", "Alt text"),
        ("topics", "Topics (comma-separated)"), ("locations", "Locations (comma-separated)"),
    ):
        ctk.CTkLabel(outer, text=label, text_color=TEXT_SECONDARY, anchor="w").pack(fill="x", padx=16)
        entry = ctk.CTkEntry(outer, height=34)
        entry.pack(fill="x", padx=16, pady=(2, 7))
        entry.insert(0, defaults[key])
        fields[key] = entry

    permitted = ctk.BooleanVar(value=False)
    modification = ctk.BooleanVar(value=False)
    branding = ctk.BooleanVar(value=False)
    ctk.CTkCheckBox(
        outer,
        text="I confirm the licence permits newsletter and commercial use",
        variable=permitted, text_color=TEXT_PRIMARY,
    ).pack(anchor="w", padx=16, pady=(8, 4))
    ctk.CTkCheckBox(
        outer, text="Licence permits modification", variable=modification,
        text_color=TEXT_PRIMARY,
    ).pack(anchor="w", padx=16, pady=4)
    ctk.CTkCheckBox(
        outer, text="Licence permits logo branding", variable=branding,
        text_color=TEXT_PRIMARY,
    ).pack(anchor="w", padx=16, pady=4)
    feedback = ctk.CTkLabel(outer, text="", text_color=ACCENT, anchor="w", wraplength=680)
    feedback.pack(fill="x", padx=16, pady=6)
    actions = ctk.CTkFrame(outer, fg_color="transparent")
    actions.pack(fill="x", padx=16, pady=(6, 16))

    def approve_and_attach():
        try:
            required = ("title", "owner", "licence", "evidence", "alt")
            if any(not fields[key].get().strip() for key in required):
                raise ValueError("Complete the title, copyright owner, licence, evidence and alt text.")
            if not permitted.get():
                raise ValueError("Confirm newsletter and commercial use before approving the image.")
            now = datetime.now().astimezone()
            rights = ImageRights(
                copyright_owner=fields["owner"].get().strip(),
                supplier=fields["supplier"].get().strip(),
                original_source=fields["source"].get().strip(),
                licence_type=fields["licence"].get().strip(),
                evidence_reference=fields["evidence"].get().strip(),
                attribution=fields["credit"].get().strip(),
                tenant_key=TENANT_KEY,
                status=RightsStatus.GREEN,
                newsletter_use_permitted=True,
                commercial_use_permitted=True,
                modification_permitted=modification.get(),
                branding_permitted=branding.get(),
                approved_by=actor,
                approved_at=now,
            )
            asset = images.import_asset(
                source_path,
                tenant_key=TENANT_KEY,
                title=fields["title"].get(),
                rights=rights,
                alt_text=fields["alt"].get(),
                topics=fields["topics"].get().split(","),
                locations=fields["locations"].get().split(","),
                actor=actor,
            )
            _attach_approved_asset(service, images, edition, item, asset, actor=actor)
        except (KeyError, ValueError, OSError) as exc:
            feedback.configure(text=str(exc))
            return
        dialog.grab_release()
        dialog.destroy()
        messagebox.showinfo("Image approved", "The approved image was added to the library and attached to the newsletter story.", parent=parent)
        if on_changed is not None:
            on_changed()

    ctk.CTkButton(actions, text="CANCEL", width=110, fg_color="#374151", command=dialog.destroy).pack(side="right")
    ctk.CTkButton(actions, text="APPROVE AND ATTACH", width=190, fg_color=ACCENT, command=approve_and_attach).pack(side="right", padx=(0, 8))
    dialog.bind("<Escape>", lambda _event: dialog.destroy())
    dialog.after(120, fields["owner"].focus_set)
    return dialog


def planning_story(application: dict) -> Story:
    """Create a provenance-preserving Story from a planning application."""

    proposal = str(
        application.get("proposal_summary")
        or application.get("proposal")
        or application.get("description")
        or "Planning application"
    ).strip()
    reference = str(application.get("reference") or "").strip()
    area = str(application.get("area") or application.get("location") or "").strip()
    url = str(
        application.get("url")
        or application.get("application_url")
        or application.get("source_url")
        or ""
    ).strip()
    summary_parts = [proposal]
    if reference:
        summary_parts.append(f"Planning reference: {reference}")
    if area:
        summary_parts.append(f"Location: {area}")
    return Story(
        story_id=f"planning:{reference}" if reference else "",
        title=proposal,
        summary=". ".join(summary_parts),
        source=str(application.get("authority") or "Bassetlaw District Council").strip(),
        url=url,
        published=str(
            application.get("received_date")
            or application.get("published")
            or application.get("date")
            or ""
        ).strip(),
        category="Planning",
    )


def open_add_to_newsletter(
    parent,
    story: Story,
    *,
    module_key: str,
    service: NewsletterService | None = None,
    actor: str = "local_editor",
    newsletter_copy: str = "",
    on_changed=None,
):
    """Open the controlled edition/section chooser for one selected story."""

    service = service or NewsletterService()
    editions = [
        edition for edition in service.list_editions(tenant_key=TENANT_KEY)
        if edition.status in EDITABLE_STATUSES
    ]
    if not editions:
        messagebox.showinfo(
            "Add to Newsletter",
            "Create a draft edition in Newsletter Desk before selecting stories.",
            parent=parent,
        )
        if on_changed is not None:
            on_changed()
        return None
    if not str(story.title or "").strip():
        messagebox.showwarning(
            "Add to Newsletter", "The selected story has no title.", parent=parent,
        )
        return None
    if not str(story.url or "").strip():
        messagebox.showwarning(
            "Add to Newsletter",
            "This story has no source link, so it cannot yet be added with legal provenance.",
            parent=parent,
        )
        return None

    dialog = ctk.CTkToplevel(parent)
    dialog.title("Add to Newsletter")
    has_source_image = _source_image_path(story) is not None
    dialog.geometry("760x530" if has_source_image else "680x500")
    dialog.resizable(False, False)
    dialog.configure(fg_color=APP_BG)
    dialog.transient(parent)
    dialog.grab_set()

    panel = ctk.CTkFrame(
        dialog, fg_color=HEADER_BG, border_width=1,
        border_color=BORDER, corner_radius=12,
    )
    panel.pack(fill="both", expand=True, padx=22, pady=22)
    ctk.CTkLabel(
        panel, text="ADD TO NEWSLETTER", font=("Arial", 20, "bold"),
        text_color=TEXT_PRIMARY, anchor="w",
    ).pack(fill="x", padx=20, pady=(18, 5))
    ctk.CTkLabel(
        panel, text=str(story.title), text_color=TEXT_SECONDARY,
        anchor="w", justify="left", wraplength=610,
    ).pack(fill="x", padx=20, pady=(0, 14))

    labels = {
        f"{edition.issue_date.strftime('%d/%m/%Y')} — {edition.title}": edition
        for edition in editions
    }
    ctk.CTkLabel(panel, text="Destination edition", text_color=TEXT_SECONDARY, anchor="w").pack(fill="x", padx=20)
    edition_menu = ctk.CTkOptionMenu(panel, values=list(labels), height=38)
    edition_menu.pack(fill="x", padx=20, pady=(4, 12))

    ctk.CTkLabel(panel, text="Newsletter section", text_color=TEXT_SECONDARY, anchor="w").pack(fill="x", padx=20)
    section_menu = ctk.CTkOptionMenu(
        panel, values=list(editions[0].section_order), height=38,
    )
    section_menu.pack(fill="x", padx=20, pady=(4, 12))

    def edition_changed(label):
        edition = labels[label]
        section_menu.configure(values=list(edition.section_order))
        section_menu.set(_default_section(module_key, edition.section_order))

    edition_menu.configure(command=edition_changed)
    edition_menu.set(next(iter(labels)))
    edition_changed(edition_menu.get())

    legal = ctk.CTkFrame(panel, fg_color=CARD_BG, corner_radius=8)
    legal.pack(fill="x", padx=20, pady=(2, 12))
    ctk.CTkLabel(
        legal,
        text=(
            "A downloaded source image is available. You can review its rights after adding the story; "
            "it will remain excluded unless approval is completed."
            if has_source_image else
            "Source credit and original link will be retained. No image is included."
        ),
        text_color=SUCCESS, anchor="w", justify="left", wraplength=590,
    ).pack(fill="x", padx=12, pady=10)

    feedback = ctk.CTkLabel(panel, text="", text_color=ACCENT, anchor="w")
    feedback.pack(fill="x", padx=20)
    actions = ctk.CTkFrame(panel, fg_color="transparent")
    actions.pack(fill="x", padx=20, pady=(5, 16))

    def add(*, review_image=False):
        edition = labels[edition_menu.get()]
        try:
            item = service.add_story(
                edition.edition_id,
                story,
                module_key=module_key,
                selected_by=actor,
                section=section_menu.get(),
                newsletter_summary=str(newsletter_copy or "").strip() or None,
            )
        except DuplicateNewsletterItemError as exc:
            feedback.configure(text=str(exc))
            return
        except (KeyError, ValueError, OSError) as exc:
            feedback.configure(text=f"Could not add story: {exc}")
            return
        dialog.grab_release()
        dialog.destroy()
        if on_changed is not None:
            on_changed()
        if review_image and has_source_image:
            return _open_source_image_review(
                parent, story, edition, item, service,
                actor=actor, on_changed=on_changed,
            )
        messagebox.showinfo(
            "Added to Newsletter",
            f"The story was added to {edition.title}.\n\nNo image was included.",
            parent=parent,
        )

    ctk.CTkButton(
        actions, text="CANCEL", width=110, fg_color="#374151",
        command=dialog.destroy,
    ).pack(side="right")
    if has_source_image:
        ctk.CTkButton(
            actions, text="ADD WITHOUT IMAGE", width=155,
            fg_color="#374151", command=lambda: add(review_image=False),
        ).pack(side="right", padx=(0, 8))
        ctk.CTkButton(
            actions, text="ADD STORY + REVIEW IMAGE", width=215,
            fg_color=ACCENT, command=lambda: add(review_image=True),
        ).pack(side="right", padx=(0, 8))
    else:
        ctk.CTkButton(
            actions, text="ADD STORY", width=150, fg_color=ACCENT,
            command=lambda: add(review_image=False),
        ).pack(side="right", padx=(0, 8))
    dialog.bind("<Return>", lambda _event: add(review_image=has_source_image))
    dialog.bind("<Escape>", lambda _event: dialog.destroy())
    return dialog


def find_story_memberships(
    story: Story,
    *,
    service: NewsletterService | None = None,
    tenant_key: str = TENANT_KEY,
):
    """Return editions/items containing a story, newest edition first."""

    service = service or NewsletterService()
    identity = story_identity(story)
    matches = []
    for edition in service.list_editions(tenant_key=tenant_key):
        for item in edition.items:
            if item.source_identity == identity:
                matches.append((edition, item))
    return matches


def newsletter_action_label(
    story: Story, *, service: NewsletterService | None = None,
) -> str:
    """Return the central action label for a module story."""

    return (
        "IN NEWSLETTER"
        if find_story_memberships(story, service=service)
        else "ADD TO NEWSLETTER"
    )


def configure_newsletter_action(action_bar, story: Story, *, service=None) -> str:
    """Apply the current newsletter membership label to a shared action bar."""

    label = newsletter_action_label(story, service=service)
    action_bar.set_text("ADD TO NEWSLETTER", label)
    return label


def open_newsletter_action(
    parent,
    story: Story,
    *,
    module_key: str,
    service: NewsletterService | None = None,
    actor: str = "local_editor",
    newsletter_copy: str = "",
    on_changed=None,
):
    """Open an existing newsletter item or start the controlled add workflow."""

    service = service or NewsletterService()
    memberships = find_story_memberships(story, service=service)
    if memberships:
        edition, item = memberships[0]
        from modules.newsletter_desk import open_newsletter_desk

        return open_newsletter_desk(
            parent,
            service=service,
            edition_id=edition.edition_id,
            item_id=item.item_id,
        )
    return open_add_to_newsletter(
        parent,
        story,
        module_key=module_key,
        service=service,
        actor=actor,
        newsletter_copy=newsletter_copy,
        on_changed=on_changed,
    )


def _default_section(module_key: str, sections: list[str]) -> str:
    preferred = {
        "planning": "Council and Planning",
        "council": "Council and Planning",
        "police": "Police and Public Safety",
        "fire": "Police and Public Safety",
        "sport": "Sport",
        "events": "Events",
        "content": "Council and Planning",
    }.get(str(module_key).strip().casefold(), "Other Briefs")
    return preferred if preferred in sections else sections[0]


__all__ = [
    "configure_newsletter_action",
    "find_story_memberships",
    "newsletter_action_label",
    "open_add_to_newsletter",
    "open_newsletter_action",
    "planning_story",
]
