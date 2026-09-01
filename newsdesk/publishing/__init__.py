"""Devour Lincolnshire NewsDesk publishing engine."""

from __future__ import annotations

from .builder import ArticleBuilder, BuiltArticle
from .website import WebsiteFormatter
from .newsletter import NewsletterFormatter
from .facebook import FacebookFormatter
from .breaking import BreakingNewsFormatter
from .metadata import MetadataFormatter
from .renderers import (
    HtmlFormatter,
    MarkdownFormatter,
    PlainTextFormatter,
)


_shared_builder = ArticleBuilder()


class Formatters:
    """Shared formatter instances used by StoryEngine."""

    website = WebsiteFormatter(
        builder=_shared_builder,
    )

    newsletter = NewsletterFormatter(
        builder=_shared_builder,
    )

    facebook = FacebookFormatter(
        builder=_shared_builder,
    )

    breaking = BreakingNewsFormatter(
        builder=_shared_builder,
    )
    breaking_news = breaking

    metadata = MetadataFormatter(
        builder=_shared_builder,
    )

    html = HtmlFormatter(
        builder=_shared_builder,
    )

    markdown = MarkdownFormatter(
        builder=_shared_builder,
    )

    text = PlainTextFormatter(
        builder=_shared_builder,
    )
    plain_text = text


__all__ = [
    "ArticleBuilder",
    "BuiltArticle",
    "WebsiteFormatter",
    "NewsletterFormatter",
    "FacebookFormatter",
    "BreakingNewsFormatter",
    "MetadataFormatter",
    "HtmlFormatter",
    "MarkdownFormatter",
    "PlainTextFormatter",
    "Formatters",
]