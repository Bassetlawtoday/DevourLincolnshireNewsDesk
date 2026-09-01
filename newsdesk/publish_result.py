"""
newsdesk.publish_result

Represents the complete output of the StoryEngine.

Every processed story should return one PublishResult object.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class PublishResult:
    """
    Complete publishing package returned by StoryEngine.
    """

    # ------------------------------------------------------------------
    # Generated content
    # ------------------------------------------------------------------

    website: str = ""

    facebook: str = ""

    newsletter: str = ""

    breaking_news: str = ""

    html: str = ""

    markdown: str = ""

    plain_text: str = ""

    # ------------------------------------------------------------------
    # SEO and publishing metadata
    # ------------------------------------------------------------------

    seo_title: str = ""

    slug: str = ""

    meta_description: str = ""

    tags: list[str] = field(default_factory=list)

    image_prompt: str = ""

    image_caption: str = ""

    keywords: list[str] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Editorial
    # ------------------------------------------------------------------

    priority: str = ""

    classification: str = ""

    editorial_decision: str = ""

    # ------------------------------------------------------------------
    # Source
    # ------------------------------------------------------------------

    source: str = ""

    published: str = ""

    url: str = ""

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    word_count: int = 0

    reading_time: int = 0

    # ------------------------------------------------------------------
    # Future expansion
    # ------------------------------------------------------------------

    extras: dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------

    @property
    def is_publishable(self) -> bool:
        """
        True when website content has been generated.
        """

        return bool(self.website.strip())

    # ------------------------------------------------------------------

    @property
    def has_social(self) -> bool:
        """
        True when Facebook copy has been generated.
        """

        return bool(self.facebook.strip())

    # ------------------------------------------------------------------

    @property
    def has_newsletter(self) -> bool:
        """
        True when newsletter content has been generated.
        """

        return bool(self.newsletter.strip())

    # ------------------------------------------------------------------

    def add_extra(
        self,
        key: str,
        value: Any,
    ) -> None:
        """
        Store supplementary data without modifying the class structure.
        """

        self.extras[key] = value

    # ------------------------------------------------------------------

    def get_extra(
        self,
        key: str,
        default: Any = None,
    ) -> Any:
        """
        Retrieve supplementary data.
        """

        return self.extras.get(
            key,
            default,
        )

    # ------------------------------------------------------------------

    def summary(self) -> dict[str, Any]:
        """
        Return a lightweight summary for the NewsDesk interface.
        """

        return {
            "publishable": self.is_publishable,
            "website": bool(self.website),
            "facebook": bool(self.facebook),
            "newsletter": bool(self.newsletter),
            "breaking_news": bool(self.breaking_news),
            "priority": self.priority,
            "classification": self.classification,
            "decision": self.editorial_decision,
            "word_count": self.word_count,
            "reading_time": self.reading_time,
            "image_caption": bool(self.image_caption),
            "keywords": len(self.keywords),
        }

    # ------------------------------------------------------------------

    def clear(self) -> None:
        """
        Reset every generated output and metadata field.
        """

        self.website = ""

        self.facebook = ""

        self.newsletter = ""

        self.breaking_news = ""

        self.html = ""

        self.markdown = ""

        self.plain_text = ""

        self.seo_title = ""

        self.slug = ""

        self.meta_description = ""

        self.tags.clear()

        self.image_prompt = ""

        self.image_caption = ""

        self.keywords.clear()

        self.priority = ""

        self.classification = ""

        self.editorial_decision = ""

        self.source = ""

        self.published = ""

        self.url = ""

        self.word_count = 0

        self.reading_time = 0

        self.extras.clear()

    # ------------------------------------------------------------------

    def __str__(self) -> str:
        """
        Return the most useful available title.
        """

        if self.seo_title:
            return self.seo_title

        if self.website:
            return self.website.splitlines()[0]

        return "Empty PublishResult"