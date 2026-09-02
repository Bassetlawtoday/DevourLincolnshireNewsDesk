"""Shared still-image policy for Sport Intelligence.

Sport consumes photographs, not video assets or video preview artwork.  This
module is deliberately source-neutral so every club and feed follows the same
rules.
"""

from __future__ import annotations

from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag


_REJECTED_URL_TERMS = (
    "youtube.com",
    "youtu.be",
    "vimeo.com",
    "brightcove",
    "dailymotion",
    "video-thumbnail",
    "video_thumbnail",
    "videothumb",
    "video-poster",
    "video_poster",
    "/video/",
    "play-button",
    "play_button",
    "sprite",
    "tracking",
    "pixel",
)

_REJECTED_CONTEXT_TERMS = (
    "video",
    "player",
    "play-button",
    "play_button",
    "youtube",
    "vimeo",
)

_REJECTED_IMAGE_TERMS = (
    "avatar",
    "badge",
    "crest",
    "favicon",
    "icon",
    "logo",
    "placeholder",
    "social-share",
)


def is_still_image_url(url: object) -> bool:
    """Return whether *url* can represent an ordinary still image."""

    value = str(url or "").strip()
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    lowered = value.casefold()
    return not any(term in lowered for term in _REJECTED_URL_TERMS)


def is_video_story(story: object) -> bool:
    """Return whether a story URL is a video item rather than an article."""

    url = str(getattr(story, "url", "") or "").casefold()
    parsed = urlparse(url)
    path = parsed.path
    return any(
        marker in path
        for marker in (
            "/videos/",
            "/video/",
            "/av/",
            "/watch/",
            "/highlights/video",
        )
    )


def page_has_video_metadata(soup: object) -> bool:
    """Detect pages whose primary OpenGraph asset is a video."""

    if not isinstance(soup, BeautifulSoup):
        return False
    og_type = soup.select_one("meta[property='og:type']")
    og_value = str(og_type.get("content") or "") if isinstance(og_type, Tag) else ""
    return bool(
        "video" in og_value.casefold()
        or soup.select_one(
            "meta[property^='og:video'], meta[name^='twitter:player']"
        )
    )


def article_still_image(soup: object, article_url: str) -> str:
    """Return the best visible article photograph, excluding video contexts."""

    if not isinstance(soup, BeautifulSoup):
        return ""
    selectors = (
        "article figure img",
        "article picture img",
        "article img",
        "main figure img",
        "main picture img",
        "main img",
    )
    candidates: list[tuple[int, str]] = []
    seen: set[str] = set()
    for selector_index, selector in enumerate(selectors):
        for image in soup.select(selector):
            if not isinstance(image, Tag):
                continue
            context = " ".join(
                str(value or "")
                for parent in [image, *list(image.parents)[:4]]
                if isinstance(parent, Tag)
                for value in (parent.get("class"), parent.get("id"))
            ).casefold()
            if any(term in context for term in _REJECTED_CONTEXT_TERMS):
                continue
            raw = ""
            for attribute in ("src", "data-src", "data-lazy-src", "data-original"):
                raw = str(image.get(attribute) or "").strip()
                if raw:
                    break
            if not raw:
                srcset = str(image.get("srcset") or "").strip()
                if srcset:
                    raw = srcset.split(",")[-1].strip().split()[0]
            candidate = urljoin(article_url, raw)
            lowered = candidate.casefold()
            if (
                candidate in seen
                or not is_still_image_url(candidate)
                or any(term in lowered for term in _REJECTED_IMAGE_TERMS)
            ):
                continue
            seen.add(candidate)
            try:
                width = int(image.get("width") or 0)
                height = int(image.get("height") or 0)
            except (TypeError, ValueError):
                width = height = 0
            if (width and width < 300) or (height and height < 180):
                continue
            area = width * height
            candidates.append((area + (len(selectors) - selector_index) * 1000, candidate))
    return max(candidates, default=(0, ""), key=lambda item: item[0])[1]


def choose_article_still(html_article: dict, article_url: str) -> str:
    """Choose a real still from extracted article data."""

    soup = html_article.get("soup")
    visible = article_still_image(soup, article_url)
    if visible:
        return visible
    candidate = str(html_article.get("image") or "").strip()
    if page_has_video_metadata(soup):
        return ""
    return candidate if is_still_image_url(candidate) else ""


__all__ = [
    "article_still_image",
    "choose_article_still",
    "is_still_image_url",
    "is_video_story",
    "page_has_video_metadata",
]
