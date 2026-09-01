"""Temporary Devour Lincolnshire NewsDesk formatter.

This compact version preserves the formatter interfaces required by
StoryEngine so NewsDesk and its modules can run for demonstration purposes.
"""

from __future__ import annotations

from html import escape
import re
from typing import Any


try:
    from .constants import (
        FACEBOOK_MAX_EMOJIS,
        SEO_TITLE_LENGTH,
        META_DESCRIPTION_LENGTH,
    )
except ImportError:
    FACEBOOK_MAX_EMOJIS = 8
    SEO_TITLE_LENGTH = 60
    META_DESCRIPTION_LENGTH = 160


class BaseFormatter:
    """Common formatter utilities."""

    BOILERPLATE = {
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
        "back to news",
        "related stories",
        "main image",
        "image",
    }

    IMAGE_PATTERN = re.compile(
        r".*\.(?:jpg|jpeg|png|gif|webp|svg|bmp|tif|tiff)(?:\?.*)?$",
        re.IGNORECASE,
    )

    @staticmethod
    def value(
        story: Any,
        *names: str,
        default: Any = "",
    ) -> Any:
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

    @staticmethod
    def clean(text: Any) -> str:
        if text is None:
            return ""

        value = str(text)
        value = value.replace("\r\n", "\n").replace("\r", "\n")
        value = re.sub(r"[ \t]+", " ", value)
        value = re.sub(r" *\n *", "\n", value)
        value = re.sub(r"\n{3,}", "\n\n", value)

        return value.strip()

    @classmethod
    def is_boilerplate(cls, text: Any) -> bool:
        value = cls.clean(text)

        if not value:
            return True

        comparison = value.casefold().strip(" :–—-|")

        if comparison in cls.BOILERPLATE:
            return True

        if cls.IMAGE_PATTERN.fullmatch(value):
            return True

        return False

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
        value = cls.clean(
            cls.value(
                story,
                "summary",
                "standfirst",
                "intro",
            )
        )

        if cls.is_boilerplate(value):
            return ""

        return value

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
    def source(cls, story: Any) -> str:
        value = cls.clean(
            cls.value(
                story,
                "source",
                "source_name",
            )
        )

        if cls.is_boilerplate(value):
            return ""

        return value

    @classmethod
    def location(cls, story: Any) -> str:
        extras = getattr(story, "extras", {}) or {}

        candidates = [
            extras.get("matched_place"),
            getattr(story, "location", ""),
            extras.get("location"),
            extras.get("area"),
        ]

        for candidate in candidates:
            value = cls.clean(candidate)

            if not value:
                continue

            if cls.is_boilerplate(value):
                continue

            if len(value) <= 100:
                return value

        return ""

    @classmethod
    def paragraphs(cls, text: Any) -> list[str]:
        value = cls.clean(text)

        if not value:
            return []

        blocks = re.split(r"\n\s*\n", value)

        if len(blocks) == 1 and "\n" in value:
            blocks = value.splitlines()

        output: list[str] = []
        seen: set[str] = set()

        for block in blocks:
            paragraph = re.sub(r"\s+", " ", block).strip()

            if cls.is_boilerplate(paragraph):
                continue

            comparison = re.sub(
                r"[^\w\s]",
                "",
                paragraph.casefold(),
            )

            if comparison in seen:
                continue

            seen.add(comparison)
            output.append(paragraph)

        return output

    @classmethod
    def article_paragraphs(cls, story: Any) -> list[str]:
        title = cls.title(story)
        summary = cls.summary(story)

        output = []

        for paragraph in cls.paragraphs(cls.body(story)):
            if paragraph.casefold() == title.casefold():
                continue

            if summary and paragraph.casefold() == summary.casefold():
                continue

            output.append(paragraph)

        return output

    @classmethod
    def truncate(cls, text: Any, maximum: int) -> str:
        value = cls.clean(text)

        if len(value) <= maximum:
            return value

        shortened = value[: maximum - 1].rsplit(" ", 1)[0]

        return shortened.rstrip(" ,;:-") + "…"

    @classmethod
    def complete_article(cls, story: Any) -> str:
        sections = [cls.title(story)]

        summary = cls.summary(story)

        if summary:
            sections.append(summary)

        sections.extend(cls.article_paragraphs(story))

        if len(sections) == 1:
            sections.append(
                "Further information was not available in the supplied source."
            )

        footer = []

        if cls.location(story):
            footer.append(f"Area: {cls.location(story)}")

        if cls.source(story):
            footer.append(f"Source: {cls.source(story)}")

        if footer:
            sections.append("\n".join(footer))

        return "\n\n".join(sections)


