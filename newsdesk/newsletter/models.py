"""Serializable models for newsletter editions, items and image rights."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from enum import StrEnum
import hashlib
from html.parser import HTMLParser
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from newsdesk.story import Story


DEFAULT_NEWSLETTER_SECTIONS = [
    "Top Story",
    "Local News",
    "Council and Planning",
    "Police and Public Safety",
    "Events",
    "Sport",
    "Other Briefs",
]


class _NewsletterEventTextParser(HTMLParser):
    """Convert stored event HTML to safe, readable newsletter text."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag, attrs) -> None:
        if tag.casefold() in {"script", "style"}:
            self._ignored_depth += 1
        elif not self._ignored_depth and tag.casefold() in {
            "br", "div", "p", "li", "h1", "h2", "h3", "h4", "h5", "h6"
        }:
            self.parts.append("\n\n")

    def handle_endtag(self, tag) -> None:
        if tag.casefold() in {"script", "style"} and self._ignored_depth:
            self._ignored_depth -= 1
        elif not self._ignored_depth and tag.casefold() in {
            "div", "p", "li", "h1", "h2", "h3", "h4", "h5", "h6"
        }:
            self.parts.append("\n\n")
        elif not self._ignored_depth:
            self.parts.append(" ")

    def handle_data(self, data) -> None:
        if not self._ignored_depth:
            self.parts.append(data)


def clean_event_newsletter_text(value: Any) -> str:
    """Clean legacy or edited EventsDesk copy at the central newsletter boundary."""
    raw = str(value or "").strip()
    if not raw:
        return ""
    raw = re.sub(
        r"\[embed(?:\s[^\]]*)?\].*?\[/embed\]",
        " ",
        raw,
        flags=re.IGNORECASE | re.DOTALL,
    )
    raw = re.sub(r"\\n", " ", raw)
    raw = re.sub(
        r"(?<=[.!?])\s+[^.!?]*?(?:\[…\]|\[\.\.\.\])",
        " ",
        raw,
        flags=re.DOTALL,
    )
    raw = re.sub(r"\s*(?:\[…\]|\[\.\.\.\])\s*", " ", raw)
    # Keep structured event details on separate lines through preview/export.
    raw = re.sub(
        r"\s+(?=(?:When|Where|Price|Age information):\s*)",
        "\n\n",
        raw,
        flags=re.IGNORECASE,
    )
    raw = re.sub(
        r"\bPrice:\s*(\d+(?:\.\d{1,2})?)\b",
        r"Price: £\1",
        raw,
        flags=re.IGNORECASE,
    )
    parser = _NewsletterEventTextParser()
    try:
        parser.feed(raw)
        parser.close()
    except (ValueError, TypeError):
        return " ".join(raw.split())
    paragraphs = [
        " ".join(part.split())
        for part in re.split(r"\n\s*\n", "".join(parser.parts))
    ]
    return "\n\n".join(part for part in paragraphs if part)


def _newsletter_sections(values: list[Any] | None = None) -> list[str]:
    """Return a complete central section list while preserving custom sections."""
    sections = [str(value).strip() for value in (values or []) if str(value).strip()]
    if not sections:
        return list(DEFAULT_NEWSLETTER_SECTIONS)

    for section in DEFAULT_NEWSLETTER_SECTIONS:
        if section in sections:
            continue
        if section == "Events" and "Sport" in sections:
            sections.insert(sections.index("Sport"), section)
        elif section == "Other Briefs":
            sections.append(section)
        elif "Other Briefs" in sections:
            sections.insert(sections.index("Other Briefs"), section)
        else:
            sections.append(section)
    return sections


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return _aware(parsed).astimezone(timezone.utc)


class EditionStatus(StrEnum):
    DRAFT = "draft"
    IN_PREPARATION = "in_preparation"
    READY_FOR_GHOST = "ready_for_ghost"
    SYNCED_TO_GHOST = "synced_to_ghost"
    CHANGED_SINCE_SYNC = "changed_since_sync"
    FINALISED_EXTERNALLY = "finalised_externally"


class ItemStatus(StrEnum):
    SELECTED = "selected"
    EDITED = "edited"
    READY = "ready"
    SYNCED = "synced"


class RightsStatus(StrEnum):
    GREEN = "green"
    GREEN_WITH_CONDITIONS = "green_with_conditions"
    AMBER = "amber"
    RED = "red"


