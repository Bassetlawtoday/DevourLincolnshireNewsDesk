"""Plain-text preparation for Social Desk drafts."""

from __future__ import annotations

from html import unescape
from html.parser import HTMLParser
import re


_BLOCK_TAGS = {
    "address", "article", "aside", "blockquote", "br", "div", "dl", "dt",
    "dd", "figcaption", "figure", "footer", "h1", "h2", "h3", "h4", "h5",
    "h6", "header", "hr", "li", "main", "nav", "ol", "p", "pre", "section",
    "table", "tr", "ul",
}

_BARE_WEB_URL = re.compile(
    r"(?<![\w@/:])www\.[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?:/[^\s<]*)?",
    flags=re.IGNORECASE,
)


def _normalise_embedded_urls(text: str) -> str:
    """Make bare web addresses usable by Metricool and social networks."""

    return _BARE_WEB_URL.sub(lambda match: f"https://{match.group(0)}", text)


class _SocialTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.casefold() in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def clean_social_text(value: object, *, source_url: str = "") -> str:
    """Return readable post copy, excluding the separately stored source URL."""

    raw = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    parser = _SocialTextParser()
    try:
        parser.feed(raw)
        parser.close()
        text = "".join(parser.parts)
    except Exception:
        text = re.sub(r"<[^>]+>", " ", raw)
    text = unescape(text)
    # Editorial instructions and contact/link blocks are not publication copy.
    text = re.split(r"(?im)^\s*\[?\s*notes?\s+to\s+editors?\s*:", text, maxsplit=1)[0]
    if source_url:
        text = text.replace(str(source_url).strip(), "")
    # Preserve useful embedded links (surveys, sign-up forms and supporting
    # pages).  Only the separately stored source URL is removed above.
    text = _normalise_embedded_urls(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip(" \n-")


def repair_ldrs_draft(draft):
    """Upgrade an existing LDRS draft created by the older attachment parser."""

    internal = str(getattr(draft, "internal_source_url", "") or "").strip()
    public = str(getattr(draft, "source_url", "") or "").strip()
    if public.casefold().startswith("https://ldrs.org.uk/article/"):
        draft.internal_source_url = public
        draft.source_url = ""
    elif internal:
        draft.source_url = ""
    draft.include_source_url = False

    lines = [line.strip() for line in str(getattr(draft, "text", "") or "").splitlines() if line.strip()]
    if len(lines) >= 2 and lines[0].casefold() == lines[1].casefold():
        attachment_caption = lines[0]
        draft.text = "\n\n".join(lines[2:]).strip()
        if attachment_caption:
            draft.image_caption = attachment_caption
        credit = re.search(
            r"\b(?:Credit:|Photo(?:graph)?(?:\s+credit)?:?)\s*(.+)$",
            attachment_caption,
            flags=re.IGNORECASE,
        )
        if credit:
            draft.image_credit = credit.group(1).strip()
    draft.text = clean_social_text(
        draft.text,
        source_url=str(getattr(draft, "internal_source_url", "") or ""),
    )
    return draft


def compose_metricool_text(
    post_text: object,
    *,
    source_url: str = "",
    image_caption: str = "",
    image_credit: str = "",
) -> str:
    """Build the outgoing Metricool copy while keeping the editor uncluttered."""

    parts = [clean_social_text(post_text, source_url=source_url)]
    if image_caption and image_caption not in parts[0]:
        parts.append(image_caption.strip())
    if image_credit and image_credit not in "\n".join(parts):
        parts.append(f"Image credit: {image_credit.strip()}")
    if source_url:
        parts.append(source_url.strip())
    return "\n\n".join(part for part in parts if part)


__all__ = ["clean_social_text", "compose_metricool_text", "repair_ldrs_draft"]
