"""Shared cleaning and formatting utilities for NewsDesk."""

from __future__ import annotations

from html import unescape
import re
from typing import Any, Iterable


class BaseFormatter:
    """Common newsroom formatting and source-cleaning utilities."""

    BOILERPLATE_LINES = {
        "main article content",
        "main content",
        "article content",
        "news",
        "latest news",
        "published",
        "published:",
        "updated",
        "updated:",
        "share",
        "share this article",
        "share this page",
        "back to news",
        "back to top",
        "skip to main content",
        "skip to content",
        "print this page",
        "download",
        "listen",
        "related stories",
        "related news",
        "more news",
        "contact us",
        "follow us",
        "subscribe",
        "sign up",
        "image",
        "main image",
        "copyright",
        "privacy",
        "cookies",
        "accessibility",
        "menu",
        "search",
        "home",
    }

    BOILERPLATE_PHRASES = (
        "main article content",
        "skip to main content",
        "accept all cookies",
        "manage cookie preferences",
        "share this article",
        "share this page",
        "back to news",
        "sign up for updates",
        "subscribe to our newsletter",
        "follow us on facebook",
        "follow us on twitter",
        "follow us on x",
        "opens in a new window",
        "external link",
    )

    INVALID_LOCATION_VALUES = {
        "main article content",
        "article content",
        "main content",
        "news",
        "latest news",
        "published",
        "published:",
        "police news",
        "nottinghamshire police",
        "source",
        "main image",
        "image",
        "unknown",
        "none",
        "n/a",
    }

    INVALID_CATEGORY_VALUES = {
        "main article content",
        "article content",
        "main content",
        "news",
        "latest news",
        "published",
        "published:",
        "source",
        "main image",
        "image",
    }

    IMAGE_FILENAME_PATTERN = re.compile(
        r"""
        ^\s*
        [^\n]*?
        \.
        (?:jpg|jpeg|png|gif|webp|svg|bmp|tif|tiff)
        (?:\?.*)?
        \s*$
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    DATE_ONLY_PATTERN = re.compile(
        r"""
        ^\s*
        (?:
            \d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}
            |
            \d{4}[/\-.]\d{1,2}[/\-.]\d{1,2}
            |
            \d{1,2}\s+
            (?:
                jan(?:uary)?|
                feb(?:ruary)?|
                mar(?:ch)?|
                apr(?:il)?|
                may|
                jun(?:e)?|
                jul(?:y)?|
                aug(?:ust)?|
                sep(?:tember)?|
                oct(?:ober)?|
                nov(?:ember)?|
                dec(?:ember)?
            )
            \s+\d{4}
        )
        \s*$
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    TIME_ONLY_PATTERN = re.compile(
        r"""
        ^\s*
        \d{1,2}:\d{2}
        (?::\d{2})?
        \s*
        (?:am|pm)?
        \s*$
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    LABEL_ONLY_PATTERN = re.compile(
        r"""
        ^\s*
        (?:
            published|
            updated|
            author|
            source|
            news|
            image|
            caption|
            location|
            category|
            tags
        )
        \s*:\s*$
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    SOCIAL_ONLY_PATTERN = re.compile(
        r"""
        ^\s*
        (?:
            facebook|
            twitter|
            x|
            instagram|
            linkedin|
            email|
            whatsapp
        )
        \s*$
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    NAVIGATION_ONLY_PATTERN = re.compile(
        r"""
        ^\s*
        (?:
            previous|
            next|
            previous\s+article|
            next\s+article
        )
        \s*$
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    @staticmethod
    def value(
        story: Any,
        *names: str,
        default: Any = "",
    ) -> Any:
        """Return the first populated story attribute or extras value."""

        for name in names:
            result = getattr(story, name, None)

            if result not in (None, "", [], (), {}):
                return result

        extras = getattr(story, "extras", {})

        if isinstance(extras, dict):
            for name in names:
                result = extras.get(name)

                if result not in (None, "", [], (), {}):
                    return result

        return default

    @classmethod
    def clean(cls, text: Any) -> str:
        """Normalise whitespace without rewriting supplied wording."""

        if text is None:
            return ""

        value = unescape(str(text))
        value = value.replace("\u00a0", " ")
        value = value.replace("\r\n", "\n").replace("\r", "\n")
        value = re.sub(r"[ \t]+", " ", value)
        value = re.sub(r" *\n *", "\n", value)
        value = re.sub(r"\n{3,}", "\n\n", value)

        return value.strip()

    @classmethod
    def normalise_comparison(cls, text: Any) -> str:
        """Create a conservative value for duplicate comparisons."""

        value = cls.clean(text).casefold()
        value = re.sub(r"[“”‘’\"']", "", value)
        value = re.sub(r"\s+", " ", value)
        value = re.sub(r"[^\w\s]", "", value)

        return value.strip()

    @classmethod
    def same_text(cls, first: Any, second: Any) -> bool:
        """Return True when two supplied blocks contain the same wording."""

        first_value = cls.normalise_comparison(first)
        second_value = cls.normalise_comparison(second)

        return bool(
            first_value
            and second_value
            and first_value == second_value
        )

    @classmethod
    def substantially_same(cls, first: Any, second: Any) -> bool:
        """Detect conservative near-duplicate paragraphs."""

        first_value = cls.normalise_comparison(first)
        second_value = cls.normalise_comparison(second)

        if not first_value or not second_value:
            return False

        if first_value == second_value:
            return True

        shorter = min(len(first_value), len(second_value))
        longer = max(len(first_value), len(second_value))

        if shorter < 55:
            return False

        if shorter / longer < 0.88:
            return False

        return (
            first_value in second_value
            or second_value in first_value
        )

    @classmethod
    def is_image_filename(cls, text: Any) -> bool:
        value = cls.clean(text)

        return bool(
            value
            and cls.IMAGE_FILENAME_PATTERN.fullmatch(value)
        )

    @classmethod
    def is_boilerplate(cls, text: Any) -> bool:
        """Identify website furniture and scrape artefacts."""

        value = cls.clean(text)

        if not value:
            return True

        comparison = value.casefold().strip(" :–—-|")

        if comparison in cls.BOILERPLATE_LINES:
            return True

        if cls.LABEL_ONLY_PATTERN.fullmatch(value):
            return True

        if cls.is_image_filename(value):
            return True

        if cls.DATE_ONLY_PATTERN.fullmatch(value):
            return True

        if cls.TIME_ONLY_PATTERN.fullmatch(value):
            return True

        if cls.SOCIAL_ONLY_PATTERN.fullmatch(value):
            return True

        if cls.NAVIGATION_ONLY_PATTERN.fullmatch(value):
            return True

        if len(comparison) <= 100:
            for phrase in cls.BOILERPLATE_PHRASES:
                if comparison == phrase:
                    return True

        return False

    @classmethod
    def raw_paragraphs(cls, text: Any) -> list[str]:
        """Split source content into usable paragraph blocks."""

        value = cls.clean(text)

        if not value:
            return []

        blocks = re.split(r"\n\s*\n", value)

        if len(blocks) == 1:
            lines = [
                line.strip()
                for line in value.splitlines()
                if line.strip()
            ]

            if len(lines) > 1:
                blocks = lines

        return [
            re.sub(r"\s+", " ", block).strip()
            for block in blocks
            if block.strip()
        ]

    @classmethod
    def clean_paragraphs(
        cls,
        text: Any,
        *,
        title: str = "",
        summary: str = "",
    ) -> list[str]:
        """Remove scrape artefacts and duplicate paragraphs."""

        cleaned: list[str] = []

        for paragraph in cls.raw_paragraphs(text):
            paragraph = cls.clean(paragraph)

            if not paragraph:
                continue

            if cls.is_boilerplate(paragraph):
                continue

            if title and cls.same_text(paragraph, title):
                continue

            if summary and cls.same_text(paragraph, summary):
                continue

            if any(
                cls.substantially_same(paragraph, existing)
                for existing in cleaned
            ):
                continue

            cleaned.append(paragraph)

        return cleaned

    @classmethod
    def paragraphs(cls, text: Any) -> list[str]:
        """Compatibility method used by rendering formatters."""

        return cls.clean_paragraphs(text)

    @classmethod
    def truncate(cls, text: Any, length: int) -> str:
        value = cls.clean(text)

        if length <= 0:
            return ""

        if len(value) <= length:
            return value

        shortened = value[: max(1, length - 1)].rsplit(" ", 1)[0]

        if not shortened:
            shortened = value[: max(1, length - 1)]

        return shortened.rstrip(" ,;:-") + "…"

    @classmethod
    def truncate_words(
        cls,
        text: Any,
        maximum_words: int,
    ) -> str:
        value = cls.clean(text)
        words = value.split()

        if maximum_words <= 0:
            return ""

        if len(words) <= maximum_words:
            return value

        return (
            " ".join(words[:maximum_words]).rstrip(" ,;:-")
            + "…"
        )

    @classmethod
    def title(cls, story: Any) -> str:
        return (
            cls.clean(
                cls.value(
                    story,
                    "title",
                    "headline",
                )
            )
            or "News update"
        )

    @classmethod
    def summary(cls, story: Any) -> str:
        summary = cls.clean(
            cls.value(
                story,
                "summary",
                "standfirst",
                "intro",
            )
        )

        if cls.is_boilerplate(summary):
            return ""

        return summary

    @classmethod
    def body(cls, story: Any) -> str:
        return cls.clean(
            cls.value(
                story,
                "body",
                "content",
                "article_text",
            )
        )

    @classmethod
    def article_paragraphs(cls, story: Any) -> list[str]:
        return cls.clean_paragraphs(
            cls.body(story),
            title=cls.title(story),
            summary=cls.summary(story),
        )

    @classmethod
    def source(cls, story: Any) -> str:
        source = cls.clean(
            cls.value(
                story,
                "source",
                "source_name",
                default="Devour Lincolnshire NewsDesk",
            )
        )

        if cls.is_boilerplate(source):
            return ""

        return source

    @classmethod
    def location(cls, story: Any) -> str:
        """Return the best valid editorial location."""

        extras = getattr(story, "extras", {}) or {}

        candidates = [
            extras.get("matched_place"),
            getattr(story, "location", ""),
            extras.get("location"),
            extras.get("area"),
        ]

        for candidate in candidates:
            value = cls.clean(candidate)
            comparison = value.casefold().strip(" :–—-|")

            if not value:
                continue

            if comparison in cls.INVALID_LOCATION_VALUES:
                continue

            if cls.is_boilerplate(value):
                continue

            if cls.is_image_filename(value):
                continue

            if len(value) > 100:
                continue

            return value

        return ""

    @classmethod
    def category(cls, story: Any) -> str:
        candidates = [
            getattr(story, "category", ""),
            getattr(story, "classification", ""),
            cls.value(story, "crime_type"),
        ]

        for candidate in candidates:
            value = cls.clean(candidate)
            comparison = value.casefold().strip(" :–—-|")

            if not value:
                continue

            if comparison in cls.INVALID_CATEGORY_VALUES:
                continue

            if cls.is_boilerplate(value):
                continue

            if len(value) > 100:
                continue

            return value

        return ""

    @classmethod
    def first_paragraph(cls, story: Any) -> str:
        paragraphs = cls.article_paragraphs(story)

        return paragraphs[0] if paragraphs else ""

    @staticmethod
    def contains_any(text: str, phrases: Iterable[str]) -> bool:
        lowered = text.casefold()

        return any(
            phrase.casefold() in lowered
            for phrase in phrases
        )

    @classmethod
    def compose_article_sections(
        cls,
        story: Any,
        *,
        include_title: bool = True,
        include_summary: bool = True,
    ) -> list[str]:
        """Build a full cleaned article without repeated introductions."""

        title = cls.title(story)
        summary = cls.summary(story)
        body_paragraphs = cls.article_paragraphs(story)

        sections: list[str] = []

        if include_title and title:
            sections.append(title)

        if include_summary and summary:
            sections.append(summary)

        sections.extend(body_paragraphs)

        return sections