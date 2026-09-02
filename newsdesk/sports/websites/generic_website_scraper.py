"""Generic configurable collector for official sports websites."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import json
import logging
import re
from typing import Any
from urllib.parse import parse_qsl, urljoin, urlparse, urlunparse
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup, Tag
import soupsieve

from newsdesk.sources.base_scraper import BaseScraper, ScrapeResponse
from newsdesk.sports.websites.source import WebsiteSource
from newsdesk.story import Story
from newsdesk.sports.media_policy import is_still_image_url


LOGGER = logging.getLogger(__name__)


class GenericWebsiteScraper(BaseScraper):
    """
    Collect feed-level stories from a configured website listing.

    The collector deliberately does not fetch each article body. Selected-story
    enrichment remains the responsibility of ``SportArticleService`` and the
    shared ``ArticleScraper``.
    """

    # Source listings already cap their result count.  Sport is an information
    # feed, so age does not decide inclusion; dates decide display order.
    DEFAULT_MAX_AGE_DAYS = None

    DEFAULT_LINK_SELECTORS = (
        "article a[href]",
        ".post a[href]",
        ".news a[href]",
        ".news-item a[href]",
        ".blog a[href]",
        ".blog-post a[href]",
        ".entry a[href]",
        ".card a[href]",
        ".latest-news a[href]",
        "main h2 a[href]",
        "main h3 a[href]",
        "main h4 a[href]",
    )

    DEFAULT_CARD_SELECTORS = (
        "article",
        ".post",
        ".news-item",
        ".blog-post",
        ".entry",
        ".card",
        "li",
    )

    DEFAULT_TITLE_SELECTORS = (
        "h1",
        "h2",
        "h3",
        "h4",
        ".title",
        ".entry-title",
        ".post-title",
        ".news-title",
    )

    DEFAULT_SUMMARY_SELECTORS = (
        ".excerpt",
        ".summary",
        ".description",
        ".entry-summary",
        ".post-excerpt",
        "p",
    )

    DEFAULT_DATE_SELECTORS = (
        "time[datetime]",
        "time",
        ".date",
        ".published",
        ".post-date",
        ".entry-date",
    )

    DEFAULT_IMAGE_SELECTORS = (
        "img[src]",
        "img[data-src]",
        "img[data-lazy-src]",
    )

    DEFAULT_EXCLUDED_URL_PARTS = (
        "#",
        "javascript:",
        "mailto:",
        "tel:",
        "/contact",
        "/about",
        "/privacy",
        "/terms",
        "/cookie",
        "/login",
        "/sign-in",
        "/membership",
        "/shop",
        "/gallery",
        "/sponsors",
        "/safeguarding",
    )

    PREFERRED_ARTICLE_URL_PARTS = (
        "/news/",
        "/latest/",
        "/story/",
        "/article/",
        "/blog/",
        "/event/",
        "/match-report/",
        "/race-report/",
    )

    ARTICLE_YEAR_PATH_PATTERN = re.compile(r"(?:^|/)(20\d{2})(?:/|$)")
    DATED_BLOG_SEGMENT_PATTERN = re.compile(
        r"^\d{1,2}(?:st|nd|rd|th)?-[a-z]+-(20\d{2})$",
        flags=re.IGNORECASE,
    )

    STANDALONE_CATEGORY_TITLES = (
        "cross country",
        "fell running",
        "mini league",
        "road running",
        "track and field",
        "latest news",
        "grand prix",
        "summer league",
        "northern league",
        "local xc league",
        "county development league",
    )

    LISTING_URL_SEGMENTS = frozenset(
        {
            "archive",
            "archives",
            "categories",
            "category",
            "filter",
            "filtered",
            "tag",
            "tags",
            "taxonomy",
        }
    )

    GENERIC_LISTING_TITLES = frozenset(
        {
            "all news",
            "archive",
            "archives",
            "blog",
            "latest",
            "latest news",
            "news",
            "news archive",
        }
    )

    URL_ORDINAL_DATE_PATTERN = re.compile(
        r"(?:^|/)(\d{1,2})(?:st|nd|rd|th)?-([a-z]+)-(20\d{2})(?:/|$)",
        flags=re.IGNORECASE,
    )
    URL_NUMERIC_DATE_PATTERN = re.compile(
        r"(?:^|/)(20\d{2})/(\d{1,2})(?:/(\d{1,2}))?(?:/|$)"
    )
    URL_ISO_DATE_PATTERN = re.compile(
        r"(?:^|/)(20\d{2})-(\d{2})-(\d{2})(?:/|$)"
    )

    EXCLUDED_URL_ENDINGS = (
        "/about",
        "/contact",
        "/privacy",
        "/accessibility",
        "/history",
        "/committee",
        "/join",
        "/shop",
        "/calendar",
        "/results",
        "/fixtures",
        "/tables",
    )

    NEGATIVE_URL_SCORES = (
        ("login", -100),
        ("register", -100),
        ("membership", -100),
        ("committee", -100),
        ("contact", -100),
        ("privacy", -100),
        ("accessibility", -100),
        ("safeguarding", -100),
        ("policies", -100),
        ("policy", -100),
        ("history", -100),
        ("calendar", -80),
        ("fixtures", -80),
        ("results", -80),
        ("tables", -80),
        ("downloads", -80),
        ("pdf", -80),
        ("sponsors", -50),
        ("shop", -50),
        ("volunteers", -50),
    )

    DEFAULT_EXCLUDED_TITLES = (
        "home",
        "read more",
        "view",
        "more",
        "next",
        "previous",
        "contact us",
        "about us",
        "privacy policy",
        "join the club",
        "find out more",
        "latest news",
        "news",
        "events",
        "gallery",
        "menu",
        "about",
        "committee",
        "membership",
        "contact",
        "privacy",
        "accessibility",
        "policies",
        "downloads",
        "fixtures",
        "results",
        "tables",
    )

    def __init__(self, source: WebsiteSource) -> None:
        if not isinstance(source, WebsiteSource):
            raise TypeError("source must be a WebsiteSource.")

        self.definition = source
        self._discovery_scores: dict[str, int] = {}
        self._publication_feed_metadata: dict[tuple[str, str], dict[str, str]] = {}
        self._last_candidate_count = 0
        self._last_pre_recency_count = 0
        self._pre_recency_urls: set[str] = set()

        super().__init__(
            source_name=source.name,
            source_url=source.listing_url,
            timeout=source.timeout,
            request_delay=source.request_delay,
            extra_headers=source.headers,
        )

    def fetch(self, url: str | None = None) -> ScrapeResponse:
        """Optionally establish a site session before fetching its listing."""

        content_api_url = str(
            self.definition.metadata.get("content_api_url", "") or ""
        ).strip()
        target = str(url or content_api_url or self.source_url).strip()
        warmup_url = str(
            self.definition.metadata.get("listing_warmup_url", "") or ""
        ).strip()
        if warmup_url and self._url_page_key(target) == self._url_page_key(
            self.source_url
        ):
            try:
                super().fetch(warmup_url)
            except Exception:
                LOGGER.debug(
                    "%s listing warm-up failed; continuing with listing request.",
                    self.source_name,
                )
        return super().fetch(target)

    def parse(self, response: ScrapeResponse) -> Iterable[Story]:
        if self.definition.metadata.get("content_api_url"):
            return self._stories_from_content_api(response)

        soup = BeautifulSoup(response.body, "html.parser")
        self._discovery_scores.clear()
        self._publication_feed_metadata = self._load_publication_feed_metadata()
        anchors = self._candidate_anchors(soup)
        self._last_candidate_count = len(
            {
                self._normalise_url(
                    urljoin(response.url, str(anchor.get("href") or ""))
                )
                for anchor in anchors
            }
        )
        self._last_pre_recency_count = 0
        self._pre_recency_urls.clear()
        stories: list[Story] = []
        seen_keys: set[str] = set()

        for anchor in anchors:
            story = self._story_from_anchor(anchor, response.url)
            if story is None:
                continue

            if not self._append_unique_story(story, stories, seen_keys):
                continue

            if len(stories) >= self.definition.max_stories:
                self._log_collection_summary(len(stories))
                return stories

        for story in self._stories_from_standalone_items(soup, response.url):
            if not self._append_unique_story(story, stories, seen_keys):
                continue

            if len(stories) >= self.definition.max_stories:
                break

        return stories

    def _candidate_anchors(self, soup: BeautifulSoup) -> list[Tag]:
        route = str(self.definition.metadata.get("collector_route", ""))
        route_selectors = {
            "pitchero": (
                "a[href*='/news/']",
                "a[href*='/news']",
                "article a[href]",
            ),
            "club-cms": (
                "a[href*='/news/']",
                "a[href*='/news']",
                "article a[href]",
                "main a[href]",
            ),
        }.get(route, ())
        selectors = (
            self.definition.article_link_selectors
            or list(route_selectors)
            or list(self.DEFAULT_LINK_SELECTORS)
        )

        anchors: list[Tag] = []
        seen: set[int] = set()

        for selector in selectors:
            try:
                nodes = soup.select(selector)
            except Exception:
                continue

            for node in nodes:
                anchor = node if node.name == "a" else node.find("a", href=True)
                if not isinstance(anchor, Tag) or not anchor.get("href"):
                    continue

                identity = id(anchor)
                if identity in seen:
                    continue

                seen.add(identity)
                anchors.append(anchor)

        if anchors:
            return anchors

        return [
            node
            for node in soup.find_all("a", href=True)
            if isinstance(node, Tag)
        ]

    def _story_from_anchor(
        self,
        anchor: Tag,
        base_url: str,
    ) -> Story | None:
        href = str(anchor.get("href") or "").strip()
        url = self._normalise_url(urljoin(base_url, href))

        if not self._url_is_allowed(url, base_url):
            self._log_rejected_candidate(
                url or href,
                self._url_score(url),
                "URL not allowed",
            )
            return None

        card, broad_context = self._find_card_context(anchor)
        title = self._extract_title(anchor, card)

        summary = self._extract_text(
            card,
            self.definition.summary_selectors
            or list(self.DEFAULT_SUMMARY_SELECTORS),
            exclude=title,
        )
        published, published_at = self._resolve_publication_date(card, url)
        image_url = self._extract_image(card, base_url)
        feed_metadata = self._publication_feed_metadata.get(
            self._url_page_key(url),
            {},
        )
        if not published and feed_metadata.get("published"):
            published_at = self._parse_publication_datetime(
                feed_metadata["published"]
            )
            published = (
                published_at.isoformat() if published_at is not None else ""
            )
        if not summary:
            summary = feed_metadata.get("summary", "")
        if not image_url:
            image_url = feed_metadata.get("image_url", "")
        if self._is_homepage_candidate(url, published_at, card):
            self._log_rejected_candidate(
                url,
                self._url_score(url),
                "homepage-not-article",
            )
            return None

        listing_reason = self._listing_rejection_reason(
            anchor=anchor,
            card=card,
            url=url,
            title=title,
            summary=summary,
            published=published,
            broad_context=broad_context,
        )
        if listing_reason:
            self._log_rejected_candidate(
                url,
                self._url_score(url),
                listing_reason,
            )
            return None

        if not self._title_is_allowed(title):
            self._log_rejected_candidate(
                url,
                self._url_score(url),
                "title not allowed",
            )
            return None

        self._pre_recency_urls.add(url)
        self._last_pre_recency_count = len(self._pre_recency_urls)
        recency_reason = self._recency_rejection_reason(published_at)
        if recency_reason:
            self._log_recency_rejection(
                url=url,
                published_at=published_at,
                reason=recency_reason,
            )
            return None

        if not self._candidate_passes_score(
            url=url,
            title=title,
            published=published,
            image_url=image_url,
            card=card,
        ):
            return None

        story = self._build_story(
            title=title,
            summary=summary,
            url=url,
            published=published,
            image_url=image_url,
            article_content_status="feed",
        )
        return story

    def _stories_from_standalone_items(
        self,
        soup: BeautifulSoup,
        base_url: str,
    ) -> list[Story]:
        selectors = self.definition.standalone_item_selectors
        if not selectors:
            return []

        stories: list[Story] = []
        seen_titles: set[str] = set()

        for selector in selectors:
            try:
                nodes = soup.select(selector)
            except Exception:
                continue

            for node in nodes:
                if not isinstance(node, Tag):
                    continue

                title = self._clean_text(node.get_text(" ", strip=True))
                title_key = self._normalise_text(title)
                if not self._title_is_allowed(title) or title_key in seen_titles:
                    continue

                seen_titles.add(title_key)
                card = self._standalone_card(node)
                summary = self._extract_text(
                    card,
                    self.definition.summary_selectors
                    or list(self.DEFAULT_SUMMARY_SELECTORS),
                    exclude=title,
                )

                if not summary:
                    summary = self._following_text(node)

                if not summary or len(summary.split()) < 5:
                    continue

                published, published_at = self._resolve_publication_date(
                    card,
                    base_url,
                )
                if published_at is not None:
                    recency_reason = self._recency_rejection_reason(published_at)
                    if recency_reason:
                        self._log_recency_rejection(
                            url=base_url,
                            published_at=published_at,
                            reason=recency_reason,
                        )
                        continue
                image_url = self._extract_image(card, base_url)
                fragment = self._slugify(title)
                url = f"{self._normalise_url(base_url)}#{fragment}"
                if not self._candidate_passes_score(
                    url=url,
                    title=title,
                    published=published,
                    image_url=image_url,
                    card=card,
                ):
                    continue

                stories.append(
                    self._build_story(
                        title=title,
                        summary=summary,
                        url=url,
                        published=published,
                        image_url=image_url,
                        article_content_status="complete",
                    )
                )

        self._log_collection_summary(len(stories))
        return stories

    def _stories_from_content_api(self, response: ScrapeResponse) -> list[Story]:
        """Build candidates from an optional official listing JSON endpoint."""

        self._discovery_scores.clear()
        self._publication_feed_metadata = {}
        self._last_pre_recency_count = 0
        self._pre_recency_urls.clear()
        try:
            payload = json.loads(response.body)
        except (TypeError, ValueError) as error:
            LOGGER.debug(
                "%s content API response was not valid JSON: %s",
                self.definition.name,
                error,
            )
            self._last_candidate_count = 0
            self._log_collection_summary(0)
            return []

        records = payload.get("data", []) if isinstance(payload, dict) else []
        self._last_candidate_count = (
            len(records) if isinstance(records, list) else 0
        )
        stories: list[Story] = []
        seen_keys: set[str] = set()
        for record in records if isinstance(records, list) else []:
            story = self._story_from_content_api_record(record)
            if story is None or not self._append_unique_story(
                story,
                stories,
                seen_keys,
            ):
                continue
            if len(stories) >= self.definition.max_stories:
                break

        self._log_collection_summary(len(stories))
        return stories

    def _story_from_content_api_record(self, record: Any) -> Story | None:
        """Normalise one candidate supplied by an official listing API."""

        attributes = (
            record.get("attributes", {})
            if isinstance(record, dict)
            else {}
        )
        if not isinstance(attributes, dict):
            return None

        title = self._clean_text(attributes.get("postTitle"))
        path = str(attributes.get("postSlug") or "").strip()
        url = self._normalise_url(urljoin(self.definition.listing_url, path))
        published = str(attributes.get("publishedDateTime") or "").strip()
        published_at = self._parse_publication_datetime(published)
        summary = self._clean_text(attributes.get("description"))[:700]
        image_data = attributes.get("imageData") or {}
        image_url = (
            str(
                image_data.get("location")
                or image_data.get("Location")
                or ""
            ).strip()
            if isinstance(image_data, dict)
            else ""
        )
        category = self._normalise_text(attributes.get("postCategoryName"))

        if not self._url_is_allowed(url, self.definition.listing_url):
            self._log_rejected_candidate(
                url or path,
                self._url_score(url),
                "URL not allowed",
            )
            return None
        if category and self._matches_patterns(
            category,
            list(self.definition.metadata.get("exclude_api_categories", [])),
        ):
            self._log_rejected_candidate(
                url,
                self._url_score(url),
                "excluded category",
            )
            return None
        if not self._title_is_allowed(title):
            self._log_rejected_candidate(
                url,
                self._url_score(url),
                "title not allowed",
            )
            return None

        self._pre_recency_urls.add(url)
        self._last_pre_recency_count = len(self._pre_recency_urls)
        recency_reason = self._recency_rejection_reason(published_at)
        if recency_reason:
            self._log_recency_rejection(
                url=url,
                published_at=published_at,
                reason=recency_reason,
            )
            return None

        card = BeautifulSoup("<article></article>", "html.parser").article
        if not isinstance(card, Tag):
            return None
        if published:
            time_node = BeautifulSoup("<time></time>", "html.parser").time
            if isinstance(time_node, Tag):
                time_node["datetime"] = published
                card.append(time_node)
        if summary:
            paragraph = BeautifulSoup("<p></p>", "html.parser").p
            if isinstance(paragraph, Tag):
                paragraph.string = summary
                card.append(paragraph)
        if image_url:
            image = BeautifulSoup("<img>", "html.parser").img
            if isinstance(image, Tag):
                image["src"] = image_url
                card.append(image)
        if not self._candidate_passes_score(
            url=url,
            title=title,
            published=published,
            image_url=image_url,
            card=card,
        ):
            return None

        return self._build_story(
            title=title,
            summary=summary,
            url=url,
            published=published_at.isoformat() if published_at else published,
            image_url=image_url,
            article_content_status="feed",
        )

    def _log_collection_summary(self, accepted_count: int) -> None:
        LOGGER.info(
            "%s: collected %d candidates, accepted %d current stories.",
            self.definition.name,
            self._last_candidate_count,
            accepted_count,
        )

    def _load_publication_feed_metadata(self) -> dict[tuple[str, str], dict[str, str]]:
        """Read optional source-level RSS metadata without creating another source."""

        feed_url = str(
            self.definition.metadata.get("publication_feed_url", "") or ""
        ).strip()
        if not feed_url:
            return {}
        try:
            response = super().fetch(feed_url)
            root = ET.fromstring(response.body)
        except Exception as error:
            LOGGER.debug(
                "%s publication metadata feed unavailable: %s",
                self.definition.name,
                error,
            )
            return {}

        metadata: dict[tuple[str, str], dict[str, str]] = {}
        for item in root.findall(".//item"):
            link = str(item.findtext("link") or "").strip()
            if not link:
                continue
            description = BeautifulSoup(
                str(item.findtext("description") or ""),
                "html.parser",
            ).get_text(" ", strip=True)
            enclosure = item.find("enclosure")
            metadata[self._url_page_key(link)] = {
                "published": str(item.findtext("pubDate") or "").strip(),
                "summary": self._clean_text(description)[:700],
                "image_url": (
                    str(enclosure.get("url") or "").strip()
                    if enclosure is not None
                    else ""
                ),
            }
        return metadata

    def _append_unique_story(
        self,
        story: Story,
        stories: list[Story],
        seen_keys: set[str],
    ) -> bool:
        duplicate_keys = self._duplicate_keys(story)
        if seen_keys.intersection(duplicate_keys):
            self._log_rejected_candidate(
                story.url,
                self._discovery_scores.get(story.url, 0),
                "duplicate",
            )
            return False

        seen_keys.update(duplicate_keys)
        stories.append(story)
        return True

    def _accept_candidate(
        self,
        url: str,
        score: int,
        reasons: list[str],
    ) -> bool:
        accepted = score > 0
        LOGGER.debug(
            "candidate URL=%s score=%d %s reason=%s",
            url,
            score,
            "accepted" if accepted else "rejected",
            ", ".join(reasons) or "no scoring signals",
        )
        if accepted:
            self._discovery_scores[url] = score
        return accepted

    def _candidate_passes_score(
        self,
        *,
        url: str,
        title: str,
        published: str,
        image_url: str,
        card: Tag,
    ) -> bool:
        score, reasons = self._score_candidate(
            url=url,
            title=title,
            published=published,
            image_url=image_url,
            card=card,
        )
        return self._accept_candidate(url, score, reasons)

    @staticmethod
    def _log_rejected_candidate(url: str, score: int, reason: str) -> None:
        LOGGER.debug(
            "candidate URL=%s score=%s rejected reason=%s",
            url,
            score,
            reason,
        )

    def _build_story(
        self,
        *,
        title: str,
        summary: str,
        url: str,
        published: str,
        image_url: str,
        article_content_status: str,
    ) -> Story:
        tags = self._merge_unique(
            [self.definition.sport, *self.definition.tags],
        )

        story = Story(
            title=title,
            summary=summary,
            body=summary,
            source=self.definition.name,
            url=url,
            published=published,
            location=self.definition.location,
            category=self.definition.sport,
            image_url=image_url,
            image_credit=self.definition.organisation,
            tags=tags,
            scraped_at=datetime.now(timezone.utc).isoformat(),
        )

        story.extras.update(
            {
                "sport": self.definition.sport,
                "source_kind": "generic_website",
                "source_listing_url": self.definition.listing_url,
                "source_organisation": self.definition.organisation,
                "article_content_status": article_content_status,
                **dict(self.definition.metadata),
            }
        )

        return story


    def _standalone_card(self, node: Tag) -> Tag:
        for parent in node.parents:
            if not isinstance(parent, Tag):
                continue
            if parent.name in {"article", "section"}:
                return parent
            classes = " ".join(parent.get("class", []))
            if any(word in classes.casefold() for word in ("card", "post", "item", "event")):
                return parent
            if parent.name in {"main", "body"}:
                break
        return node.parent if isinstance(node.parent, Tag) else node

    def _following_text(self, node: Tag) -> str:
        parts: list[str] = []
        sibling = node.next_sibling

        while sibling is not None and len(" ".join(parts)) < 700:
            if isinstance(sibling, Tag):
                if sibling.name in {"h1", "h2", "h3", "h4"}:
                    break
                text = self._clean_text(sibling.get_text(" ", strip=True))
                if text:
                    parts.append(text)
            sibling = sibling.next_sibling

        return self._clean_text(" ".join(parts))[:700]

    def _find_card(self, anchor: Tag) -> Tag:
        card, _ = self._find_card_context(anchor)
        return card

    def _find_card_context(self, anchor: Tag) -> tuple[Tag, bool]:
        selectors = (
            self.definition.card_selectors
            or list(self.DEFAULT_CARD_SELECTORS)
        )

        for parent in anchor.parents:
            if not isinstance(parent, Tag):
                continue
            if any(self._matches(parent, selector) for selector in selectors):
                if self._distinct_link_count(parent) > 3:
                    return self._smallest_local_context(anchor, parent), True
                return parent, False
            if parent.name in {"main", "body"}:
                break

        card = anchor.parent if isinstance(anchor.parent, Tag) else anchor
        return card, False

    def _smallest_local_context(self, anchor: Tag, boundary: Tag) -> Tag:
        fallback = anchor.parent if isinstance(anchor.parent, Tag) else anchor
        for parent in anchor.parents:
            if not isinstance(parent, Tag) or parent is boundary:
                break
            if parent.name not in {"article", "div", "li", "section"}:
                continue
            if self._distinct_link_count(parent) > 3:
                continue
            if parent.select_one("p, time, img, .date, .summary, .excerpt"):
                return parent
        return fallback

    @staticmethod
    def _distinct_link_count(card: Tag) -> int:
        return len(
            {
                str(node.get("href") or "").strip()
                for node in card.select("a[href]")
                if str(node.get("href") or "").strip()
            }
        )

    def _listing_rejection_reason(
        self,
        *,
        anchor: Tag,
        card: Tag,
        url: str,
        title: str,
        summary: str,
        published: str,
        broad_context: bool,
    ) -> str:
        title_key = self._normalise_text(title)
        has_article_evidence = self._has_local_article_evidence(
            card=card,
            url=url,
            summary=summary,
            published=published,
        )

        listing_structure = self._listing_url_structure(url)
        if title_key in self.GENERIC_LISTING_TITLES:
            return "category-or-listing-page"
        if listing_structure == "archive":
            return "archive-page"
        if listing_structure:
            return "category-or-listing-page"
        if (
            title_key in self.STANDALONE_CATEGORY_TITLES
            and not has_article_evidence
        ):
            return "standalone-category-title"
        if broad_context and not has_article_evidence:
            return "category-or-listing-page"
        if self._is_navigation_first_context(
            card=card,
            summary=summary,
            published=published,
        ):
            return "navigation-first-page"
        if (
            self._is_single_undated_blog_segment(url)
            and not has_article_evidence
            and self._has_listing_marker(anchor)
        ):
            return "undated-blog-filter"
        return ""

    def _has_local_article_evidence(
        self,
        *,
        card: Tag,
        url: str,
        summary: str,
        published: str,
    ) -> bool:
        return bool(
            published
            or summary
            or self._has_article_year_path(url)
            or self._has_dated_blog_path(url)
            or self._has_article_metadata(card)
        )

    def _has_article_metadata(self, card: Tag) -> bool:
        return bool(
            self._has_article_body_schema(card)
            or self._has_card_json_ld_article(card)
            or self._has_card_open_graph_article(card)
        )

    def _is_homepage_candidate(
        self,
        url: str,
        published_at: datetime | None,
        card: Tag,
    ) -> bool:
        if published_at is not None or self._has_article_metadata(card):
            return False

        parsed = urlparse(url)
        is_website_root = parsed.path.rstrip("/") == ""
        is_listing_root = self._url_page_key(url) == self._url_page_key(
            self.definition.listing_url
        )
        return is_website_root or is_listing_root

    @staticmethod
    def _url_page_key(url: str) -> tuple[str, str]:
        parsed = urlparse(url)
        return (
            parsed.netloc.casefold().removeprefix("www."),
            parsed.path.casefold().rstrip("/"),
        )

    @classmethod
    def _has_listing_url_structure(cls, url: str) -> bool:
        return bool(cls._listing_url_structure(url))

    @classmethod
    def _listing_url_structure(cls, url: str) -> str:
        parsed = urlparse(url)
        path_segments = {
            segment.casefold()
            for segment in parsed.path.split("/")
            if segment
        }
        query_keys = {
            key.casefold()
            for key, _ in parse_qsl(parsed.query, keep_blank_values=True)
        }
        matches = cls.LISTING_URL_SEGMENTS.intersection(
            path_segments | query_keys
        )
        if matches.intersection({"archive", "archives"}):
            return "archive"
        return "listing" if matches else ""

    def _is_navigation_first_context(
        self,
        *,
        card: Tag,
        summary: str,
        published: str,
    ) -> bool:
        links = card.select("a[href]")
        if len(links) < 2:
            return False
        if published or summary or self._has_article_metadata(card):
            return False

        text = self._clean_text(card.get_text(" ", strip=True))
        link_text = self._clean_text(
            " ".join(link.get_text(" ", strip=True) for link in links)
        )
        return bool(text and len(link_text) / len(text) >= 0.6)

    @classmethod
    def _is_single_undated_blog_segment(cls, url: str) -> bool:
        segments = [
            segment
            for segment in urlparse(url).path.strip("/").split("/")
            if segment
        ]
        return bool(
            len(segments) == 2
            and segments[0].casefold() == "blog"
            and not cls._is_dated_blog_segment(segments[1])
        )

    @classmethod
    def _has_dated_blog_path(cls, url: str) -> bool:
        segments = [
            segment
            for segment in urlparse(url).path.strip("/").split("/")
            if segment
        ]
        if len(segments) < 3 or segments[0].casefold() != "blog":
            return False
        return cls._is_dated_blog_segment(segments[1])

    @classmethod
    def _is_dated_blog_segment(cls, segment: str) -> bool:
        match = cls.DATED_BLOG_SEGMENT_PATTERN.fullmatch(segment)
        if match:
            return cls._is_plausible_publication_year(int(match.group(1)))
        if segment.isdigit() and len(segment) == 4:
            return cls._is_plausible_publication_year(int(segment))
        return False

    @staticmethod
    def _is_plausible_publication_year(year: int) -> bool:
        return 2000 <= year <= datetime.now(timezone.utc).year + 1

    @staticmethod
    def _has_listing_marker(anchor: Tag) -> bool:
        values = [
            *anchor.get("class", []),
            *anchor.get("rel", []),
        ]
        if isinstance(anchor.parent, Tag):
            values.extend(anchor.parent.get("class", []))
        marker_text = " ".join(str(value) for value in values).casefold()
        return any(
            marker in marker_text
            for marker in ("archive", "category", "filter", "tag", "taxonomy")
        )

    def _extract_title(self, anchor: Tag, card: Tag) -> str:
        selectors = (
            self.definition.title_selectors
            or list(self.DEFAULT_TITLE_SELECTORS)
        )

        for selector in selectors:
            node = card.select_one(selector)
            if isinstance(node, Tag):
                text = self._clean_text(node.get_text(" ", strip=True))
                if text:
                    return text

        for attribute in ("aria-label", "title"):
            value = self._clean_text(anchor.get(attribute, ""))
            if value:
                return value

        return self._clean_text(anchor.get_text(" ", strip=True))

    def _extract_text(
        self,
        card: Tag,
        selectors: list[str],
        *,
        exclude: str = "",
    ) -> str:
        excluded_key = self._normalise_text(exclude)

        for selector in selectors:
            for node in card.select(selector):
                text = self._clean_text(node.get_text(" ", strip=True))
                if not text or self._normalise_text(text) == excluded_key:
                    continue
                if len(text.split()) < 5:
                    continue
                return text[:700]

        return ""

    def _extract_date(self, card: Tag) -> str:
        values = self._candidate_date_values(card)
        return values[0] if values else ""

    def _candidate_date_values(self, card: Tag) -> list[str]:
        values: list[str] = []
        datetime_node = card.select_one("time[datetime]")
        if isinstance(datetime_node, Tag):
            value = str(datetime_node.get("datetime") or "").strip()
            if value:
                values.append(value)

        selectors = (
            self.definition.date_selectors
            or list(self.DEFAULT_DATE_SELECTORS)
        )

        for selector in selectors:
            node = card.select_one(selector)
            if not isinstance(node, Tag):
                continue

            value = str(node.get("datetime") or "").strip()
            if not value:
                value = self._clean_text(node.get_text(" ", strip=True))
            if value and value not in values:
                values.append(value)

        for selector, attribute in (
            ("[itemprop='datePublished']", "content"),
            ("meta[property='article:published_time']", "content"),
            ("meta[name='article:published_time']", "content"),
        ):
            node = (
                card
                if self._matches(card, selector)
                else card.select_one(selector)
            )
            if not isinstance(node, Tag):
                continue
            value = str(
                node.get(attribute)
                or node.get("datetime")
                or node.get_text(" ", strip=True)
                or ""
            ).strip()
            if value and value not in values:
                values.append(value)

        for node in card.select("script[type='application/ld+json']"):
            match = re.search(
                r'"datePublished"\s*:\s*"([^"]+)"',
                node.get_text(),
                flags=re.IGNORECASE,
            )
            if match and match.group(1) not in values:
                values.append(match.group(1))

        return values

    def _resolve_publication_date(
        self,
        card: Tag,
        url: str,
    ) -> tuple[str, datetime | None]:
        for value in self._candidate_date_values(card):
            parsed = self._parse_publication_datetime(value)
            if parsed is not None:
                return value, parsed

        parsed = self._publication_date_from_url(url)
        if parsed is not None:
            return parsed.isoformat(), parsed
        return "", None

    @classmethod
    def _parse_publication_datetime(cls, value: str) -> datetime | None:
        cleaned = cls._clean_text(value)
        if not cleaned:
            return None

        iso_value = cleaned.replace("Z", "+00:00")
        try:
            return cls._aware_datetime(datetime.fromisoformat(iso_value))
        except ValueError:
            pass

        try:
            return cls._aware_datetime(parsedate_to_datetime(cleaned))
        except (TypeError, ValueError, OverflowError):
            pass

        without_ordinal = re.sub(
            r"(?<=\d)(?:st|nd|rd|th)\b",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        for date_format in (
            "%d %B %Y",
            "%d %b %Y",
            "%d/%m/%Y",
            "%Y/%m/%d",
            "%Y-%m-%d",
            "%B %d, %Y",
            "%b %d, %Y",
        ):
            try:
                return datetime.strptime(without_ordinal, date_format).replace(
                    tzinfo=timezone.utc
                )
            except ValueError:
                continue
        return None

    @staticmethod
    def _aware_datetime(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @classmethod
    def _publication_date_from_url(cls, url: str) -> datetime | None:
        path = urlparse(url).path

        ordinal_match = cls.URL_ORDINAL_DATE_PATTERN.search(path)
        if ordinal_match:
            month = cls._month_number(ordinal_match.group(2))
            if month is not None:
                return cls._safe_utc_date(
                    int(ordinal_match.group(3)),
                    month,
                    int(ordinal_match.group(1)),
                )

        iso_match = cls.URL_ISO_DATE_PATTERN.search(path)
        if iso_match:
            return cls._safe_utc_date(
                int(iso_match.group(1)),
                int(iso_match.group(2)),
                int(iso_match.group(3)),
            )

        numeric_match = cls.URL_NUMERIC_DATE_PATTERN.search(path)
        if numeric_match:
            return cls._safe_utc_date(
                int(numeric_match.group(1)),
                int(numeric_match.group(2)),
                int(numeric_match.group(3) or 1),
            )
        return None

    @staticmethod
    def _month_number(value: str) -> int | None:
        for date_format in ("%B", "%b"):
            try:
                return datetime.strptime(value, date_format).month
            except ValueError:
                continue
        return None

    @classmethod
    def _safe_utc_date(
        cls,
        year: int,
        month: int,
        day: int,
    ) -> datetime | None:
        if not cls._is_plausible_publication_year(year):
            return None
        try:
            return datetime(year, month, day, tzinfo=timezone.utc)
        except ValueError:
            return None

    def _recency_rejection_reason(
        self,
        published_at: datetime | None,
    ) -> str:
        if published_at is None:
            return ""

        now = datetime.now(timezone.utc)
        if published_at > now + timedelta(hours=24):
            return "story-date-in-future"
        if published_at < now - timedelta(days=7):
            return "story-older-than-seven-days"
        return ""

    def _max_age_days(self) -> int:
        return 7

    def _log_recency_rejection(
        self,
        *,
        url: str,
        published_at: datetime | None,
        reason: str,
    ) -> None:
        LOGGER.debug(
            "candidate URL=%s parsed publication date=%s "
            "rejected reason=%s",
            url,
            published_at.isoformat() if published_at else "missing",
            reason,
        )

    def _extract_image(self, card: Tag, base_url: str) -> str:
        selectors = (
            self.definition.image_selectors
            or list(self.DEFAULT_IMAGE_SELECTORS)
        )

        for selector in selectors:
            node = card.select_one(selector)
            if not isinstance(node, Tag):
                continue

            candidate = ""
            for attribute in (
                "src",
                "data-src",
                "data-lazy-src",
                "data-original",
            ):
                candidate = str(node.get(attribute) or "").strip()
                if candidate:
                    break

            if not candidate:
                srcset = str(node.get("srcset") or "").strip()
                if srcset:
                    candidate = srcset.split(",")[-1].strip().split()[0]

            if not candidate or candidate.startswith("data:"):
                continue

            image_url = urljoin(base_url, candidate)
            lowered = image_url.casefold()
            if (
                not is_still_image_url(image_url)
                or any(part in lowered for part in ("emoji", "avatar", "logo"))
            ):
                continue

            return image_url

        return ""

    def _url_is_allowed(self, url: str, base_url: str) -> bool:
        if not url:
            return False

        lowered = url.casefold()
        if any(
            self._url_contains_part(lowered, part)
            for part in self.DEFAULT_EXCLUDED_URL_PARTS
        ):
            return False

        path = urlparse(url).path.casefold().rstrip("/")
        if any(path.endswith(ending) for ending in self.EXCLUDED_URL_ENDINGS):
            return False

        if self.definition.same_domain_only:
            base_host = self._hostname(base_url)
            host = self._hostname(url)
            if host and host != base_host:
                return False

        if self._matches_patterns(url, self.definition.exclude_url_patterns):
            return False

        if self.definition.include_url_patterns and not self._matches_patterns(
            url,
            self.definition.include_url_patterns,
        ):
            return False

        return True

    def _score_candidate(
        self,
        *,
        url: str,
        title: str,
        published: str,
        image_url: str,
        card: Tag,
    ) -> tuple[int, list[str]]:
        score, reasons = self._url_score_details(url)

        signals = (
            (bool(published), 30, "publication date"),
            (20 <= len(title) <= 120, 25, "title length"),
            (bool(image_url), 20, "article image"),
            (self._has_article_body_schema(card), 20, "article body schema"),
            (self._has_card_json_ld_article(card), 15, "JSON-LD Article"),
            (self._has_card_open_graph_article(card), 15, "OpenGraph article"),
            (
                any(
                    self._clean_text(node.get_text(" ", strip=True))
                    for node in card.find_all("p")
                ),
                10,
                "paragraph text",
            ),
        )
        for present, points, label in signals:
            if present:
                score += points
                reasons.append(f"{label} +{points}")

        return score, reasons

    def _url_score(self, url: str) -> int:
        score, _ = self._url_score_details(url)
        return score

    def _url_score_details(self, url: str) -> tuple[int, list[str]]:
        lowered = url.casefold()
        preferred = any(
            part in lowered for part in self.PREFERRED_ARTICLE_URL_PARTS
        ) or self._has_article_year_path(url)
        score = 40 if preferred else 0
        reasons = ["article URL +40"] if preferred else []
        for term, penalty in self.NEGATIVE_URL_SCORES:
            if self._url_contains_term(lowered, term):
                score += penalty
                reasons.append(f"{term} {penalty}")
        return score, reasons

    @classmethod
    def _has_article_year_path(cls, url: str) -> bool:
        current_year = datetime.now(timezone.utc).year
        path = urlparse(url).path
        return any(
            2000 <= int(match.group(1)) <= current_year + 1
            for match in cls.ARTICLE_YEAR_PATH_PATTERN.finditer(path)
        )

    @staticmethod
    def _url_contains_term(url: str, term: str) -> bool:
        return bool(
            re.search(
                rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])",
                url,
                flags=re.IGNORECASE,
            )
        )

    @classmethod
    def _url_contains_part(cls, url: str, part: str) -> bool:
        if part.startswith("/"):
            return bool(
                re.search(
                    rf"{re.escape(part)}(?![a-z0-9])",
                    url,
                    flags=re.IGNORECASE,
                )
            )
        return part.casefold() in url.casefold()

    @staticmethod
    def _hostname(url: str) -> str:
        return urlparse(url).netloc.casefold().removeprefix("www.")

    @staticmethod
    def _has_article_body_schema(card: Tag) -> bool:
        return bool(
            card.get("itemprop") == "articleBody"
            or "Article" in str(card.get("itemtype", ""))
            or card.select_one("[itemprop='articleBody']")
            or card.select_one("[itemtype*='Article']")
        )

    @classmethod
    def _has_card_json_ld_article(cls, card: Tag) -> bool:
        for node in card.select("script[type='application/ld+json']"):
            if re.search(r'"@type"\s*:\s*"(?:News)?Article"', node.get_text(), re.I):
                return True
        return False

    @staticmethod
    def _has_card_open_graph_article(card: Tag) -> bool:
        node = card.select_one("meta[property='og:type']")
        return bool(node and str(node.get("content", "")).casefold() == "article")

    @classmethod
    def _duplicate_keys(cls, story: Story) -> set[str]:
        normalised_url = cls._normalise_url(story.url).casefold().rstrip("/")
        parsed = urlparse(normalised_url)
        queryless_url = urlunparse(
            (parsed.scheme, parsed.netloc, parsed.path, "", "", "")
        ).rstrip("/")
        slug = parsed.path.rstrip("/").rsplit("/", 1)[-1]
        title = cls._normalise_text(story.title)

        return {
            key
            for key in (
                f"title:{title}" if title else "",
                f"normalised_url:{normalised_url}" if normalised_url else "",
                f"slug:{slug}" if slug else "",
                f"queryless:{queryless_url}" if queryless_url else "",
            )
            if key
        }

    def _title_is_allowed(self, title: str) -> bool:
        title = self._clean_text(title)
        if not title or len(title) < 8 or len(title.split()) < 2:
            return False

        lowered = title.casefold().strip(" .:-–—")
        if lowered in self.DEFAULT_EXCLUDED_TITLES:
            return False

        if self._matches_patterns(title, self.definition.exclude_title_patterns):
            return False

        return True

    @staticmethod
    def _matches(node: Tag, selector: str) -> bool:
        try:
            return bool(soupsieve.match(selector, node))
        except Exception:
            return False

    @staticmethod
    def _matches_patterns(value: str, patterns: list[str]) -> bool:
        for pattern in patterns:
            try:
                if re.search(pattern, value, flags=re.IGNORECASE):
                    return True
            except re.error:
                if pattern.casefold() in value.casefold():
                    return True
        return False

    @staticmethod
    def _normalise_url(url: str) -> str:
        parsed = urlparse(url.strip())
        if parsed.scheme not in {"http", "https"}:
            return ""
        return urlunparse(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path or "/",
                "",
                parsed.query,
                "",
            )
        )

    @classmethod
    def _slugify(cls, value: Any) -> str:
        slug = cls._normalise_ascii(value, "-")
        return slug.strip("-")[:100] or "story"

    @staticmethod
    def _clean_text(value: Any) -> str:
        return " ".join(str(value or "").split()).strip()

    @classmethod
    def _normalise_text(cls, value: Any) -> str:
        return cls._normalise_ascii(value, " ").strip()

    @classmethod
    def _normalise_ascii(cls, value: Any, separator: str) -> str:
        return re.sub(
            r"[^a-z0-9]+",
            separator,
            cls._clean_text(value).casefold(),
        )

    @classmethod
    def _merge_unique(cls, values: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            cleaned = cls._clean_text(value)
            key = cleaned.casefold()
            if cleaned and key not in seen:
                seen.add(key)
                result.append(cleaned)
        return result


__all__ = ["GenericWebsiteScraper"]
