"""
newsdesk.sources.article_scraper

Generic HTML article scraper used by concrete source scrapers.
"""

from __future__ import annotations
from email.mime import text
from .content_selector import ContentSelector
from dataclasses import dataclass
import json
import logging
import re
from typing import Any, Iterable, Mapping, Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag

from newsdesk.sources import content_selector


LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class ArticleLink:
    """A discovered article title and its absolute URL."""

    title: str
    url: str


class ArticleScraper:
    """
    Generic helper for HTML-based sources.

    Concrete scrapers should subclass ``BaseScraper`` as normal and compose
    an ``ArticleScraper`` instance to avoid duplicating HTTP and HTML parsing
    logic.
    """

    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/150.0 Safari/537.36 "
            "BassetlawToday-NewsDesk/1.0"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,"
            "application/xml;q=0.9,*/*;q=0.8"
        ),
        "Accept-Language": "en-GB,en;q=0.9",
    }

    _REMOVAL_SELECTORS = (
        "script",
        "style",
        "noscript",
        "iframe",
        "form",
        "nav",
        "footer",
        "aside",
        "[role='navigation']",
        "[role='complementary']",
        "[aria-hidden='true']",
        ".advert",
        ".advertisement",
        ".ad",
        ".ads",
        ".ad-slot",
        ".ad-container",
        ".commercial",
        ".cookie",
        ".cookie-banner",
        ".consent",
        ".newsletter",
        ".newsletter-signup",
        ".subscribe",
        ".subscription",
        ".social",
        ".social-share",
        ".share",
        ".sharing",
        ".related",
        ".related-content",
        ".recommended",
        ".recommendations",
        ".most-read",
        ".read-more",
        ".promo",
        ".promotion",
        ".comments",
        ".comment-section",
        ".author-bio",
        ".article-footer",
        ".story-footer",
        ".sharedaddy",
        ".sd-sharing-enabled",
        ".sd-social",
        ".jp-relatedposts",
        ".post-navigation",
        ".navigation",
        ".nav-links",
        ".entry-meta",
        ".post-meta",
        ".article-meta",
        ".tags-links",
        ".cat-links",
        ".like-button",
        ".likes-widget",
        ".reaction",
        ".reactions",
        ".share-buttons",
        ".share-links",
        ".social-links",
        ".social-buttons",
        ".twitter-share-button",
        ".facebook-share-button",
        ".wp-block-social-links",
        ".wp-block-buttons",
        ".wp-block-jetpack-sharing-buttons",
        ".wp-block-jetpack-like",
        "[class*='share-']",
        "[class*='sharing-']",
        "[class*='social-share']",
        "[class*='related-post']",
        "[class*='newsletter']",
        "[id*='share-']",
        "[id*='sharing-']",
        "[id*='related-post']",
    )

    _MAIN_CONTENT_SELECTORS = (
        "article",
        "[itemprop='articleBody']",
        ".article-body",
        ".article__body",
        ".story-body",
        ".story__body",
        ".entry-content",
        ".post-content",
        ".content-body",
        ".main-content",
        "main",
    )

    _CONTENT_TAGS = (
        "h2",
        "h3",
        "h4",
        "p",
        "blockquote",
        "li",
    )

    _IMAGE_ATTRIBUTES = (
        "src",
        "data-src",
        "data-lazy-src",
        "data-original",
        "data-orig-file",
        "data-large-file",
        "data-image",
        "data-url",
    )

    _SRCSET_ATTRIBUTES = (
        "srcset",
        "data-srcset",
        "data-lazy-srcset",
    )

    _IMAGE_REJECT_TERMS = (
        "logo",
        "icon",
        "avatar",
        "badge",
        "crest",
        "sprite",
        "tracking",
        "pixel",
        "placeholder",
        "spinner",
        "loading",
        "advert",
        "cookie",
        "social",
        "share",
    )

    _BOILERPLATE_PATTERNS = (
        re.compile(r"^\s*subscribe\b", re.IGNORECASE),
        re.compile(r"^\s*sign up\b", re.IGNORECASE),
        re.compile(r"^\s*read more\b", re.IGNORECASE),
        re.compile(r"^\s*related (?:articles|stories|posts|content)\b", re.IGNORECASE),
        re.compile(r"^\s*(?:you may also like|more from|recommended for you)\b", re.IGNORECASE),
        re.compile(r"^\s*follow us\b", re.IGNORECASE),
        re.compile(r"^\s*share this\b", re.IGNORECASE),
        re.compile(r"^\s*share (?:on|via|to)\b", re.IGNORECASE),
        re.compile(r"^\s*(?:facebook|twitter|x|linkedin|whatsapp|email)\s*$", re.IGNORECASE),
        re.compile(r"^\s*(?:share|tweet|pin|send|print)\s*$", re.IGNORECASE),
        re.compile(r"^\s*like this:?\s*$", re.IGNORECASE),
        re.compile(r"^\s*loading(?:\.\.\.)?\s*$", re.IGNORECASE),
        re.compile(r"^\s*advertisement\b", re.IGNORECASE),
        re.compile(r"^\s*cookie\b", re.IGNORECASE),
        re.compile(r"^\s*comments?\b", re.IGNORECASE),
        re.compile(r"^\s*leave a (?:reply|comment)\b", re.IGNORECASE),
        re.compile(r"^\s*posted (?:in|on|by)\b", re.IGNORECASE),
        re.compile(r"^\s*(?:previous|next) (?:article|post|story)\b", re.IGNORECASE),
        re.compile(r"^\s*tags?:\s*", re.IGNORECASE),
        re.compile(r"^\s*categories?:\s*", re.IGNORECASE),
        re.compile(r"^\s*opens? in (?:a )?new window\b", re.IGNORECASE),
        re.compile(r"^\s*copy link\b", re.IGNORECASE),
    )

    def __init__(
        self,
        timeout: float = 30.0,
        headers: Optional[Mapping[str, str]] = None,
    ) -> None:
        self.timeout = float(timeout)
        self.headers = dict(headers or self.DEFAULT_HEADERS)
        self._session = requests.Session()
        self._session.headers.update(self.headers)

    def fetch(self, url: str) -> BeautifulSoup:
        """Fetch *url* and return a parsed HTML document."""

        response = self._session.get(
            url,
            timeout=self.timeout,
        )
        response.raise_for_status()

        if not response.encoding or response.encoding.lower() == "iso-8859-1":
            response.encoding = response.apparent_encoding

        return BeautifulSoup(response.text, "html.parser")

    def close(self) -> None:
        """Close the underlying HTTP session."""

        self._session.close()

    def extract_links(
        self,
        listing_url: str,
        selector: str,
        title_selector: Optional[str] = None,
    ) -> list[ArticleLink]:
        """Extract and de-duplicate article links from a listing page."""

        soup = self.fetch(listing_url)
        articles: list[ArticleLink] = []

        for node in soup.select(selector):
            anchor = self._find_anchor(node)
            if anchor is None:
                continue

            href = anchor.get("href")
            if not isinstance(href, str) or not href.strip():
                continue

            title = self._extract_title(node, anchor, title_selector)
            if not title:
                continue

            articles.append(
                ArticleLink(
                    title=title,
                    url=urljoin(listing_url, href.strip()),
                )
            )

        return self.deduplicate(articles)

    def extract_article(
        self,
        article_url: str,
        body_selector: str,
        image_selector: Optional[str] = None,
    ) -> dict:
        """
        Extract full article content, image and common metadata from a page.

        Existing return keys are preserved. Additional metadata keys are added
        so current callers continue to work unchanged while newer callers can
        use richer article information.
        """
        soup = self.fetch(article_url)

        body = soup.select_one(body_selector) if body_selector else None
        if body is None:
            body = self._find_main_content(soup)

        text = self._extract_content_text(body)

        image = self._extract_image_url(
            soup=soup,
            article_url=article_url,
            image_selector=image_selector,
        )

        metadata = self._extract_metadata(soup, article_url)

        return {
            "url": article_url,
            "text": text.strip(),
            "image": image or metadata["image"],
            "soup": soup,
            "title": metadata["title"],
            "author": metadata["author"],
            "published": metadata["published"],
            "updated": metadata["updated"],
            "canonical": metadata["canonical"],
            "categories": metadata["categories"],
            "tags": metadata["tags"],
        }

    @staticmethod
    def deduplicate(items: Iterable[ArticleLink]) -> list[ArticleLink]:
        """Return links in their original order with duplicate URLs removed."""

        seen: set[str] = set()
        results: list[ArticleLink] = []

        for item in items:
            key = item.url.strip()
            if not key or key in seen:
                continue

            seen.add(key)
            results.append(item)

        return results

    @staticmethod
    def _find_anchor(node: Tag) -> Optional[Tag]:
        if node.name == "a":
            return node

        anchor = node.find("a")
        return anchor if isinstance(anchor, Tag) else None

    @staticmethod
    def _extract_title(
        node: Tag,
        anchor: Tag,
        title_selector: Optional[str],
    ) -> str:
        if title_selector:
            title_node = node.select_one(title_selector)
            if title_node is not None:
                title = title_node.get_text(" ", strip=True)
                if title:
                    return title

        return anchor.get_text(" ", strip=True)

    def _find_main_content(self, soup: BeautifulSoup) -> Optional[Tag]:
        """
        Locate the primary article container.

        First try the new ContentSelector. If anything goes wrong,
        fall back to the original implementation.
        """

        # Try the new selector first
        try:
            selector = ContentSelector()
            node = selector.select(soup)

            if isinstance(node, Tag):
                return node

        except Exception:
            # Fall back to legacy logic
            pass

        # ----- Original implementation -----

        for selector in self._MAIN_CONTENT_SELECTORS:
            node = soup.select_one(selector)
            if isinstance(node, Tag):
                return node

        candidates = [
            node
            for node in soup.find_all(["div", "section"])
            if isinstance(node, Tag)
        ]

        if not candidates:
            return None

        return max(
            candidates,
            key=lambda node: len(node.get_text(" ", strip=True)),
        )

    def _extract_content_text(self, body: Optional[Tag]) -> str:
        if body is None:
            return ""

        working = BeautifulSoup(str(body), "html.parser")

        for selector in self._REMOVAL_SELECTORS:
            for node in working.select(selector):
                node.decompose()

        parts: list[str] = []
        seen: set[str] = set()

        # Standard article elements plus Elementor paragraph-like blocks
        content_selector = (
            "h2, "
            "h3, "
            "h4, "
            "p, "
            "blockquote, "
            "li, "
            "div.elementToProof"
        )

        for element in working.select(content_selector):
            try:
                if not isinstance(element, Tag):
                    continue

                # Ignore outer wrappers containing more specific content elements.
                # This prevents duplicated text while allowing Elementor divs
                # that directly contain article text to be extracted.
                if element.select_one(content_selector):
                    continue

                text = self._clean_text(
                    element.get_text(" ", strip=True)
                )

                if not text or self._is_boilerplate(text):
                    continue

                text = self._strip_inline_boilerplate(text)

                if not text or self._is_boilerplate(text):
                    continue

                normalised = self._normalise_for_deduplication(text)

                if not normalised or normalised in seen:
                    continue

                seen.add(normalised)

                if element.name == "blockquote":
                    parts.append(f'“{text.strip("“”")}”')

                elif element.name == "li":
                    parts.append(f"• {text}")

                else:
                    parts.append(text)

                caption = self._caption_for_element(element)

                if caption:
                    caption = self._strip_inline_boilerplate(caption)
                    caption_key = self._normalise_for_deduplication(caption)

                    if (
                        caption
                        and not self._is_boilerplate(caption)
                        and caption_key
                        and caption_key not in seen
                    ):
                        seen.add(caption_key)
                        parts.append(f"Caption: {caption}")

            except Exception:
                LOGGER.debug(
                    "Content extraction skipped element tag=%s text=%r",
                    element.name,
                    element.get_text(" ", strip=True)[:200],
                    exc_info=True,
                )

        LOGGER.debug(
            "Extracted article content characters=%d parts=%d",
            len("\n\n".join(parts)),
            len(parts),
        )

        return "\n\n".join(parts)

    
    @classmethod
    def _strip_inline_boilerplate(cls, text: str) -> str:
        """
        Remove common social-sharing suffixes accidentally joined to real copy.
        """

        cleaned = cls._clean_text(text)

        inline_patterns = (
            r"\s*[•|]\s*Share on X(?:\s*\(Opens? in new window\))?\s*X\s*$",
            r"\s*[•|]\s*Share on Facebook(?:\s*\(Opens? in new window\))?\s*Facebook\s*$",
            r"\s*[•|]\s*Share on LinkedIn(?:\s*\(Opens? in new window\))?\s*LinkedIn\s*$",
            r"\s*[•|]\s*Share via Email\s*$",
            r"\s*Like this:\s*$",
            r"\s*Loading(?:\.\.\.)?\s*$",
        )

        previous = None
        while previous != cleaned:
            previous = cleaned
            for pattern in inline_patterns:
                cleaned = re.sub(
                    pattern,
                    "",
                    cleaned,
                    flags=re.IGNORECASE,
                ).strip()

        return cleaned

    @staticmethod
    def _normalise_for_deduplication(value: str) -> str:
        cleaned = re.sub(r"[^a-z0-9]+", " ", value.casefold())
        return re.sub(r"\s+", " ", cleaned).strip()

    @classmethod
    def _caption_for_element(cls, element: Tag) -> str:
        figure = element.find_parent("figure")
        if figure is None:
            return ""

        caption = figure.find("figcaption")
        if caption is None:
            return ""

        return cls._clean_text(caption.get_text(" ", strip=True))

    @classmethod
    def _is_boilerplate(cls, text: str) -> bool:
        if len(text) < 2:
            return True

        return any(pattern.search(text) for pattern in cls._BOILERPLATE_PATTERNS)

    @staticmethod
    def _clean_text(value: str) -> str:
        return re.sub(r"\s+", " ", str(value or "")).strip()

    def _extract_metadata(
        self,
        soup: BeautifulSoup,
        article_url: str,
    ) -> dict[str, Any]:
        title = self._first_meta(
            soup,
            ("meta[property='og:title']", "content"),
            ("meta[name='twitter:title']", "content"),
        )

        if not title:
            heading = soup.select_one("h1")
            if heading is not None:
                title = heading.get_text(" ", strip=True)

        if not title and soup.title is not None:
            title = soup.title.get_text(" ", strip=True)

        author = self._first_meta(
            soup,
            ("meta[name='author']", "content"),
            ("meta[property='article:author']", "content"),
        )

        if not author:
            author_node = soup.select_one(
                "[rel='author'], [itemprop='author'], "
                ".author, .byline, .article-author"
            )
            if author_node is not None:
                author = author_node.get_text(" ", strip=True)

        published = self._first_meta(
            soup,
            ("meta[property='article:published_time']", "content"),
            ("meta[name='article:published_time']", "content"),
            ("meta[name='date']", "content"),
            ("time[datetime]", "datetime"),
        )

        updated = self._first_meta(
            soup,
            ("meta[property='article:modified_time']", "content"),
            ("meta[name='article:modified_time']", "content"),
        )

        canonical = ""
        canonical_node = soup.select_one("link[rel='canonical']")
        if canonical_node is not None:
            canonical = urljoin(
                article_url,
                str(canonical_node.get("href") or "").strip(),
            )

        categories = self._meta_values(
            soup,
            "meta[property='article:section']",
        )
        tags = self._meta_values(
            soup,
            "meta[property='article:tag']",
        )

        schema = self._schema_metadata(soup, article_url)

        return {
            "title": title or schema.get("title", ""),
            "author": author or schema.get("author", ""),
            "published": published or schema.get("published", ""),
            "updated": updated or schema.get("updated", ""),
            "canonical": canonical or schema.get("canonical", article_url),
            "categories": categories or schema.get("categories", []),
            "tags": tags or schema.get("tags", []),
            "image": schema.get("image", ""),
        }

    @staticmethod
    def _first_meta(
        soup: BeautifulSoup,
        *rules: tuple[str, str],
    ) -> str:
        for selector, attribute in rules:
            node = soup.select_one(selector)
            if node is None:
                continue

            value = node.get(attribute)
            if isinstance(value, str) and value.strip():
                return value.strip()

        return ""

    @staticmethod
    def _meta_values(
        soup: BeautifulSoup,
        selector: str,
    ) -> list[str]:
        values: list[str] = []

        for node in soup.select(selector):
            value = node.get("content")
            if isinstance(value, str) and value.strip():
                cleaned = value.strip()
                if cleaned not in values:
                    values.append(cleaned)

        return values

    def _schema_metadata(
        self,
        soup: BeautifulSoup,
        article_url: str,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "title": "",
            "author": "",
            "published": "",
            "updated": "",
            "canonical": "",
            "categories": [],
            "tags": [],
            "image": "",
        }

        for script in soup.select("script[type='application/ld+json']"):
            raw = script.string or script.get_text(strip=True)
            if not raw:
                continue

            try:
                payload = json.loads(raw)
            except (TypeError, ValueError, json.JSONDecodeError):
                continue

            for item in self._walk_json(payload):
                if not isinstance(item, dict):
                    continue

                item_type = item.get("@type")
                if isinstance(item_type, list):
                    type_names = {str(value).casefold() for value in item_type}
                else:
                    type_names = {str(item_type or "").casefold()}

                if not type_names.intersection(
                    {
                        "article",
                        "newsarticle",
                        "reportagearticle",
                        "blogposting",
                    }
                ):
                    continue

                result["title"] = self._string_value(
                    item.get("headline") or item.get("name")
                )
                result["author"] = self._author_value(item.get("author"))
                result["published"] = self._string_value(
                    item.get("datePublished")
                )
                result["updated"] = self._string_value(
                    item.get("dateModified")
                )
                result["canonical"] = urljoin(
                    article_url,
                    self._string_value(
                        item.get("url")
                        or item.get("mainEntityOfPage")
                    ),
                )
                result["categories"] = self._list_value(
                    item.get("articleSection")
                )
                result["tags"] = self._list_value(
                    item.get("keywords")
                )
                result["image"] = urljoin(
                    article_url,
                    self._image_value(item.get("image")),
                )
                return result

        return result

    @classmethod
    def _walk_json(cls, value: Any):
        if isinstance(value, dict):
            yield value
            for child in value.values():
                yield from cls._walk_json(child)
        elif isinstance(value, list):
            for child in value:
                yield from cls._walk_json(child)

    @staticmethod
    def _string_value(value: Any) -> str:
        if isinstance(value, str):
            return value.strip()

        if isinstance(value, dict):
            candidate = value.get("@id") or value.get("url") or value.get("name")
            return str(candidate or "").strip()

        return ""

    @classmethod
    def _author_value(cls, value: Any) -> str:
        if isinstance(value, list):
            names = [cls._author_value(item) for item in value]
            return ", ".join(name for name in names if name)

        if isinstance(value, dict):
            return cls._string_value(value.get("name") or value)

        return cls._string_value(value)

    @classmethod
    def _list_value(cls, value: Any) -> list[str]:
        if isinstance(value, list):
            result = []
            for item in value:
                text = cls._string_value(item)
                if text and text not in result:
                    result.append(text)
            return result

        if isinstance(value, str):
            return [
                part.strip()
                for part in re.split(r"[,|]", value)
                if part.strip()
            ]

        return []

    @classmethod
    def _image_value(cls, value: Any) -> str:
        if isinstance(value, str):
            return value.strip()

        if isinstance(value, list):
            for item in value:
                candidate = cls._image_value(item)
                if candidate:
                    return candidate
            return ""

        if isinstance(value, dict):
            return cls._string_value(
                value.get("url") or value.get("contentUrl")
            )

        return ""

    def _extract_image_url(
        self,
        soup: BeautifulSoup,
        article_url: str,
        image_selector: Optional[str],
    ) -> Optional[str]:
        candidates: list[tuple[int, str]] = []

        if image_selector:
            for image in soup.select(image_selector):
                if isinstance(image, Tag):
                    candidate = self._best_image_from_tag(image, article_url)
                    if candidate:
                        candidates.append((10_000, candidate))

        metadata_rules = (
            ("meta[property='og:image:secure_url']", "content", 9_500),
            ("meta[property='og:image']", "content", 9_400),
            ("meta[name='twitter:image']", "content", 9_300),
            ("meta[property='twitter:image']", "content", 9_200),
            ("link[rel='image_src']", "href", 9_100),
        )

        for selector, attribute, score in metadata_rules:
            for node in soup.select(selector):
                value = node.get(attribute)
                if isinstance(value, str) and value.strip():
                    candidate = self._normalise_image_url(
                        article_url,
                        value.strip(),
                    )
                    if self._is_usable_image_url(candidate):
                        candidates.append((score, candidate))

        schema_image = self._schema_metadata(soup, article_url).get("image", "")
        if schema_image and self._is_usable_image_url(schema_image):
            candidates.append((9_000, schema_image))

        fallback_selectors = (
            "article figure img",
            "article picture img",
            "article img",
            "[class*='hero'] img",
            "[class*='featured'] img",
            "[class*='lead'] img",
            "[class*='masthead'] img",
            "main figure img",
            "main picture img",
            "main img",
        )

        selector_weight = len(fallback_selectors)
        for index, selector in enumerate(fallback_selectors):
            base_score = 8_000 - (index * 100)
            for image in soup.select(selector):
                if not isinstance(image, Tag):
                    continue

                candidate = self._best_image_from_tag(image, article_url)
                if not candidate:
                    continue

                width = self._numeric_dimension(image.get("width"))
                height = self._numeric_dimension(image.get("height"))
                area_bonus = min((width * height) // 1000, 1500)
                candidates.append((base_score + area_bonus, candidate))

        if not candidates:
            return None

        candidates.sort(key=lambda item: item[0], reverse=True)

        seen: set[str] = set()
        for _, candidate in candidates:
            key = candidate.casefold()
            if key in seen:
                continue
            seen.add(key)
            return candidate

        return None

    @classmethod
    def _best_image_from_tag(
        cls,
        image: Tag,
        article_url: str,
    ) -> str:
        candidates: list[tuple[int, str]] = []

        for attribute in cls._IMAGE_ATTRIBUTES:
            value = image.get(attribute)
            if isinstance(value, str) and value.strip():
                candidate = cls._normalise_image_url(
                    article_url,
                    value.strip(),
                )
                if cls._is_usable_image_url(candidate):
                    score = 100
                    if attribute in {"data-large-file", "data-orig-file"}:
                        score += 300
                    candidates.append((score, candidate))

        for attribute in cls._SRCSET_ATTRIBUTES:
            srcset = image.get(attribute)
            if not isinstance(srcset, str) or not srcset.strip():
                continue

            for descriptor_score, candidate in cls._parse_srcset(srcset):
                absolute = cls._normalise_image_url(
                    article_url,
                    candidate,
                )
                if cls._is_usable_image_url(absolute):
                    candidates.append((descriptor_score, absolute))

        picture = image.find_parent("picture")
        if picture is not None:
            for source in picture.find_all("source"):
                for attribute in cls._SRCSET_ATTRIBUTES:
                    srcset = source.get(attribute)
                    if not isinstance(srcset, str) or not srcset.strip():
                        continue

                    for descriptor_score, candidate in cls._parse_srcset(srcset):
                        absolute = cls._normalise_image_url(
                            article_url,
                            candidate,
                        )
                        if cls._is_usable_image_url(absolute):
                            candidates.append((descriptor_score + 500, absolute))

        if not candidates:
            return ""

        return max(candidates, key=lambda item: item[0])[1]

    @staticmethod
    def _parse_srcset(srcset: str) -> list[tuple[int, str]]:
        results: list[tuple[int, str]] = []

        for item in srcset.split(","):
            parts = item.strip().split()
            if not parts:
                continue

            candidate = parts[0].strip()
            descriptor = parts[1].strip().casefold() if len(parts) > 1 else ""
            score = 100

            if descriptor.endswith("w"):
                try:
                    score = int(float(descriptor[:-1]))
                except ValueError:
                    score = 100
            elif descriptor.endswith("x"):
                try:
                    score = int(float(descriptor[:-1]) * 1000)
                except ValueError:
                    score = 100

            results.append((score, candidate))

        return results

    @classmethod
    def _is_usable_image_url(cls, value: str) -> bool:
        candidate = str(value or "").strip()
        if not candidate:
            return False

        parsed = urlparse(candidate)
        if parsed.scheme.casefold() not in {"http", "https"}:
            return False

        lowered = candidate.casefold()
        return not any(term in lowered for term in cls._IMAGE_REJECT_TERMS)

    @staticmethod
    def _normalise_image_url(article_url: str, value: str) -> str:
        candidate = str(value or "").strip()
        if not candidate or candidate.startswith("data:"):
            return ""

        if candidate.startswith("//"):
            scheme = urlparse(article_url).scheme or "https"
            return f"{scheme}:{candidate}"

        return urljoin(article_url, candidate)

    @staticmethod
    def _numeric_dimension(value: Any) -> int:
        match = re.search(r"\d+", str(value or ""))
        return int(match.group(0)) if match else 0


__all__ = ["ArticleLink", "ArticleScraper"]
