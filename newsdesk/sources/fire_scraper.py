"""Lincolnshire Fire and Rescue news scraper.

This module owns Lincolnshire County Council Fire and Rescue navigation,
classification, location detection and Story construction. Generic article
HTML extraction is delegated to :class:`ArticleScraper`.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import logging
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag
import requests

from newsdesk.sources.article_scraper import ArticleScraper
from newsdesk.sources.base_scraper import BaseScraper, ScrapeResponse
from newsdesk.geography import story_matches_lincolnshire
from newsdesk.story import Story


LOGGER = logging.getLogger(__name__)
DEFAULT_MAX_AGE_DAYS = 14
FUTURE_ALLOWANCE_HOURS = 24
MAX_LISTING_PAGES = 6


@dataclass(frozen=True, slots=True)
class _FireListingCandidate:
    url: str
    title: str
    published: datetime | None
    raw_published: str


def _parse_fire_publication_datetime(value: object) -> datetime | None:
    """Parse supported Fire publication values as UTC."""

    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, datetime.min.time())
    else:
        raw = str(value).strip()
        if not raw:
            return None
        raw = re.sub(
            r"^(?:posted\s+on|published)\s*:?\s*",
            "",
            raw,
            flags=re.IGNORECASE,
        )
        raw = re.sub(r"(?<=\d)(?:st|nd|rd|th)\b", "", raw, flags=re.IGNORECASE)
        parsed = None
        for part in (item.strip() for item in re.split(r"\s*[•|]\s*", raw)):
            if not part:
                continue
            iso_value = part[:-1] + "+00:00" if part.endswith(("Z", "z")) else part
            try:
                parsed = datetime.fromisoformat(iso_value)
            except ValueError:
                parsed = None
            if parsed is None:
                for date_format in (
                    "%d %B %Y",
                    "%d %b %Y",
                    "%H:%M %d %B %Y",
                    "%H:%M %d %b %Y",
                    "%d/%m/%Y",
                    "%d/%m/%Y %H:%M",
                    "%a %d %b %Y %H:%M",
                    "%a %d %B %Y %H:%M",
                ):
                    try:
                        parsed = datetime.strptime(part, date_format)
                        break
                    except ValueError:
                        continue
            if parsed is None:
                try:
                    parsed = parsedate_to_datetime(part)
                except (TypeError, ValueError, OverflowError):
                    parsed = None
            if parsed is not None:
                break
        if parsed is None:
            return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _fire_recency_rejection_reason(
    value: object,
    *,
    now: datetime | None = None,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
) -> tuple[datetime | None, str | None]:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)
    parsed = _parse_fire_publication_datetime(value)
    if parsed is None:
        reason = "missing-publication-date" if not str(value or "").strip() else "invalid-publication-date"
        return None, reason
    if parsed < current - timedelta(days=max_age_days):
        return parsed, "story-too-old"
    if parsed > current + timedelta(hours=FUTURE_ALLOWANCE_HOURS):
        return parsed, "story-date-in-future"
    return parsed, None


class FireScraper(BaseScraper):
    BASE_URL = "https://www.lincolnshire.gov.uk"
    NEWS_URL = f"{BASE_URL}/news"
    DEFAULT_LIMIT = 20

    ARTICLE_BODY_SELECTOR = "main, article"
    ARTICLE_IMAGE_SELECTOR = (
        "figure img[src], .wp-post-image[src], .news img[src], "
        "main img[src], article img[src]"
    )

    def __init__(
        self,
        *,
        limit: int = DEFAULT_LIMIT,
        timeout: float = 30.0,
        request_delay: float = 0.35,
    ) -> None:
        if limit <= 0:
            raise ValueError("limit must be greater than zero.")

        super().__init__(
            source_name="Lincolnshire Fire and Rescue",
            source_url=self.NEWS_URL,
            timeout=timeout,
            request_delay=request_delay,
        )

        self.limit = int(limit)
        self.article_scraper = ArticleScraper(
            timeout=self.timeout,
            headers=self._build_headers(),
        )
        self._last_collection_diagnostics: dict[str, object] = {}

    def close(self) -> None:
        """Compatibility method; this scraper does not keep a browser open."""

    def parse(self, response: ScrapeResponse) -> Iterable[Story]:
        candidates, diagnostics = self._discover_recent_candidates(response)
        stories: list[Story] = []

        for candidate in candidates[: self.limit]:
            try:
                story = self._parse_article_url(candidate.url)

                if (
                    story.title
                    and (story.body or story.summary)
                    and self._is_fire_content(story)
                ):
                    if (
                        _parse_fire_publication_datetime(story.published) is None
                        and candidate.published is not None
                    ):
                        article_time = str(story.published or "").strip()
                        story.published = " • ".join(
                            value
                            for value in (candidate.raw_published, article_time)
                            if value
                        )
                    parsed, reason = _fire_recency_rejection_reason(story.published)
                    if reason is None:
                        stories.append(story)
                    else:
                        diagnostics["article_date_rejections"] += 1
                        LOGGER.debug(
                            "Rejecting Fire story title=%r url=%s raw_date=%r "
                            "parsed_date=%s reason=%s",
                            story.title,
                            candidate.url,
                            story.published,
                            parsed,
                            reason,
                        )
            except Exception:
                # One malformed release must not prevent the remaining
                # releases loading.
                LOGGER.exception("Could not collect Fire article %s.", candidate.url)
                continue

        diagnostics["stories_retained"] = len(stories)
        self._last_collection_diagnostics = diagnostics
        LOGGER.info(
            "Fire recency collection: visited %s pages, discovered %s unique "
            "links, retained %s stories from the last 14 days.",
            diagnostics["pages_visited"],
            diagnostics["unique_links_discovered"],
            len(stories),
        )
        return stories

    @staticmethod
    def _is_fire_content(story: Story) -> bool:
        """Exclude unrelated county-council news from the shared news index."""

        text = " ".join(
            str(value or "")
            for value in (story.title, story.summary, story.body, story.category)
        ).casefold()
        return any(
            term in text
            for term in (
                "fire and rescue", "fire service", "firefighter", "fire crew",
                "fire engine", "fire station", "fire safety", "smoke alarm",
                "wildfire", "house fire", "building fire", "shed fire",
                "vehicle fire", "caravan fire", "blaze", "arson",
            )
        )

    def _discover_recent_candidates(
        self,
        first_response: ScrapeResponse,
    ) -> tuple[list[_FireListingCandidate], dict[str, object]]:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=DEFAULT_MAX_AGE_DAYS)
        candidates: list[_FireListingCandidate] = []
        seen_urls: set[str] = set()
        visited_pages: set[str] = set()
        ordering_trusted = True
        response = first_response
        diagnostics: dict[str, object] = {
            "pages_visited": 0,
            "unique_links_discovered": 0,
            "listing_old_rejections": 0,
            "listing_future_rejections": 0,
            "article_date_rejections": 0,
            "stories_retained": 0,
            "stop_reason": "",
        }

        for page_number in range(1, MAX_LISTING_PAGES + 1):
            page_url = self._normalise_url(response.url)
            if page_url.casefold() in visited_pages:
                diagnostics["stop_reason"] = "pagination-loop"
                break
            visited_pages.add(page_url.casefold())
            diagnostics["pages_visited"] = page_number

            page_candidates = self._extract_listing_candidates(response.body, page_url)
            new_candidates: list[_FireListingCandidate] = []
            for candidate in page_candidates:
                key = self._query_free_url(candidate.url).casefold().rstrip("/")
                if key in seen_urls:
                    continue
                seen_urls.add(key)
                new_candidates.append(candidate)

            dated = [candidate.published for candidate in page_candidates if candidate.published]
            current_count = 0
            old_count = 0
            for candidate in new_candidates:
                if candidate.published is None:
                    candidates.append(candidate)
                    continue
                _, reason = _fire_recency_rejection_reason(candidate.published, now=now)
                if reason == "story-too-old":
                    diagnostics["listing_old_rejections"] += 1
                    old_count += 1
                elif reason == "story-date-in-future":
                    diagnostics["listing_future_rejections"] += 1
                elif reason is None:
                    candidates.append(candidate)
                    current_count += 1

            diagnostics["unique_links_discovered"] = len(seen_urls)
            newest = max(dated) if dated else None
            oldest = min(dated) if dated else None
            LOGGER.debug(
                "Fire listing page=%s url=%s links=%s new_unique=%s newest=%s "
                "oldest=%s current=%s rejected_old=%s",
                page_number,
                page_url,
                len(page_candidates),
                len(new_candidates),
                newest,
                oldest,
                current_count,
                old_count,
            )

            all_dated = bool(page_candidates) and len(dated) == len(page_candidates)
            ordered = all(
                dated[index] >= dated[index + 1]
                for index in range(len(dated) - 1)
            )
            ordering_trusted = ordering_trusted and all_dated and ordered
            if ordering_trusted and newest is not None and newest < cutoff:
                diagnostics["stop_reason"] = "ordered-page-entirely-older-than-cutoff"
                break

            next_url = self._extract_next_listing_url(response.body, page_url)
            if not next_url:
                diagnostics["stop_reason"] = "no-next-page"
                break
            if page_number >= MAX_LISTING_PAGES:
                diagnostics["stop_reason"] = "maximum-page-safety-limit"
                break
            response = self.fetch(next_url)

        LOGGER.debug("Fire pagination stopped: %s", diagnostics["stop_reason"])
        return candidates, diagnostics

    def _extract_listing_candidates(
        self,
        html: str,
        page_url: str,
    ) -> list[_FireListingCandidate]:
        soup = BeautifulSoup(html, "html.parser")
        candidates: list[_FireListingCandidate] = []
        cards = soup.select(
            "li.searchList, article, .news-item, .listing-item, "
            ".search-result, main li"
        )
        for card in cards:
            anchor = card.select_one("a[href]")
            if anchor is None:
                continue
            url = self._normalise_url(urljoin(page_url, str(anchor.get("href") or "")))
            if not self._is_article_url(url):
                continue
            text = card.get_text(" ", strip=True)
            if not self._looks_like_fire_listing(
                f"{anchor.get_text(' ', strip=True)} {text}"
            ):
                continue
            match = re.search(
                r"\b(?:Posted\s+on|Published)\s*:?\s*"
                r"(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\s+\d{4})",
                text,
                flags=re.IGNORECASE,
            )
            raw_published = match.group(1) if match else ""
            candidates.append(
                _FireListingCandidate(
                    url=url,
                    title=self._clean(anchor.get_text(" ", strip=True)),
                    published=_parse_fire_publication_datetime(raw_published),
                    raw_published=raw_published,
                )
            )
        return candidates

    @staticmethod
    def _looks_like_fire_listing(text: str) -> bool:
        lowered = str(text or "").casefold()
        return any(
            term in lowered
            for term in (
                "fire and rescue", "fire service", "firefighter", "fire crew",
                "fire engine", "fire station", "fire safety", "smoke alarm",
                "wildfire", "house fire", "building fire", "shed fire",
                "vehicle fire", "caravan fire", "blaze", "arson",
            )
        )

    def _extract_next_listing_url(self, html: str, page_url: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        for anchor in soup.find_all("a", href=True):
            label = " ".join(
                (
                    anchor.get_text(" ", strip=True),
                    str(anchor.get("aria-label") or ""),
                    str(anchor.get("title") or ""),
                )
            ).casefold()
            rel = {str(value).casefold() for value in (anchor.get("rel") or [])}
            if "next" in rel or label.strip() in {"next", "next page"}:
                return self._normalise_url(urljoin(page_url, str(anchor.get("href") or "")))
        return ""

    def _normalise_url(self, value: str) -> str:
        parsed = urlparse(urljoin(self.BASE_URL, str(value or "").strip()))
        return parsed._replace(fragment="").geturl()

    def _is_article_url(self, value: str) -> bool:
        parsed = urlparse(value)
        path = parsed.path.rstrip("/") + "/"
        return (
            parsed.netloc.casefold()
            in {"www.lincolnshire.gov.uk", "lincolnshire.gov.uk"}
            and path.startswith("/news/article/")
        )

    @staticmethod
    def _query_free_url(value: str) -> str:
        parsed = urlparse(value)
        return parsed._replace(query="", fragment="").geturl()

    def fetch_latest_news(self, limit: int | None = None) -> list[Story]:
        original = self.limit

        if limit is not None:
            if limit <= 0:
                raise ValueError("limit must be greater than zero.")

            self.limit = int(limit)

        try:
            return self.get_stories(refresh=True, deduplicate=True)
        finally:
            self.limit = original

    def _extract_listing_links(self, html: str, page_url: str) -> list[str]:
        soup = BeautifulSoup(html, "html.parser")
        links: list[str] = []

        for anchor in soup.select("a[href]"):
            href = str(anchor.get("href", "")).strip()
            absolute = urljoin(page_url, href)
            parsed = urlparse(absolute)
            path = parsed.path.rstrip("/") + "/"

            if parsed.netloc not in {
                "www.lincolnshire.gov.uk",
                "lincolnshire.gov.uk",
            }:
                continue

            if not path.startswith("/news/article/"):
                continue

            if any(
                part in path
                for part in (
                    "/page/",
                    "/category/",
                    "/tag/",
                    "/media-enquiries/",
                )
            ):
                continue

            if absolute not in links:
                links.append(absolute)

        return links

    def _parse_article_url(self, article_url: str) -> Story:
        article = self.article_scraper.extract_article(
            article_url,
            body_selector=self.ARTICLE_BODY_SELECTOR,
            image_selector=self.ARTICLE_IMAGE_SELECTOR,
        )

        soup = article["soup"]
        main = soup.select_one("main") or soup.select_one("article") or soup

        return self._build_story(
            soup=soup,
            main=main,
            article_url=str(article.get("url") or article_url),
            extracted_text=str(article.get("text") or ""),
            extracted_image=str(article.get("image") or ""),
        )

    def _parse_article(self, response: ScrapeResponse) -> Story:
        """Parse a pre-fetched article response.

        This compatibility method preserves the existing callable API while
        using the same Story-building path as ArticleScraper-backed requests.
        """

        soup = BeautifulSoup(response.body, "html.parser")
        main = soup.select_one("main") or soup.select_one("article") or soup

        extracted_text = "\n\n".join(
            node.get_text(" ", strip=True)
            for node in main.find_all(["p", "li"])
        ).strip()

        extracted_image = ""
        image = soup.select_one(self.ARTICLE_IMAGE_SELECTOR)

        if image is not None:
            src = str(image.get("data-src") or image.get("src") or "").strip()

            if src and not src.startswith("data:"):
                extracted_image = urljoin(response.url, src)

        return self._build_story(
            soup=soup,
            main=main,
            article_url=response.url,
            extracted_text=extracted_text,
            extracted_image=extracted_image,
        )

    def _build_story(
        self,
        *,
        soup: BeautifulSoup,
        main: Tag | BeautifulSoup,
        article_url: str,
        extracted_text: str,
        extracted_image: str,
    ) -> Story:
        title = self._first_text(soup, ("main h1", "article h1", "h1"))
        published = self._published(soup)
        parsed_published = _parse_fire_publication_datetime(published)
        if parsed_published is not None:
            # Store one canonical value.  The Fire UI and Social Desk both
            # understand ISO dates; ordinal display text such as "25th
            # August" was previously shown as "Date unavailable".
            published = parsed_published.isoformat()

        paragraphs = [
            self._clean(part)
            for part in extracted_text.split("\n")
            if self._clean(part)
        ]
        paragraphs = [
            paragraph
            for paragraph in paragraphs
            if len(paragraph) >= 20 and not self._blocked(paragraph)
        ]
        paragraphs = list(dict.fromkeys(paragraphs))

        summary = paragraphs[0] if paragraphs else ""
        body = "\n\n".join(paragraphs)

        image_url, caption, alt = self._image(main, article_url)

        if not image_url:
            image_url = extracted_image

        category = self._category(f"{title} {summary} {body}")
        location = self._location(f"{title} {summary} {body}")
        now = datetime.now(timezone.utc).isoformat()

        story = Story(
            title=title,
            summary=summary,
            body=body,
            source="Lincolnshire Fire and Rescue",
            url=article_url,
            published=published,
            location=location,
            category=category,
            image_url=image_url,
            image_caption=caption,
            image_credit=(
                "Lincolnshire County Council / Lincolnshire Fire and Rescue"
                if image_url
                else ""
            ),
            image_alt_text=alt,
            scraped_at=now,
            tags=["Fire and Rescue", category]
            + ([location] if location else []),
        )

        story.extras.update(
            {
                "source_module": "fire",
                "image_source_url": image_url,
                "image_credit_required": bool(image_url),
                "image_download_status": "not_downloaded",
            }
        )

        return story

    def _image(
        self,
        main: Tag | BeautifulSoup,
        page_url: str,
    ) -> tuple[str, str, str]:
        selectors = (
            "figure img[src]",
            ".wp-post-image[src]",
            ".news img[src]",
            "main img[src]",
            "article img[src]",
        )

        for selector in selectors:
            image = main.select_one(selector)

            if image is None:
                continue

            src = str(
                image.get("data-src")
                or image.get("src")
                or ""
            ).strip()

            if not src or src.startswith("data:"):
                continue

            url = urljoin(page_url, src)
            alt = self._clean(str(image.get("alt") or ""))
            figure = image.find_parent("figure")
            caption = ""

            if figure:
                caption_node = figure.select_one("figcaption")

                if caption_node:
                    caption = self._clean(
                        caption_node.get_text(" ", strip=True)
                    )

            return url, caption, alt

        meta = main.find_previous("meta", attrs={"property": "og:image"})

        if meta and meta.get("content"):
            return urljoin(page_url, str(meta["content"])), "", ""

        return "", "", ""

    @staticmethod
    def _first_text(
        soup: BeautifulSoup,
        selectors: tuple[str, ...],
    ) -> str:
        for selector in selectors:
            node = soup.select_one(selector)

            if node:
                text = FireScraper._clean(
                    node.get_text(" ", strip=True)
                )

                if text:
                    return text

        return ""

    @staticmethod
    def _published(soup: BeautifulSoup) -> str:
        time_node = soup.select_one("time[datetime]")

        time_value = ""
        if time_node:
            time_value = str(
                time_node.get("datetime")
                or time_node.get_text(" ", strip=True)
                or ""
            ).strip()

        text = soup.get_text(" ", strip=True)        
        match = re.search(
            r"(?:Posted on|Published)\s*:?\s*"
            r"(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\s+\d{4})",
            text,
            re.IGNORECASE,
        )

        date_value = match.group(1) if match else ""

        return " • ".join(
            value
            for value in (
                date_value,
                time_value,
        )
        if value
        )

    

    @staticmethod
    def _blocked(text: str) -> bool:
        lowered = text.casefold()

        return lowered.startswith(
            (
                "share this",
                "cookie",
                "privacy",
                "for general enquiries",
                "in an emergency call",
            )
        )

    @staticmethod
    def _clean(value: str) -> str:
        return re.sub(
            r"\s+",
            " ",
            str(value or "").replace("\xa0", " "),
        ).strip()

    @staticmethod
    def _category(text: str) -> str:
        lowered = text.casefold()
        rules = (
            (
                "Major Incident",
                (
                    "major incident",
                    "large fire",
                    "blaze",
                    "multiple fire engines",
                ),
            ),
            (
                "Road Traffic Collision",
                ("road traffic collision", "rtc", "collision"),
            ),
            (
                "Fire Safety",
                ("fire safety", "smoke alarm", "safety advice", "warning"),
            ),
            (
                "Water Safety",
                ("water safety", "open water", "drowning"),
            ),
            (
                "Incident",
                ("firefighters attended", "crews attended", "incident"),
            ),
            (
                "Community",
                ("cadets", "open day", "community", "charity"),
            ),
            (
                "Service News",
                (
                    "firefighter",
                    "fire station",
                    "command support",
                    "training",
                ),
            ),
        )

        for category, terms in rules:
            if any(term in lowered for term in terms):
                return category

        return "Fire and Rescue"

    @staticmethod
    def _location(text: str) -> str:
        places = (
            "Lincolnshire", "Lincoln", "Boston", "Grantham", "Spalding",
            "Skegness", "Gainsborough", "Sleaford", "Stamford", "Louth",
            "Horncastle", "Bourne", "Market Rasen", "Mablethorpe", "Alford",
            "Holbeach", "Long Sutton", "Woodhall Spa", "North Hykeham",
            "South Kesteven", "North Kesteven", "East Lindsey", "West Lindsey",
            "South Holland", "Cleethorpes", "Grimsby", "Scunthorpe",
            "Immingham", "Barton-upon-Humber", "Brigg",
        )
        lowered = text.casefold()

        for place in places:
            if place.casefold() in lowered:
                return place

        return ""


class HumbersideFireIncidentScraper(BaseScraper):
    """Collect individual northern-Lincolnshire incidents from the live log."""

    NEWS_URL = "https://humbersidefire.gov.uk/newsroom/latest-incidents"

    def __init__(self, *, timeout: float = 30.0, request_delay: float = 0.35) -> None:
        super().__init__(
            source_name="Humberside Fire and Rescue Service",
            source_url=self.NEWS_URL,
            timeout=timeout,
            request_delay=request_delay,
        )

    def close(self) -> None:
        """Compatibility method; this scraper does not keep a browser open."""

    def fetch_latest_news(self) -> list[Story]:
        return self.get_stories(refresh=True, deduplicate=True)

    def fetch(self, url: str | None = None) -> ScrapeResponse:
        """Fetch the live log with browser-compatible HTTP handling.

        The Humberside site can return different content to urllib on
        Windows.  Requests also handles compressed responses consistently.
        """

        target = str(url or self.NEWS_URL)
        headers = self._build_headers()
        headers.update(
            {
                "Accept": (
                    "text/html,application/xhtml+xml,application/xml;q=0.9,"
                    "image/avif,image/webp,*/*;q=0.8"
                ),
                "Accept-Language": "en-GB,en;q=0.9",
                "Cache-Control": "no-cache",
                "Referer": "https://humbersidefire.gov.uk/newsroom",
            }
        )
        response = requests.get(
            target,
            headers=headers,
            timeout=self.timeout,
            allow_redirects=True,
        )
        response.raise_for_status()
        return ScrapeResponse(
            url=str(response.url),
            body=response.text,
            status_code=int(response.status_code),
            content_type=str(response.headers.get("Content-Type", "")),
            encoding=str(response.encoding or "utf-8"),
            headers={str(key): str(value) for key, value in response.headers.items()},
        )

    def parse(self, response: ScrapeResponse) -> Iterable[Story]:
        soup = BeautifulSoup(response.body, "html.parser")
        main = soup.select_one("main") or soup
        stories: list[Story] = []
        now = datetime.now(timezone.utc)

        for heading in main.find_all("h3"):
            title = FireScraper._clean(heading.get_text(" ", strip=True))
            if not title:
                continue
            parts: list[str] = []
            node = heading.find_next_sibling()
            while node is not None and getattr(node, "name", "") != "h3":
                text = FireScraper._clean(node.get_text(" ", strip=True))
                if text:
                    parts.append(text)
                node = node.find_next_sibling()
            combined = "\n\n".join(parts)
            date_match = re.search(
                r"Date\s*&\s*Time:\s*([^\n(]+?)"
                r"\s*\(No:\s*([^)]+)\)",
                combined,
                flags=re.IGNORECASE,
            )
            if date_match is None:
                continue
            raw_date = date_match.group(1).strip()
            incident_number = (date_match.group(2) or "").strip()
            parsed_date = _parse_fire_publication_datetime(raw_date)
            _, rejection = _fire_recency_rejection_reason(parsed_date, now=now)
            if rejection is not None:
                continue

            description = combined.split("Date & Time:", 1)[0].strip()
            type_match = re.search(r"Incident Type:\s*([^\n]+)", combined, re.I)
            incident_type = FireScraper._clean(type_match.group(1)) if type_match else "Incident"
            story = Story(
                title=title,
                summary=description,
                body="\n\n".join(
                    value for value in (
                        description,
                        f"Date and time: {raw_date}",
                        f"Incident number: {incident_number}" if incident_number else "",
                        f"Incident type: {incident_type}",
                    ) if value
                ),
                source="Humberside Fire and Rescue Service",
                url=(
                    f"{self.NEWS_URL}#incident-{incident_number}"
                    if incident_number else self.NEWS_URL
                ),
                published=parsed_date.isoformat() if parsed_date else raw_date,
                location=title.rstrip(". "),
                category="Incident",
                image_credit="Humberside Fire and Rescue Service",
                scraped_at=now.isoformat(),
                tags=["Fire and Rescue", "Incident", incident_type],
            )
            match = story_matches_lincolnshire(story)
            if not match.matched:
                continue
            story.extras.update(
                {
                    "source_module": "fire",
                    "source_key": "humberside_fire_incidents_lincolnshire",
                    "incident_number": incident_number,
                    "incident_type": incident_type,
                    "geographic_filter": "lincolnshire",
                    "geographic_matches": list(match.places),
                }
            )
            stories.append(story)
        return stories


__all__ = ["FireScraper", "HumbersideFireIncidentScraper"]
