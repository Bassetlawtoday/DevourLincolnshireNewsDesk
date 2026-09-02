"""
Shared RSS scraper base class for SportDesk.

Concrete scrapers only need to define:
    FEED_URL
    SOURCE_NAME
    CATEGORY
"""

from __future__ import annotations

from email.utils import parsedate_to_datetime
import html
import re
from typing import Any
from urllib.parse import urljoin

import feedparser
import requests
from bs4 import BeautifulSoup

from newsdesk.story import Story
from newsdesk.sports.media_policy import is_still_image_url


class BaseRssScraper:
    """Collect and normalise stories from one SportDesk RSS feed."""

    FEED_URL: str = ""
    SOURCE_NAME: str = ""
    CATEGORY: str = "Sport"

    DEFAULT_TIMEOUT = 30.0
    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/150.0 Safari/537.36 "
            "DevourLincolnshire-NewsDesk/1.0"
        ),
        "Accept": (
            "application/rss+xml,application/xml,text/xml,"
            "text/html;q=0.9,*/*;q=0.8"
        ),
        "Accept-Language": "en-GB,en;q=0.9",
        "Cache-Control": "no-cache",
    }

    _IMAGE_EXTENSIONS = (
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".gif",
        ".bmp",
    )

    def __init__(
        self,
        *,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._stories: list[Story] = []
        self.timeout = float(timeout)
        self._session = requests.Session()
        self._session.headers.update(self.DEFAULT_HEADERS)

    @property
    def source_name(self) -> str:
        return self.SOURCE_NAME

    def clear(self) -> None:
        self._stories.clear()

    def close(self) -> None:
        self._session.close()

    def get_stories(
        self,
        *,
        refresh: bool = True,
        deduplicate: bool = True,
    ) -> list[Story]:
        if not refresh and self._stories:
            return list(self._stories)

        feed = self._fetch_feed()
        stories: list[Story] = []

        for entry in getattr(feed, "entries", []) or []:
            title = self._plain_text(
                getattr(entry, "title", "")
            )
            summary = self._summary(entry)
            article_url = str(
                getattr(entry, "link", "") or ""
            ).strip()
            image_url = self._image_url(
                entry,
                article_url,
            )

            story = Story(
                title=title,
                summary=summary,
                body=summary,
                source=self.SOURCE_NAME,
                url=article_url,
                category=self.CATEGORY,
                published=self._published(entry),
                author=self._author(entry),
                image_url=image_url,
                image_caption=self._image_caption(entry),
                image_credit=self._image_credit(entry),
                image_alt_text=title,
                tags=self._tags(entry),
            )

            story.extras.update(
                {
                    "rss_feed_url": self.FEED_URL,
                    "rss_image_found": bool(image_url),
                    "rss_image_url": image_url,
                    "rss_source_name": self.SOURCE_NAME,
                    "rss_entry_id": str(
                        getattr(entry, "id", "") or ""
                    ).strip(),
                }
            )

            if story.title or story.url:
                stories.append(story)

        if deduplicate:
            stories = self._deduplicate(stories)

        self._stories = stories
        return list(stories)

    def _fetch_feed(self):
        """
        Fetch the RSS document explicitly with requests.

        This avoids feedparser's platform-dependent urllib behaviour and gives
        BBC feeds the same browser-style headers used elsewhere in NewsDesk.
        """

        if not self.FEED_URL.strip():
            raise ValueError(
                f"{type(self).__name__} does not define FEED_URL."
            )

        response = self._session.get(
            self.FEED_URL,
            timeout=self.timeout,
            allow_redirects=True,
        )
        response.raise_for_status()

        payload = response.content
        if not payload:
            raise OSError(
                f"{self.SOURCE_NAME or type(self).__name__} "
                "returned an empty RSS response."
            )

        parsed = feedparser.parse(payload)

        entries = getattr(parsed, "entries", []) or []
        bozo = bool(getattr(parsed, "bozo", False))
        bozo_exception = getattr(
            parsed,
            "bozo_exception",
            None,
        )

        # Some feeds remain usable despite a minor XML warning. Only treat a
        # parser warning as fatal when no entries were recovered.
        if bozo and not entries:
            raise OSError(
                f"Could not parse {self.SOURCE_NAME or self.FEED_URL}: "
                f"{bozo_exception or 'invalid RSS document'}"
            )

        return parsed

    def _image_url(
        self,
        entry: Any,
        article_url: str,
    ) -> str:
        """Return the strongest image URL supplied by an RSS entry."""

        candidates: list[tuple[int, str]] = []

        for attribute in (
            "media_content",
            "media_thumbnail",
        ):
            values = getattr(entry, attribute, None) or []
            if isinstance(values, dict):
                values = [values]

            for item in values:
                if not isinstance(item, dict):
                    continue

                url = str(
                    item.get("url")
                    or item.get("href")
                    or ""
                ).strip()
                if not url:
                    continue

                medium = str(
                    item.get("medium", "") or ""
                ).casefold()
                content_type = str(
                    item.get("type", "") or ""
                ).casefold()
                width = self._integer_value(
                    item.get("width")
                )
                height = self._integer_value(
                    item.get("height")
                )

                if (
                    not medium
                    or medium == "image"
                    or content_type.startswith("image/")
                    or self._looks_like_image(url)
                ):
                    candidates.append(
                        (
                            self._image_score(
                                url,
                                width=width,
                                height=height,
                            ),
                            url,
                        )
                    )

        enclosures = getattr(
            entry,
            "enclosures",
            None,
        ) or []
        if isinstance(enclosures, dict):
            enclosures = [enclosures]

        for enclosure in enclosures:
            if not isinstance(enclosure, dict):
                continue

            url = str(
                enclosure.get("href")
                or enclosure.get("url")
                or ""
            ).strip()
            content_type = str(
                enclosure.get("type", "") or ""
            ).casefold()

            if url and (
                content_type.startswith("image/")
                or self._looks_like_image(url)
            ):
                candidates.append(
                    (self._image_score(url), url)
                )

        entry_image = getattr(entry, "image", None)
        if isinstance(entry_image, dict):
            image_value = str(
                entry_image.get("href")
                or entry_image.get("url")
                or ""
            ).strip()
            if image_value:
                candidates.append(
                    (
                        self._image_score(image_value),
                        image_value,
                    )
                )

        for attribute in (
            "summary",
            "description",
            "content",
        ):
            value = getattr(entry, attribute, None)

            if isinstance(value, list):
                markup_values = [
                    str(item.get("value", "") or "")
                    for item in value
                    if isinstance(item, dict)
                ]
            else:
                markup_values = [str(value or "")]

            for markup in markup_values:
                if not markup:
                    continue

                soup = BeautifulSoup(
                    markup,
                    "html.parser",
                )

                for image in soup.find_all("img"):
                    candidates.extend(
                        self._image_node_candidates(image)
                    )

        best = self._best_image_candidate(
            candidates,
            article_url or self.FEED_URL,
        )
        if best:
            return best

        return self._article_page_image(article_url)

    def _article_page_image(self, article_url: str) -> str:
        """Return the strongest page-level lead image."""

        url = str(article_url or "").strip()
        if not self._is_http_url(url):
            return ""

        try:
            response = self._session.get(
                url,
                timeout=min(self.timeout, 15.0),
                allow_redirects=True,
            )
            response.raise_for_status()
        except requests.RequestException:
            return ""

        soup = BeautifulSoup(response.content, "html.parser")
        candidates: list[tuple[int, str]] = []

        metadata_rules = (
            ("meta[property='og:image:secure_url']", "content"),
            ("meta[property='og:image']", "content"),
            ("meta[name='twitter:image']", "content"),
            ("meta[property='twitter:image']", "content"),
            ("meta[name='twitter:image:src']", "content"),
            ("link[rel='image_src']", "href"),
        )

        for selector, attribute in metadata_rules:
            for node in soup.select(selector):
                value = node.get(attribute)
                if not isinstance(value, str) or not value.strip():
                    continue

                width = 0
                height = 0

                if selector.startswith("meta[property='og:image"):
                    width_node = soup.select_one(
                        "meta[property='og:image:width']"
                    )
                    height_node = soup.select_one(
                        "meta[property='og:image:height']"
                    )
                    if width_node is not None:
                        width = self._integer_value(
                            width_node.get("content")
                        )
                    if height_node is not None:
                        height = self._integer_value(
                            height_node.get("content")
                        )

                candidates.append(
                    (
                        self._image_score(
                            value,
                            width=width,
                            height=height,
                            metadata=True,
                        ),
                        value.strip(),
                    )
                )

        selectors = (
            "article img.wp-post-image",
            "article img.featured-image",
            "article .featured-image img",
            "article figure img",
            "article picture img",
            "article img",
            "main img.wp-post-image",
            "main img.featured-image",
            "main .featured-image img",
            "main figure img",
            "main picture img",
            "main img",
            "img.wp-post-image",
            "img.featured-image",
            ".featured-image img",
        )

        seen_nodes: set[int] = set()
        for selector in selectors:
            for image in soup.select(selector):
                node_id = id(image)
                if node_id in seen_nodes:
                    continue
                seen_nodes.add(node_id)
                candidates.extend(
                    self._image_node_candidates(image)
                )

        if not candidates:
            for image in soup.find_all("img"):
                candidates.extend(
                    self._image_node_candidates(image)
                )

        return self._best_image_candidate(
            candidates,
            response.url,
        )

    def _image_node_candidates(
        self,
        image: Any,
    ) -> list[tuple[int, str]]:
        """Return all useful image candidates exposed by one HTML img node."""

        candidates: list[tuple[int, str]] = []
        width = self._integer_value(image.get("width"))
        height = self._integer_value(image.get("height"))

        for attribute in (
            "srcset",
            "data-srcset",
            "data-lazy-srcset",
        ):
            value = image.get(attribute)
            if not isinstance(value, str):
                continue

            for source, source_width in self._srcset_candidates(value):
                candidates.append(
                    (
                        self._image_score(
                            source,
                            width=source_width or width,
                            height=height,
                        ),
                        source,
                    )
                )

        for attribute in (
            "src",
            "data-src",
            "data-lazy-src",
            "data-original",
            "data-lazyload",
            "data-image",
        ):
            source = image.get(attribute)
            if not isinstance(source, str) or not source.strip():
                continue

            candidates.append(
                (
                    self._image_score(
                        source,
                        width=width,
                        height=height,
                    ),
                    source.strip(),
                )
            )

        return candidates

    @staticmethod
    def _srcset_candidates(
        srcset: str,
    ) -> list[tuple[str, int]]:
        """Parse a srcset string into URL and declared-width pairs."""

        candidates: list[tuple[str, int]] = []

        for item in str(srcset or "").split(","):
            part = item.strip()
            if not part:
                continue

            pieces = part.rsplit(None, 1)
            source = pieces[0].strip()
            width = 0

            if len(pieces) == 2:
                descriptor = pieces[1].strip().casefold()
                if descriptor.endswith("w"):
                    match = re.search(r"\d+", descriptor)
                    width = int(match.group(0)) if match else 0
                elif descriptor.endswith("x"):
                    match = re.search(r"[\d.]+", descriptor)
                    if match:
                        width = int(float(match.group(0)) * 1000)

            if source:
                candidates.append((source, width))

        return candidates

    def _best_image_candidate(
        self,
        candidates: list[tuple[int, str]],
        base_url: str,
    ) -> str:
        """Normalise, rank and return the best usable image candidate."""

        ranked: list[tuple[int, str]] = []
        seen: set[str] = set()

        for score, raw_candidate in candidates:
            candidate = self._normalise_image_url(
                raw_candidate,
                base_url,
            )
            if not candidate or not is_still_image_url(candidate):
                continue

            key = candidate.casefold()
            if key in seen:
                continue

            seen.add(key)
            ranked.append(
                (
                    max(score, self._image_score(candidate)),
                    candidate,
                )
            )

        ranked.sort(
            key=lambda item: item[0],
            reverse=True,
        )

        return ranked[0][1] if ranked else ""

    def _normalise_image_url(
        self,
        candidate: str,
        base_url: str,
    ) -> str:
        """Resolve an image URL and upgrade known small BBC thumbnails."""

        value = html.unescape(
            str(candidate or "").strip()
        )
        if not value:
            return ""

        lowered = value.casefold()
        if lowered.startswith(
            ("data:", "blob:", "javascript:")
        ):
            return ""

        absolute = urljoin(base_url, value)
        if not self._is_http_url(absolute):
            return ""

        return self._upgrade_bbc_image_url(absolute)

    @staticmethod
    def _upgrade_bbc_image_url(url: str) -> str:
        """Request a larger rendition when a BBC thumbnail URL is recognised."""

        value = str(url or "")
        lowered = value.casefold()

        if "ichef.bbci.co.uk" not in lowered:
            return value

        value = re.sub(
            r"/(standard|news|ace)/(?:\d{2,4})(?=/)",
            lambda match: f"/{match.group(1)}/976",
            value,
            flags=re.IGNORECASE,
        )
        value = re.sub(
            r"/(?:\d{2,4})x(?:\d{2,4})(?=/)",
            "/976x549",
            value,
            flags=re.IGNORECASE,
        )

        return value

    def _image_score(
        self,
        url: str,
        *,
        width: int = 0,
        height: int = 0,
        metadata: bool = False,
    ) -> int:
        """Return a ranking score favouring large editorial photographs."""

        value = str(url or "")
        lowered = value.casefold()

        inferred_width, inferred_height = self._dimensions_from_url(value)
        width = max(width, inferred_width)
        height = max(height, inferred_height)

        if width and height:
            score = width * height
        elif width:
            score = width * width
        else:
            score = 1

        if metadata:
            score += 2_000_000

        if any(
            token in lowered
            for token in (
                "logo",
                "icon",
                "avatar",
                "emoji",
                "sprite",
                "badge",
                "crest",
                "favicon",
                "tracking",
                "pixel",
            )
        ):
            score -= 5_000_000

        return score

    @staticmethod
    def _dimensions_from_url(url: str) -> tuple[int, int]:
        """Infer common width/height patterns embedded in an image URL."""

        value = str(url or "")

        patterns = (
            r"(?<!\d)(\d{2,4})[xX](\d{2,4})(?!\d)",
            r"[?&](?:width|w)=(\d{2,4}).*?[?&](?:height|h)=(\d{2,4})",
            r"/(?:standard|news|ace)/(\d{2,4})(?=/)",
        )

        for index, pattern in enumerate(patterns):
            match = re.search(pattern, value, flags=re.IGNORECASE)
            if not match:
                continue

            if index == 2:
                width = int(match.group(1))
                return width, int(width * 9 / 16)

            return int(match.group(1)), int(match.group(2))

        return 0, 0

    @staticmethod
    def _summary(entry: Any) -> str:
        value = (
            getattr(entry, "summary", "")
            or getattr(entry, "description", "")
            or ""
        )
        return BaseRssScraper._plain_text(value)

    @staticmethod
    def _plain_text(value: Any) -> str:
        text = str(value or "")
        if not text:
            return ""

        soup = BeautifulSoup(text, "html.parser")
        cleaned = soup.get_text(" ", strip=True)
        cleaned = html.unescape(cleaned)
        return re.sub(r"\s+", " ", cleaned).strip()

    @staticmethod
    def _author(entry: Any) -> str:
        return str(
            getattr(entry, "author", "")
            or getattr(entry, "dc_creator", "")
            or ""
        ).strip()

    @staticmethod
    def _tags(entry: Any) -> list[str]:
        values: list[str] = []

        for item in getattr(entry, "tags", None) or []:
            if isinstance(item, dict):
                term = str(
                    item.get("term", "") or ""
                ).strip()
            else:
                term = str(
                    getattr(item, "term", "") or ""
                ).strip()

            if term and term not in values:
                values.append(term)

        return values

    @staticmethod
    def _image_caption(entry: Any) -> str:
        for attribute in (
            "media_content",
            "media_thumbnail",
        ):
            values = getattr(entry, attribute, None) or []
            if isinstance(values, dict):
                values = [values]

            for item in values:
                if not isinstance(item, dict):
                    continue

                caption = str(
                    item.get("title")
                    or item.get("description")
                    or ""
                ).strip()
                if caption:
                    return caption

        return ""

    @staticmethod
    def _image_credit(entry: Any) -> str:
        values = getattr(
            entry,
            "media_credit",
            None,
        ) or []

        if isinstance(values, dict):
            values = [values]

        for item in values:
            if isinstance(item, dict):
                credit = str(
                    item.get("content")
                    or item.get("value")
                    or ""
                ).strip()
            else:
                credit = str(item or "").strip()

            if credit:
                return credit

        return ""

    @classmethod
    def _looks_like_image(cls, url: str) -> bool:
        value = str(url or "").casefold().split(
            "?",
            1,
        )[0]
        return value.endswith(cls._IMAGE_EXTENSIONS)

    @staticmethod
    def _is_http_url(url: str) -> bool:
        value = str(url or "").strip().casefold()
        return (
            value.startswith("http://")
            or value.startswith("https://")
        )

    @staticmethod
    def _integer_value(value: Any) -> int:
        match = re.search(r"\d+", str(value or ""))
        return int(match.group(0)) if match else 0

    @staticmethod
    def _published(entry: Any) -> str:
        value = (
            getattr(entry, "published", "")
            or getattr(entry, "updated", "")
        )
        if not value:
            return ""

        try:
            return parsedate_to_datetime(
                value
            ).isoformat()
        except Exception:
            return str(value)

    @staticmethod
    def _deduplicate(
        stories: list[Story],
    ) -> list[Story]:
        seen: set[str] = set()
        unique: list[Story] = []

        for story in stories:
            key = (
                story.url.casefold().rstrip("/")
                or story.title.casefold()
            )

            if not key or key in seen:
                continue

            seen.add(key)
            unique.append(story)

        return unique


__all__ = ["BaseRssScraper"]
