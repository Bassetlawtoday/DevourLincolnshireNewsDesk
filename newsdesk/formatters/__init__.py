"""Compatibility import for the NewsDesk publishing engine.

Existing code may continue using:

    from newsdesk.formatters import Formatters
"""

from newsdesk.publishing import (
    ArticleBuilder,
    BreakingNewsFormatter,
    BuiltArticle,
    FacebookFormatter,
    Formatters,
    HtmlFormatter,
    MarkdownFormatter,
    MetadataFormatter,
    NewsletterFormatter,
    PlainTextFormatter,
    WebsiteFormatter,
)


__all__ = [
    "Formatters",
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
]