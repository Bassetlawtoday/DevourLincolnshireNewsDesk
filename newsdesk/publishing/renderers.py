"""HTML, Markdown and plain-text publication renderers."""

from __future__ import annotations

from html import escape
from typing import Any

from .builder import ArticleBuilder
from .website import WebsiteFormatter


class HtmlFormatter:
    """Generate complete semantic HTML."""

    def __init__(
        self,
        builder: ArticleBuilder | None = None,
    ) -> None:
        self.builder = builder or ArticleBuilder()

    def format(self, story: Any) -> str:
        article = self.builder.build(story)

        summary_html = (
            f"<p><strong>{escape(article.summary)}</strong></p>"
            if article.summary
            else ""
        )

        body_html = "\n".join(
            f"<p>{escape(paragraph)}</p>"
            for paragraph in article.paragraphs
        )

        if not article.has_content:
            body_html = (
                "<p>Further information was not available "
                "in the supplied source material.</p>"
            )

        footer = article.footer_lines()

        footer_html = (
            f"<p><small>{escape(' | '.join(footer))}</small></p>"
            if footer
            else ""
        )

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{escape(article.title)}</title>
</head>
<body>
<article>
<h1>{escape(article.title)}</h1>
{summary_html}
{body_html}
{footer_html}
</article>
</body>
</html>
"""


class MarkdownFormatter:
    """Generate complete Markdown output."""

    def __init__(
        self,
        builder: ArticleBuilder | None = None,
    ) -> None:
        self.builder = builder or ArticleBuilder()

    def format(self, story: Any) -> str:
        article = self.builder.build(story)

        sections = [
            f"# {article.title}"
        ]

        if article.summary:
            sections.append(
                f"**{article.summary}**"
            )

        sections.extend(article.paragraphs)

        if not article.has_content:
            sections.append(
                "Further information was not available "
                "in the supplied source material."
            )

        footer = article.footer_lines()

        if footer:
            sections.append(
                "*" + " | ".join(footer) + "*"
            )

        return "\n\n".join(
            section
            for section in sections
            if section.strip()
        )


class PlainTextFormatter:
    """Generate complete plain-text output."""

    def __init__(
        self,
        builder: ArticleBuilder | None = None,
    ) -> None:
        self.website_formatter = WebsiteFormatter(
            builder=builder,
        )

    def format(self, story: Any) -> str:
        return self.website_formatter.format(story)