@dataclass(slots=True)
class WeatherBlock:
    included: bool = False
    location: str = "Bassetlaw"
    headline: str = ""
    summary: str = ""
    fetched_at: datetime | None = None
    attribution: str = "Data from MET Norway"
    source_url: str = "https://api.met.no/weatherapi/locationforecast/2.0/documentation"

    def ready(self) -> bool:
        return bool(
            not self.included
            or (
                self.location.strip()
                and self.headline.strip()
                and self.summary.strip()
                and self.fetched_at
                and self.attribution.strip()
                and self.source_url.strip()
            )
        )

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["fetched_at"] = self.fetched_at.isoformat() if self.fetched_at else None
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "WeatherBlock":
        values = dict(data or {})
        values["fetched_at"] = _parse_datetime(values.get("fetched_at"))
        return cls(**values)


@dataclass(slots=True)
class ImageRights:
    """Evidence and enforced permissions for one candidate image."""

    rights_id: str = field(default_factory=lambda: uuid4().hex)
    asset_id: str = ""
    copyright_owner: str = ""
    supplier: str = ""
    original_source: str = ""
    licence_type: str = ""
    evidence_reference: str = ""
    attribution: str = ""
    tenant_key: str = ""
    status: RightsStatus = RightsStatus.RED
    newsletter_use_permitted: bool = False
    commercial_use_permitted: bool = False
    modification_permitted: bool = False
    branding_permitted: bool = False
    expires_at: datetime | None = None
    approved_by: str = ""
    approved_at: datetime | None = None
    notes: str = ""

    def usable(self, *, tenant_key: str, at: datetime | None = None) -> bool:
        current = _aware(at or utc_now()).astimezone(timezone.utc)
        return bool(
            self.status in {RightsStatus.GREEN, RightsStatus.GREEN_WITH_CONDITIONS}
            and self.newsletter_use_permitted
            and self.commercial_use_permitted
            and self.copyright_owner.strip()
            and self.licence_type.strip()
            and self.evidence_reference.strip()
            and (not self.tenant_key or self.tenant_key == tenant_key)
            and (self.expires_at is None or _aware(self.expires_at) > current)
        )

    def brandable(self, *, tenant_key: str, at: datetime | None = None) -> bool:
        return bool(
            self.usable(tenant_key=tenant_key, at=at)
            and self.modification_permitted
            and self.branding_permitted
            and self.status != RightsStatus.AMBER
        )

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["status"] = self.status.value
        result["expires_at"] = self.expires_at.isoformat() if self.expires_at else None
        result["approved_at"] = self.approved_at.isoformat() if self.approved_at else None
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ImageRights":
        values = dict(data)
        values["status"] = RightsStatus(values.get("status", RightsStatus.RED))
        values["expires_at"] = _parse_datetime(values.get("expires_at"))
        values["approved_at"] = _parse_datetime(values.get("approved_at"))
        return cls(**values)


@dataclass(slots=True)
class NewsletterItem:
    item_id: str
    source_identity: str
    source_story_id: str
    module_key: str
    original_title: str
    original_summary: str
    original_url: str
    source_name: str
    source_author: str
    source_published: str
    newsletter_title: str
    newsletter_summary: str
    section: str = "Other Briefs"
    status: ItemStatus = ItemStatus.SELECTED
    selected_by: str = ""
    selected_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    image_asset_id: str = ""
    image_rights: ImageRights | None = None
    image_credit: str = ""
    image_alt_text: str = ""
    image_derivative_path: str = ""
    image_derivative_sha256: str = ""
    image_branded: bool = False
    include_image: bool = False
    notes: str = ""

    @classmethod
    def from_story(
        cls,
        story: Story,
        *,
        module_key: str,
        selected_by: str = "",
        section: str = "Other Briefs",
        now: datetime | None = None,
    ) -> "NewsletterItem":
        selected = _aware(now or utc_now()).astimezone(timezone.utc)
        identity = story_identity(story)
        original_summary = str(story.summary or story.body or "").strip()
        if str(module_key or "").strip().casefold() == "events":
            original_summary = clean_event_newsletter_text(original_summary)
        return cls(
            item_id=uuid4().hex,
            source_identity=identity,
            source_story_id=str(story.story_id or ""),
            module_key=str(module_key or "").strip().casefold(),
            original_title=str(story.title or "").strip(),
            original_summary=original_summary,
            original_url=str(story.url or "").strip(),
            source_name=str(story.source or "").strip(),
            source_author=str(story.author or "").strip(),
            source_published=str(story.published or "").strip(),
            newsletter_title=str(story.title or "").strip(),
            newsletter_summary=original_summary,
            section=section,
            selected_by=str(selected_by or "").strip(),
            selected_at=selected,
            updated_at=selected,
            image_credit=str(story.image_credit or "").strip(),
            image_alt_text=str(story.image_alt_text or "").strip(),
        )

    def ready(self, *, tenant_key: str, at: datetime | None = None) -> bool:
        if not self.newsletter_title.strip() or not self.newsletter_summary.strip():
            return False
        if not self.source_name.strip() or not self.original_url.strip():
            return False
        if not self.include_image:
            return True
        return bool(
            self.image_rights
            and self.image_rights.usable(tenant_key=tenant_key, at=at)
            and (self.image_credit.strip() or not self.image_rights.attribution.strip())
            and self.image_alt_text.strip()
            and self.image_derivative_path.strip()
            and self.image_derivative_sha256.strip()
            and _file_sha256(self.image_derivative_path) == self.image_derivative_sha256
        )

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["status"] = self.status.value
        result["selected_at"] = self.selected_at.isoformat()
        result["updated_at"] = self.updated_at.isoformat()
        result["image_rights"] = self.image_rights.to_dict() if self.image_rights else None
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NewsletterItem":
        values = dict(data)
        if str(values.get("module_key") or "").strip().casefold() == "events":
            values["original_summary"] = clean_event_newsletter_text(
                values.get("original_summary")
            )
            values["newsletter_summary"] = clean_event_newsletter_text(
                values.get("newsletter_summary")
            )
        values["status"] = ItemStatus(values.get("status", ItemStatus.SELECTED))
        values["selected_at"] = _parse_datetime(values.get("selected_at")) or utc_now()
        values["updated_at"] = _parse_datetime(values.get("updated_at")) or utc_now()
        rights = values.get("image_rights")
        values["image_rights"] = ImageRights.from_dict(rights) if rights else None
        return cls(**values)


