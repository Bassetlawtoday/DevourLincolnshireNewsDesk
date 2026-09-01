"""
newsdesk.story

Core Story model used throughout Devour Lincolnshire NewsDesk.

Every scraper, classifier, formatter and publisher should use this class
instead of passing dictionaries around.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class Story:
    """
    Normalised newsroom story.

    Every NewsDesk module should produce one of these.
    """

    # ------------------------------------------------------------------
    # Editorial content
    # ------------------------------------------------------------------

    title: str = ""

    summary: str = ""

    body: str = ""

    # ------------------------------------------------------------------
    # Source information
    # ------------------------------------------------------------------

    source: str = ""

    url: str = ""

    published: str = ""

    author: str = ""

    # ------------------------------------------------------------------
    # Location and category
    # ------------------------------------------------------------------

    location: str = ""

    category: str = ""

    # ------------------------------------------------------------------
    # Editorial workflow
    # ------------------------------------------------------------------

    priority: str = ""

    classification: str = ""

    editorial_decision: str = ""

    # ------------------------------------------------------------------
    # SEO / Publishing
    # ------------------------------------------------------------------

    slug: str = ""

    seo_title: str = ""

    meta_description: str = ""

    image_prompt: str = ""

    # ------------------------------------------------------------------
    # Source image
    # ------------------------------------------------------------------

    # Original image address supplied by the source website.
    image_url: str = ""

    # Local cached copy created by the shared ImageService.
    image_local_path: str = ""

    # Editorial/source information associated with the image.
    image_caption: str = ""

    image_credit: str = ""

    image_alt_text: str = ""

    # Technical metadata populated by ImageService.
    image_content_type: str = ""

    image_width: int = 0

    image_height: int = 0

    image_file_size: int = 0

    image_cached: bool = False

    image_is_fallback: bool = False

    image_error: str = ""

    tags: list[str] = field(default_factory=list)

    keywords: list[str] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Internal metadata
    # ------------------------------------------------------------------

    story_id: str = ""

    scraped_at: str = ""

    processed_at: str = ""

    notes: str = ""

    extras: dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------

    @property
    def has_body(self) -> bool:
        """
        True when the story contains body text.
        """

        return bool(self.body.strip())

    # ------------------------------------------------------------------

    @property
    def has_summary(self) -> bool:
        """
        True when the story contains a summary.
        """

        return bool(self.summary.strip())

    # ------------------------------------------------------------------

    @property
    def has_image(self) -> bool:
        """
        True when the story has either a source image URL or cached image.
        """

        return bool(
            self.image_url.strip()
            or self.image_local_path.strip()
        )

    # ------------------------------------------------------------------

    @property
    def has_local_image(self) -> bool:
        """
        True when the cached image path currently exists on disk.
        """

        if not self.image_local_path.strip():
            return False

        try:
            from pathlib import Path

            return Path(self.image_local_path).is_file()
        except OSError:
            return False

    # ------------------------------------------------------------------

    @property
    def image_aspect_ratio(self) -> float:
        """
        Return width divided by height, or zero when dimensions are unknown.
        """

        if self.image_height <= 0:
            return 0.0

        return self.image_width / self.image_height

    # ------------------------------------------------------------------

    @property
    def is_publishable(self) -> bool:
        """
        True when the story has a title and either body or summary text.

        This allows shorter Facebook and social-media updates to enter the
        publishing workflow even when they do not have a separate full body.
        """

        return (
            bool(self.title.strip())
            and bool(
                self.body.strip()
                or self.summary.strip()
            )
        )

    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """
        Convert the Story object into a standard dictionary.
        """

        return asdict(self)

    # ------------------------------------------------------------------

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
    ) -> "Story":
        """
        Create a Story from a dictionary.

        Known fields are placed directly on the Story object.

        Unknown fields are stored inside extras so additional source-specific
        data is not lost.
        """

        field_names = set(
            cls.__dataclass_fields__.keys()
        )

        known: dict[str, Any] = {}

        extras: dict[str, Any] = {}

        supplied_extras = data.get("extras")

        if isinstance(supplied_extras, dict):
            extras.update(supplied_extras)

        for key, value in data.items():

            if key == "extras":
                continue

            if key in field_names:
                known[key] = value
            else:
                extras[key] = value

        story = cls(**known)

        story.extras.update(extras)

        return story

    # ------------------------------------------------------------------

    def update(
        self,
        **kwargs: Any,
    ) -> None:
        """
        Update one or more Story fields.

        Unknown fields are stored in extras.
        """

        field_names = set(
            self.__dataclass_fields__.keys()
        )

        for key, value in kwargs.items():

            if key in field_names:
                setattr(
                    self,
                    key,
                    value,
                )
            else:
                self.extras[key] = value

    # ------------------------------------------------------------------

    def attach_image(
        self,
        image_asset: Any,
        *,
        caption: str | None = None,
        credit: str | None = None,
        alt_text: str | None = None,
    ) -> None:
        """
        Attach an ImageService result without coupling Story to the service.

        ``image_asset`` may be an ``ImageAsset`` instance or any object with
        the same public attributes. This duck-typed approach keeps the core
        Story model independent from network and caching services.
        """

        self.image_url = str(
            getattr(image_asset, "source_url", "") or ""
        )

        self.image_local_path = str(
            getattr(image_asset, "local_path", "") or ""
        )

        self.image_content_type = str(
            getattr(image_asset, "content_type", "") or ""
        )

        self.image_width = int(
            getattr(image_asset, "width", 0) or 0
        )

        self.image_height = int(
            getattr(image_asset, "height", 0) or 0
        )

        self.image_file_size = int(
            getattr(image_asset, "file_size", 0) or 0
        )

        self.image_cached = bool(
            getattr(image_asset, "cached", False)
        )

        self.image_is_fallback = bool(
            getattr(image_asset, "is_fallback", False)
        )

        self.image_error = str(
            getattr(image_asset, "error", "") or ""
        )

        if caption is not None:
            self.image_caption = str(caption).strip()

        if credit is not None:
            self.image_credit = str(credit).strip()

        if alt_text is not None:
            self.image_alt_text = str(alt_text).strip()

    # ------------------------------------------------------------------

    def clear(self) -> None:
        """
        Reset editable editorial and publishing content.

        Source and workflow metadata are retained so the Story object can
        continue to represent the same collected source item.
        """

        self.title = ""

        self.summary = ""

        self.body = ""

        self.location = ""

        self.category = ""

        self.slug = ""

        self.seo_title = ""

        self.meta_description = ""

        self.image_prompt = ""

        # Keep the collected source image and cache metadata attached to the
        # story. Only editable presentation text is cleared.
        self.image_caption = ""

        self.image_alt_text = ""

        self.tags.clear()

        self.keywords.clear()

        self.notes = ""

    # ------------------------------------------------------------------

    def __str__(self) -> str:
        """
        Return a useful human-readable representation.
        """

        return self.title or "Untitled Story"