class WebsiteFormatter(BaseFormatter):
    def format(self, story: Any) -> str:
        return self.complete_article(story)


class NewsletterFormatter(BaseFormatter):
    def format(self, story: Any) -> str:
        return self.complete_article(story)


class FacebookFormatter(BaseFormatter):
    def format(
        self,
        story: Any,
        emoji_limit: int = FACEBOOK_MAX_EMOJIS,
    ) -> str:
        sections = [f"🚨 {self.title(story)}"]

        summary = self.summary(story)

        if summary:
            sections.append(summary)

        paragraphs = self.article_paragraphs(story)

        emojis = ["📍", "🔎", "🚔", "⚖️", "📢", "ℹ️", "📰"]
        emoji_limit = max(0, min(int(emoji_limit or 0), 8))

        for index, paragraph in enumerate(paragraphs):
            prefix = ""

            if index % 2 == 1 and emoji_limit > 1:
                emoji = emojis[
                    min(index, len(emojis) - 1)
                ]
                prefix = f"{emoji} "

            sections.append(prefix + paragraph)

        footer = []

        if self.location(story):
            footer.append(f"📍 {self.location(story)}")

        if self.source(story):
            footer.append(f"Source: {self.source(story)}")

        if footer:
            sections.append("\n".join(footer))

        return "\n\n".join(sections)


class BreakingNewsFormatter(BaseFormatter):
    def format(self, story: Any) -> str:
        summary = self.summary(story)

        if not summary:
            paragraphs = self.article_paragraphs(story)
            summary = paragraphs[0] if paragraphs else ""

        return (
            "🚨 BREAKING NEWS\n\n"
            f"{self.title(story)}\n\n"
            f"{self.truncate(summary, 300)}"
        ).strip()


class MetadataFormatter(BaseFormatter):
    def seo_title(self, title: str) -> str:
        return self.truncate(title, SEO_TITLE_LENGTH)

    def meta_description(self, text: str) -> str:
        return self.truncate(text, META_DESCRIPTION_LENGTH)

    def slug(self, title: str) -> str:
        value = self.clean(title).lower()
        value = re.sub(r"[^a-z0-9]+", "-", value)

        return value.strip("-")

    def tags(self, text: str) -> list[str]:
        words = re.findall(
            r"[A-Za-z][A-Za-z'-]{3,}",
            self.clean(text).lower(),
        )

        output = []

        for word in words:
            word = word.strip("-'")

            if word and word not in output:
                output.append(word)

            if len(output) == 10:
                break

        return output

    def keywords(self, text: str) -> list[str]:
        return self.tags(text)

    def image_caption(self, story: Any) -> str:
        caption = self.title(story)

        if self.location(story):
            caption += f" — {self.location(story)}"

        if self.source(story):
            caption += f". Source: {self.source(story)}"

        return caption


class HtmlFormatter(BaseFormatter):
    def format(self, story: Any) -> str:
        title = self.title(story)
        summary = self.summary(story)

        paragraphs = "\n".join(
            f"<p>{escape(paragraph)}</p>"
            for paragraph in self.article_paragraphs(story)
        )

        summary_html = (
            f"<p><strong>{escape(summary)}</strong></p>"
            if summary
            else ""
        )

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{escape(title)}</title>
</head>
<body>
<article>
<h1>{escape(title)}</h1>
{summary_html}
{paragraphs}
</article>
</body>
</html>"""


class MarkdownFormatter(BaseFormatter):
    def format(self, story: Any) -> str:
        sections = [f"# {self.title(story)}"]

        summary = self.summary(story)

        if summary:
            sections.append(f"**{summary}**")

        sections.extend(self.article_paragraphs(story))

        return "\n\n".join(sections)


class PlainTextFormatter(BaseFormatter):
    def format(self, story: Any) -> str:
        return self.complete_article(story)


class Formatters:
    """Formatter instances required by StoryEngine."""

    website = WebsiteFormatter()
    newsletter = NewsletterFormatter()
    facebook = FacebookFormatter()

    breaking = BreakingNewsFormatter()
    breaking_news = breaking

    metadata = MetadataFormatter()

    html = HtmlFormatter()
    markdown = MarkdownFormatter()

    text = PlainTextFormatter()
    plain_text = text