@dataclass(slots=True)
class NewsletterEvent:
    action: str
    occurred_at: datetime = field(default_factory=utc_now)
    actor: str = ""
    item_id: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "action": self.action,
            "occurred_at": self.occurred_at.isoformat(),
            "actor": self.actor,
            "item_id": self.item_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NewsletterEvent":
        return cls(
            action=str(data.get("action") or ""),
            occurred_at=_parse_datetime(data.get("occurred_at")) or utc_now(),
            actor=str(data.get("actor") or ""),
            item_id=str(data.get("item_id") or ""),
        )


@dataclass(slots=True)
class NewsletterEdition:
    edition_id: str
    tenant_key: str
    title: str
    issue_date: date
    status: EditionStatus = EditionStatus.DRAFT
    introduction: str = ""
    weather: WeatherBlock = field(default_factory=WeatherBlock)
    items: list[NewsletterItem] = field(default_factory=list)
    section_order: list[str] = field(
        default_factory=lambda: list(DEFAULT_NEWSLETTER_SECTIONS)
    )
    lead_item_id: str = ""
    header_image_asset_id: str = ""
    header_image_rights: ImageRights | None = None
    header_image_credit: str = ""
    header_image_alt_text: str = ""
    header_image_derivative_path: str = ""
    header_image_derivative_sha256: str = ""
    include_header_image: bool = False
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    ghost_post_id: str = ""
    ghost_updated_at: datetime | None = None
    last_synced_at: datetime | None = None
    events: list[NewsletterEvent] = field(default_factory=list)

    @classmethod
    def create(
        cls,
        *,
        tenant_key: str,
        title: str,
        issue_date: date,
        actor: str = "",
        now: datetime | None = None,
    ) -> "NewsletterEdition":
        timestamp = _aware(now or utc_now()).astimezone(timezone.utc)
        edition = cls(
            edition_id=uuid4().hex,
            tenant_key=str(tenant_key or "").strip().casefold(),
            title=str(title or "").strip(),
            issue_date=issue_date,
            created_at=timestamp,
            updated_at=timestamp,
        )
        edition.record("edition_created", actor=actor, at=timestamp)
        return edition

    def record(
        self,
        action: str,
        *,
        actor: str = "",
        item_id: str = "",
        at: datetime | None = None,
    ) -> None:
        timestamp = _aware(at or utc_now()).astimezone(timezone.utc)
        self.events.append(NewsletterEvent(action, timestamp, actor, item_id))
        self.events = self.events[-500:]
        self.updated_at = timestamp
        if self.status == EditionStatus.SYNCED_TO_GHOST:
            self.status = EditionStatus.CHANGED_SINCE_SYNC

    def readiness_errors(self, *, at: datetime | None = None) -> list[str]:
        errors: list[str] = []
        if not self.title.strip():
            errors.append("Edition title is required.")
        if not self.items:
            errors.append("At least one newsletter item is required.")
        if not self.weather.ready():
            errors.append("The included weather block is incomplete.")
        if self.include_header_image and not (
            self.header_image_rights
            and self.header_image_rights.usable(tenant_key=self.tenant_key, at=at)
            and self.header_image_alt_text.strip()
            and self.header_image_derivative_path.strip()
            and self.header_image_derivative_sha256.strip()
            and _file_sha256(self.header_image_derivative_path)
            == self.header_image_derivative_sha256
        ):
            errors.append("The selected newsletter header image is not ready.")
        for item in self.items:
            if not item.ready(tenant_key=self.tenant_key, at=at):
                errors.append(f"Item is not ready: {item.newsletter_title or item.original_title}")
        return errors

    def final_review_errors(self, *, at: datetime | None = None) -> list[str]:
        """Return structural blockers before an editor can approve the edition."""

        errors = self.readiness_errors(at=at)
        if not self.introduction.strip():
            errors.append("Edition introduction is required.")
        if self.items and not self.lead_item_id:
            errors.append("Select one lead story.")
        elif self.lead_item_id and not any(
            item.item_id == self.lead_item_id for item in self.items
        ):
            errors.append("The selected lead story is no longer in the edition.")
        return errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "edition_id": self.edition_id,
            "tenant_key": self.tenant_key,
            "title": self.title,
            "issue_date": self.issue_date.isoformat(),
            "status": self.status.value,
            "introduction": self.introduction,
            "weather": self.weather.to_dict(),
            "items": [item.to_dict() for item in self.items],
            "section_order": list(self.section_order),
            "lead_item_id": self.lead_item_id,
            "header_image_asset_id": self.header_image_asset_id,
            "header_image_rights": self.header_image_rights.to_dict() if self.header_image_rights else None,
            "header_image_credit": self.header_image_credit,
            "header_image_alt_text": self.header_image_alt_text,
            "header_image_derivative_path": self.header_image_derivative_path,
            "header_image_derivative_sha256": self.header_image_derivative_sha256,
            "include_header_image": self.include_header_image,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "ghost_post_id": self.ghost_post_id,
            "ghost_updated_at": self.ghost_updated_at.isoformat() if self.ghost_updated_at else None,
            "last_synced_at": self.last_synced_at.isoformat() if self.last_synced_at else None,
            "events": [event.to_dict() for event in self.events],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NewsletterEdition":
        header_rights = data.get("header_image_rights")
        items = [NewsletterItem.from_dict(item) for item in data.get("items", [])]
        sections = _newsletter_sections(data.get("section_order"))
        return cls(
            edition_id=str(data["edition_id"]),
            tenant_key=str(data["tenant_key"]),
            title=str(data.get("title") or ""),
            issue_date=date.fromisoformat(str(data["issue_date"])),
            status=EditionStatus(data.get("status", EditionStatus.DRAFT)),
            introduction=str(data.get("introduction") or ""),
            weather=WeatherBlock.from_dict(data.get("weather")),
            items=items,
            section_order=sections,
            lead_item_id=str(data.get("lead_item_id") or ""),
            header_image_asset_id=str(data.get("header_image_asset_id") or ""),
            header_image_rights=ImageRights.from_dict(header_rights) if header_rights else None,
            header_image_credit=str(data.get("header_image_credit") or ""),
            header_image_alt_text=str(data.get("header_image_alt_text") or ""),
            header_image_derivative_path=str(data.get("header_image_derivative_path") or ""),
            header_image_derivative_sha256=str(data.get("header_image_derivative_sha256") or ""),
            include_header_image=bool(data.get("include_header_image", False)),
            created_at=_parse_datetime(data.get("created_at")) or utc_now(),
            updated_at=_parse_datetime(data.get("updated_at")) or utc_now(),
            ghost_post_id=str(data.get("ghost_post_id") or ""),
            ghost_updated_at=_parse_datetime(data.get("ghost_updated_at")),
            last_synced_at=_parse_datetime(data.get("last_synced_at")),
            events=[NewsletterEvent.from_dict(event) for event in data.get("events", [])],
        )


def story_identity(story: Story) -> str:
    if str(story.story_id or "").strip():
        return "story:" + str(story.story_id).strip().casefold()
    raw_url = str(story.url or "").strip()
    if raw_url:
        parsed = urlsplit(raw_url)
        canonical = urlunsplit(
            (parsed.scheme.casefold(), parsed.netloc.casefold(), parsed.path.rstrip("/"), "", "")
        )
        return "url:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    fallback = "|".join(
        str(value or "").strip().casefold()
        for value in (story.source, story.title, story.published)
    )
    return "content:" + hashlib.sha256(fallback.encode("utf-8")).hexdigest()


def _file_sha256(path: str) -> str:
    try:
        digest = hashlib.sha256()
        with Path(path).open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return ""
