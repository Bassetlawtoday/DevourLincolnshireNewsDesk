"""Central newsletter edition operations independent of UI and Ghost."""

from __future__ import annotations

from datetime import date, datetime

from newsdesk.story import Story

from .models import (
    EditionStatus, ImageRights, ItemStatus, NewsletterEdition, NewsletterItem,
    WeatherBlock, clean_event_newsletter_text,
)
from .store import NewsletterStore


class DuplicateNewsletterItemError(ValueError):
    pass


class NewsletterService:
    def __init__(self, store: NewsletterStore | None = None) -> None:
        self.store = store or NewsletterStore()

    def list_editions(self, *, tenant_key: str | None = None) -> list[NewsletterEdition]:
        editions = self.store.load()
        if tenant_key is not None:
            tenant = str(tenant_key).strip().casefold()
            editions = [edition for edition in editions if edition.tenant_key == tenant]
        return sorted(editions, key=lambda edition: edition.issue_date, reverse=True)

    def create_edition(
        self,
        *,
        tenant_key: str,
        title: str,
        issue_date: date,
        actor: str = "",
        now: datetime | None = None,
    ) -> NewsletterEdition:
        if not str(tenant_key or "").strip():
            raise ValueError("Tenant key is required.")
        if not str(title or "").strip():
            raise ValueError("Edition title is required.")
        editions = self.store.load()
        edition = NewsletterEdition.create(
            tenant_key=tenant_key,
            title=title,
            issue_date=issue_date,
            actor=actor,
            now=now,
        )
        editions.append(edition)
        self.store.save(editions)
        return edition

    def add_story(
        self,
        edition_id: str,
        story: Story,
        *,
        module_key: str,
        selected_by: str = "",
        section: str = "Other Briefs",
        newsletter_title: str | None = None,
        newsletter_summary: str | None = None,
        now: datetime | None = None,
    ) -> NewsletterItem:
        editions, edition = self._load_target(edition_id)
        candidate = NewsletterItem.from_story(
            story,
            module_key=module_key,
            selected_by=selected_by,
            section=section,
            now=now,
        )
        if newsletter_title is not None:
            cleaned_title = str(newsletter_title).strip()
            if not cleaned_title:
                raise ValueError("Newsletter title is required.")
            candidate.newsletter_title = cleaned_title
        if newsletter_summary is not None:
            candidate.newsletter_summary = str(newsletter_summary).strip()
        if any(item.source_identity == candidate.source_identity for item in edition.items):
            raise DuplicateNewsletterItemError("Story is already in this newsletter edition.")
        self._return_to_preparation(edition)
        edition.items.append(candidate)
        edition.record("item_added", actor=selected_by, item_id=candidate.item_id, at=now)
        self.store.save(editions)
        return candidate

    def remove_item(
        self, edition_id: str, item_id: str, *, actor: str = "", now: datetime | None = None
    ) -> None:
        editions, edition = self._load_target(edition_id)
        retained = [item for item in edition.items if item.item_id != item_id]
        if len(retained) == len(edition.items):
            raise KeyError(f"Newsletter item not found: {item_id}")
        self._return_to_preparation(edition)
        edition.items = retained
        if edition.lead_item_id == item_id:
            edition.lead_item_id = ""
        edition.record("item_removed", actor=actor, item_id=item_id, at=now)
        self.store.save(editions)

    def reorder_items(
        self,
        edition_id: str,
        ordered_item_ids: list[str],
        *,
        actor: str = "",
        now: datetime | None = None,
    ) -> None:
        editions, edition = self._load_target(edition_id)
        existing = {item.item_id: item for item in edition.items}
        if len(ordered_item_ids) != len(set(ordered_item_ids)):
            raise ValueError("Item order contains duplicates.")
        if set(ordered_item_ids) != set(existing):
            raise ValueError("Item order must contain every edition item exactly once.")
        self._return_to_preparation(edition)
        edition.items = [existing[item_id] for item_id in ordered_item_ids]
        edition.record("items_reordered", actor=actor, at=now)
        self.store.save(editions)

    def move_item(
        self,
        edition_id: str,
        item_id: str,
        direction: int,
        *,
        actor: str = "",
        now: datetime | None = None,
    ) -> None:
        if direction not in {-1, 1}:
            raise ValueError("Item direction must be -1 or 1.")
        editions, edition = self._load_target(edition_id)
        index = next(
            (position for position, item in enumerate(edition.items) if item.item_id == item_id),
            None,
        )
        if index is None:
            raise KeyError(f"Newsletter item not found: {item_id}")
        target = index + direction
        if target < 0 or target >= len(edition.items):
            return
        self._return_to_preparation(edition)
        edition.items[index], edition.items[target] = edition.items[target], edition.items[index]
        edition.record("item_moved", actor=actor, item_id=item_id, at=now)
        self.store.save(editions)

    def set_lead_item(
        self,
        edition_id: str,
        item_id: str,
        *,
        actor: str = "",
        now: datetime | None = None,
    ) -> None:
        editions, edition = self._load_target(edition_id)
        cleaned = str(item_id or "").strip()
        if cleaned and not any(item.item_id == cleaned for item in edition.items):
            raise KeyError(f"Newsletter item not found: {item_id}")
        self._return_to_preparation(edition)
        edition.lead_item_id = cleaned
        edition.record(
            "lead_item_selected" if cleaned else "lead_item_cleared",
            actor=actor,
            item_id=cleaned,
            at=now,
        )
        self.store.save(editions)

    def get_edition(self, edition_id: str) -> NewsletterEdition:
        _, edition = self._load_target(edition_id)
        return edition

    def delete_empty_draft_edition(
        self,
        edition_id: str,
        *,
        actor: str = "",
        now: datetime | None = None,
    ) -> None:
        editions, edition = self._load_target(edition_id)
        if edition.items:
            raise ValueError("Only an empty newsletter edition can be deleted.")
        if edition.status != EditionStatus.DRAFT:
            raise ValueError("Only a draft newsletter edition can be deleted.")
        if edition.ghost_post_id or edition.last_synced_at:
            raise ValueError("A newsletter edition linked to Ghost cannot be deleted here.")
        editions = [value for value in editions if value.edition_id != edition_id]
        self.store.save(editions)

    def update_edition(
        self,
        edition_id: str,
        *,
        title: str | None = None,
        issue_date: date | None = None,
        introduction: str | None = None,
        weather: WeatherBlock | None = None,
        status: EditionStatus | str | None = None,
        actor: str = "",
        now: datetime | None = None,
    ) -> NewsletterEdition:
        editions, edition = self._load_target(edition_id)
        if status is None:
            self._return_to_preparation(edition)
        if title is not None:
            cleaned = str(title).strip()
            if not cleaned:
                raise ValueError("Edition title is required.")
            edition.title = cleaned
        if issue_date is not None:
            edition.issue_date = issue_date
        if introduction is not None:
            edition.introduction = str(introduction).strip()
        if weather is not None:
            edition.weather = weather
        if status is not None:
            edition.status = EditionStatus(status)
        edition.record("edition_updated", actor=actor, at=now)
        self.store.save(editions)
        return edition

    def update_item(
        self,
        edition_id: str,
        item_id: str,
        *,
        newsletter_title: str | None = None,
        newsletter_summary: str | None = None,
        section: str | None = None,
        notes: str | None = None,
        status: ItemStatus | str | None = None,
        actor: str = "",
        now: datetime | None = None,
    ) -> NewsletterItem:
        editions, edition = self._load_target(edition_id)
        item = next((value for value in edition.items if value.item_id == item_id), None)
        if item is None:
            raise KeyError(f"Newsletter item not found: {item_id}")
        self._return_to_preparation(edition)
        if newsletter_title is not None:
            item.newsletter_title = str(newsletter_title).strip()
        if newsletter_summary is not None:
            cleaned_summary = str(newsletter_summary).strip()
            if item.module_key == "events":
                cleaned_summary = clean_event_newsletter_text(cleaned_summary)
            item.newsletter_summary = cleaned_summary
        if section is not None:
            cleaned_section = str(section).strip()
            if cleaned_section not in edition.section_order:
                raise ValueError("Newsletter section is not valid for this edition.")
            item.section = cleaned_section
        if notes is not None:
            item.notes = str(notes).strip()
        if status is not None:
            item.status = ItemStatus(status)
        item.updated_at = now or datetime.now().astimezone()
        edition.record("item_updated", actor=actor, item_id=item_id, at=now)
        self.store.save(editions)
        return item

    def set_item_image(
        self,
        edition_id: str,
        item_id: str,
        *,
        asset_id: str,
        rights: ImageRights,
        credit: str,
        alt_text: str,
        derivative_path: str,
        derivative_sha256: str,
        branded: bool,
        actor: str = "",
        now: datetime | None = None,
    ) -> NewsletterItem:
        editions, edition = self._load_target(edition_id)
        item = next((value for value in edition.items if value.item_id == item_id), None)
        if item is None:
            raise KeyError(f"Newsletter item not found: {item_id}")
        if not rights.usable(tenant_key=edition.tenant_key, at=now):
            raise ValueError("The selected image is not approved for this newsletter.")
        if not str(alt_text).strip() or not str(derivative_path).strip() or not str(derivative_sha256).strip():
            raise ValueError("Approved image derivative, hash and alt text are required.")
        self._return_to_preparation(edition)
        item.image_asset_id = str(asset_id).strip()
        item.image_rights = rights
        item.image_credit = str(credit).strip()
        item.image_alt_text = str(alt_text).strip()
        item.image_derivative_path = str(derivative_path).strip()
        item.image_derivative_sha256 = str(derivative_sha256).strip()
        item.image_branded = bool(branded)
        item.include_image = True
        item.updated_at = now or datetime.now().astimezone()
        edition.record("item_image_approved", actor=actor, item_id=item_id, at=now)
        self.store.save(editions)
        return item

    def clear_item_image(
        self, edition_id: str, item_id: str, *, actor: str = "", now: datetime | None = None
    ) -> NewsletterItem:
        editions, edition = self._load_target(edition_id)
        item = next((value for value in edition.items if value.item_id == item_id), None)
        if item is None:
            raise KeyError(f"Newsletter item not found: {item_id}")
        self._return_to_preparation(edition)
        item.image_asset_id = ""
        item.image_rights = None
        item.image_credit = ""
        item.image_alt_text = ""
        item.image_derivative_path = ""
        item.image_derivative_sha256 = ""
        item.image_branded = False
        item.include_image = False
        item.updated_at = now or datetime.now().astimezone()
        edition.record("item_image_cleared", actor=actor, item_id=item_id, at=now)
        self.store.save(editions)
        return item

    def mark_ready_for_final_review(
        self,
        edition_id: str,
        *,
        editorial_confirmed: bool,
        attribution_confirmed: bool,
        image_rights_confirmed: bool,
        actor: str = "",
        now: datetime | None = None,
    ) -> NewsletterEdition:
        editions, edition = self._load_target(edition_id)
        errors = edition.final_review_errors(at=now)
        if errors:
            raise ValueError("Final review is blocked: " + " ".join(errors))
        if not editorial_confirmed:
            raise ValueError("Confirm that the newsletter wording has been editorially reviewed.")
        if not attribution_confirmed:
            raise ValueError("Confirm that source credits and links have been checked.")
        if not image_rights_confirmed:
            raise ValueError("Confirm that the image-rights position has been checked.")
        edition.status = EditionStatus.READY_FOR_GHOST
        edition.record("final_review_approved", actor=actor, at=now)
        self.store.save(editions)
        return edition

    def set_header_image(
        self, edition_id: str, *, asset_id: str, rights, credit: str,
        alt_text: str, derivative_path: str, derivative_sha256: str,
        actor: str = "local_editor",
    ):
        editions, edition = self._load_target(edition_id)
        if not rights.usable(tenant_key=edition.tenant_key):
            raise ValueError("The selected header image is not approved for this newsletter.")
        if not derivative_path or not derivative_sha256 or not str(alt_text).strip():
            raise ValueError("Approved header derivative, hash and alt text are required.")
        edition.header_image_asset_id = str(asset_id).strip()
        edition.header_image_rights = rights
        edition.header_image_credit = str(credit).strip()
        edition.header_image_alt_text = str(alt_text).strip()
        edition.header_image_derivative_path = str(derivative_path).strip()
        edition.header_image_derivative_sha256 = str(derivative_sha256).strip()
        edition.include_header_image = True
        edition.record("header_image_approved", actor=actor)
        self.store.save(editions)
        return edition

    def clear_header_image(self, edition_id: str, *, actor: str = "local_editor"):
        editions, edition = self._load_target(edition_id)
        edition.header_image_asset_id = ""
        edition.header_image_rights = None
        edition.header_image_credit = ""
        edition.header_image_alt_text = ""
        edition.header_image_derivative_path = ""
        edition.header_image_derivative_sha256 = ""
        edition.include_header_image = False
        edition.record("header_image_cleared", actor=actor)
        self.store.save(editions)
        return edition

    def return_to_editing(
        self,
        edition_id: str,
        *,
        actor: str = "",
        now: datetime | None = None,
    ) -> NewsletterEdition:
        editions, edition = self._load_target(edition_id)
        edition.status = EditionStatus.IN_PREPARATION
        edition.record("returned_to_editing", actor=actor, at=now)
        self.store.save(editions)
        return edition

    def mark_finalised_externally(
        self, edition_id: str, *, actor: str = "", now: datetime | None = None,
    ) -> NewsletterEdition:
        """Record a human-confirmed Ghost completion; never contacts Ghost."""

        editions, edition = self._load_target(edition_id)
        if not edition.ghost_post_id or edition.status != EditionStatus.SYNCED_TO_GHOST:
            raise ValueError("Only a currently synced Ghost draft can be marked finalised.")
        edition.status = EditionStatus.FINALISED_EXTERNALLY
        edition.record("finalised_externally_confirmed", actor=actor, at=now)
        self.store.save(editions)
        return edition

    @staticmethod
    def _return_to_preparation(edition: NewsletterEdition) -> None:
        if edition.status == EditionStatus.SYNCED_TO_GHOST:
            edition.status = EditionStatus.CHANGED_SINCE_SYNC
        elif edition.status in {
            EditionStatus.READY_FOR_GHOST,
            EditionStatus.FINALISED_EXTERNALLY,
        }:
            edition.status = EditionStatus.IN_PREPARATION

    def _load_target(
        self, edition_id: str
    ) -> tuple[list[NewsletterEdition], NewsletterEdition]:
        editions = self.store.load()
        edition = next(
            (candidate for candidate in editions if candidate.edition_id == edition_id),
            None,
        )
        if edition is None:
            raise KeyError(f"Newsletter edition not found: {edition_id}")
        return editions, edition
