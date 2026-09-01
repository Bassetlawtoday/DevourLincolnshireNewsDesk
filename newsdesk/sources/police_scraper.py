"""
newsdesk.sources.police_scraper

Lincolnshire Police news collector for Devour Lincolnshire NewsDesk.

The scraper:

- reads the official Lincolnshire Police RSS feed when available;
- falls back to the paginated official News Search rather than the
  seven-item Latest panel;
- collects the latest article links;
- visits each article;
- extracts its title, publication date, summary and main article text;
- returns shared NewsDesk Story objects;
- leaves editorial scoring and formatting to StoryEngine.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import logging
import re
import time
from urllib.parse import urljoin, urlparse
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup, Tag
from selenium import webdriver
from selenium.common.exceptions import (
    NoSuchWindowException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support.ui import WebDriverWait

from newsdesk.sources.base_scraper import (
    BaseScraper,
    ScrapeResponse,
    ScraperParseError,
    ScraperRequestError,
)
from newsdesk.story import Story


LOGGER = logging.getLogger(__name__)

DEFAULT_MAX_AGE_DAYS = 14
MAX_LISTING_PAGES = 20
FUTURE_ALLOWANCE_HOURS = 24


@dataclass(frozen=True, slots=True)
class _ListingCandidate:
    url: str
    title: str
    published: datetime | None
    raw_published: str


def _parse_police_publication_datetime(value: object) -> datetime | None:
    """Parse supported Police publication values as timezone-aware UTC."""

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
        raw = re.sub(r"^published\s*:\s*", "", raw, flags=re.IGNORECASE)
        iso_value = raw[:-1] + "+00:00" if raw.endswith(("Z", "z")) else raw
        try:
            parsed = datetime.fromisoformat(iso_value)
        except ValueError:
            parsed = None
        if parsed is None:
            for date_format in (
                "%H:%M %d/%m/%Y",
                "%d/%m/%Y %H:%M",
                "%d/%m/%Y %H:%M:%S",
                "%d/%m/%Y",
                "%H:%M %d %B %Y",
                "%H:%M %d %b %Y",
                "%d %B %Y %H:%M",
                "%d %b %Y %H:%M",
                "%d %B %Y",
                "%d %b %Y",
            ):
                try:
                    parsed = datetime.strptime(raw, date_format)
                    break
                except ValueError:
                    continue
        if parsed is None:
            try:
                parsed = parsedate_to_datetime(raw)
            except (TypeError, ValueError, OverflowError):
                return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _police_recency_rejection_reason(
    value: object,
    *,
    now: datetime | None = None,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
) -> tuple[datetime | None, str | None]:
    """Return the parsed date and a rejection reason, if any."""

    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)
    parsed = _parse_police_publication_datetime(value)
    if parsed is None:
        reason = "missing-publication-date" if not str(value or "").strip() else "invalid-publication-date"
        return None, reason
    if parsed < current - timedelta(days=max_age_days):
        return parsed, "story-too-old"
    if parsed > current + timedelta(hours=FUTURE_ALLOWANCE_HOURS):
        return parsed, "story-date-in-future"
    return parsed, None


class PoliceScraper(BaseScraper):
    """
    Collect the latest Lincolnshire Police news releases.

    A browser is created lazily when the first collection begins and is closed
    after each run unless ``keep_browser_open`` is enabled.
    """

    BASE_URL = "https://www.lincs.police.uk"
    NEWS_URL = f"{BASE_URL}/news/lincolnshire/news/"
    NEWS_SEARCH_URL = f"{BASE_URL}/news/news-search/?ct=News"
    RSS_URL = f"{NEWS_URL}GetNewsRss/"

    DEFAULT_LIMIT = 20
    DEFAULT_WAIT_SECONDS = 20.0
    DEFAULT_PAGE_DELAY = 1.25
    DEFAULT_MAX_ATTEMPTS = 3

    ARTICLE_PATH_MARKER = "/news/lincolnshire/news/"

    RATE_LIMIT_TERMS = (
        "too many requests",
        "error 429",
        "http 429",
        "rate limit exceeded",
    )

    BLOCKED_PARAGRAPH_PREFIXES = (
        "share this page",
        "is there a problem with this page",
        "please report any comments",
        "contact us",
        "copyright",
        "privacy notice",
        "accessibility statement",
    )

    CONTENT_SELECTORS = (
        "main article",
        "article",
        ".article-content",
        ".article__content",
        ".content-page",
        ".content",
        "main",
    )

    TITLE_SELECTORS = (
        "main h1",
        "article h1",
        "h1",
    )

    DATE_SELECTORS = (
        "time[datetime]",
        "main time",
        "article time",
        ".published-date",
        ".published",
        ".date",
    )

    SUMMARY_SELECTORS = (
        "main .lead",
        "article .lead",
        ".article-intro",
        ".article__intro",
        ".intro",
        ".standfirst",
        "main h1 + p",
    )

    IMAGE_META_SELECTORS = (
        'meta[property="og:image:secure_url"]',
        'meta[property="og:image"]',
        'meta[name="twitter:image"]',
        'meta[name="twitter:image:src"]',
        'link[rel="image_src"]',
    )

    IMAGE_SELECTORS = (
        "main article figure img",
        "article figure img",
        "main .image img",
        "main .media img",
        ".article-image img",
        ".article__image img",
        ".hero img",
        ".hero-image img",
        "main article img",
        "article img",
        "main img",
    )

    IMAGE_SOURCE_ATTRIBUTES = (
        "src",
        "data-src",
        "data-lazy-src",
        "data-original",
        "data-image",
    )

    REJECTED_IMAGE_TERMS = (
        "logo",
        "icon",
        "avatar",
        "sprite",
        "favicon",
        "placeholder",
        "tracking",
        "pixel",
        "cookie",
    )

    def __init__(
        self,
        *,
        limit: int = DEFAULT_LIMIT,
        headless: bool = True,
        browser_wait: float = DEFAULT_WAIT_SECONDS,
        page_delay: float = DEFAULT_PAGE_DELAY,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        keep_browser_open: bool = False,
    ) -> None:
        if limit <= 0:
            raise ValueError("limit must be greater than zero.")

        if browser_wait <= 0:
            raise ValueError("browser_wait must be greater than zero.")

        if page_delay < 0:
            raise ValueError("page_delay cannot be negative.")

        if max_attempts <= 0:
            raise ValueError("max_attempts must be greater than zero.")

        super().__init__(
            source_name="Lincolnshire Police",
            source_url=self.NEWS_SEARCH_URL,
            timeout=browser_wait,
            request_delay=page_delay,
        )

        self.limit = int(limit)
        self.headless = bool(headless)
        self.browser_wait = float(browser_wait)
        self.page_delay = float(page_delay)
        self.max_attempts = int(max_attempts)
        self.keep_browser_open = bool(keep_browser_open)

        self._driver: WebDriver | None = None
        self._last_collection_diagnostics: dict[str, object] = {}

    # ------------------------------------------------------------------
    # Browser lifecycle
    # ------------------------------------------------------------------

    def _build_options(self) -> Options:
        """
        Build Chrome options suitable for interactive or headless operation.
        """

        options = Options()

        if self.headless:
            options.add_argument("--headless=new")
        else:
            options.add_argument("--start-maximized")

        options.add_argument("--disable-gpu")
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-popup-blocking")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--no-sandbox")
        options.add_argument("--log-level=3")
        options.add_argument("--window-size=1600,1000")
        options.add_argument(
            f"--user-agent={self.user_agent}"
        )

        options.add_experimental_option(
            "excludeSwitches",
            ["enable-automation", "enable-logging"],
        )

        return options

    def _get_driver(self) -> WebDriver:
        """
        Return the active browser, creating it when necessary.
        """

        if self._driver is not None:
            try:
                _ = self._driver.current_url
                return self._driver
            except (NoSuchWindowException, WebDriverException):
                self._driver = None

        try:
            self._driver = webdriver.Chrome(
                options=self._build_options()
            )
        except WebDriverException as error:
            raise ScraperRequestError(
                "Chrome could not be started. Confirm that Google Chrome "
                "and Selenium are installed and available."
            ) from error

        self._driver.set_page_load_timeout(self.browser_wait)

        return self._driver

    def close(self) -> None:
        """
        Close the Selenium browser safely.
        """

        driver = self._driver
        self._driver = None

        if driver is None:
            return

        try:
            driver.quit()
        except Exception:
            LOGGER.debug(
                "The Lincolnshire Police browser did not close cleanly.",
                exc_info=True,
            )

    def clear(self) -> None:
        """
        Clear cached scraper data and close the browser.
        """

        self.close()
        super().clear()

    def __enter__(self) -> PoliceScraper:
        self._get_driver()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Page collection
    # ------------------------------------------------------------------

    def fetch(
        self,
        url: str | None = None,
    ) -> ScrapeResponse:
        """
        Open a page through Selenium and return its rendered HTML.
        """

        target_url = (url or self.source_url).strip()

        if not target_url:
            raise ValueError("A target URL is required.")

        driver = self._get_driver()
        last_error: Exception | None = None

        for attempt in range(1, self.max_attempts + 1):
            try:
                LOGGER.info(
                    "Opening %s, attempt %s of %s.",
                    target_url,
                    attempt,
                    self.max_attempts,
                )

                driver.get(target_url)

                wait = WebDriverWait(
                    driver,
                    self.browser_wait,
                )

                wait.until(
                    lambda current_driver: current_driver.execute_script(
                        "return document.readyState"
                    )
                    == "complete"
                )

                if self.page_delay:
                    time.sleep(self.page_delay)

                page_source = driver.page_source or ""

                if not page_source.strip():
                    raise ScraperRequestError(
                        f"{target_url} returned no rendered HTML."
                    )

                if self._contains_rate_limit(page_source):
                    if attempt >= self.max_attempts:
                        raise ScraperRequestError(
                            "Lincolnshire Police continued to return a "
                            "rate-limit response after all retry attempts."
                        )

                    wait_seconds = 30 * attempt

                    LOGGER.warning(
                        "Rate limit detected. Waiting %s seconds before "
                        "retrying.",
                        wait_seconds,
                    )

                    time.sleep(wait_seconds)
                    continue

                response = ScrapeResponse(
                    url=driver.current_url or target_url,
                    body=page_source,
                    status_code=200,
                    content_type="text/html",
                    encoding="utf-8",
                    headers={},
                    fetched_at=datetime.now(timezone.utc),
                )

                self._last_response = response
                return response

            except ScraperRequestError:
                raise

            except (TimeoutException, WebDriverException) as error:
                last_error = error

                if attempt >= self.max_attempts:
                    break

                wait_seconds = 3 * attempt

                LOGGER.warning(
                    "Page load failed for %s. Waiting %s seconds before "
                    "retrying.",
                    target_url,
                    wait_seconds,
                )

                time.sleep(wait_seconds)

        raise ScraperRequestError(
            f"Could not load {target_url} after "
            f"{self.max_attempts} attempts: {last_error}"
        ) from last_error

    @classmethod
    def _contains_rate_limit(cls, html: str) -> bool:
        lowered = html.lower()

        return any(
            term in lowered
            for term in cls.RATE_LIMIT_TERMS
        )

    # ------------------------------------------------------------------
    # Story discovery
    # ------------------------------------------------------------------

    def parse(
        self,
        response: ScrapeResponse,
    ) -> Iterable[Story]:
        """
        Parse the news-search page and collect complete articles.
        """

        candidates, diagnostics = self._discover_recent_candidates(response)

        if not candidates:
            raise ScraperParseError(
                "No Lincolnshire Police article links were found on "
                "the news-search page."
            )

        stories: list[Story] = []

        try:
            for position, candidate in enumerate(
                candidates,
                start=1,
            ):
                article_url = candidate.url
                LOGGER.info(
                    "Collecting police article %s of %s: %s",
                    position,
                    len(candidates),
                    article_url,
                )

                try:
                    article_response = self.fetch(article_url)
                    story = self.parse_article(article_response)

                    if story is not None:
                        if not str(story.published or "").strip() and candidate.published is not None:
                            # Some official publishers expose the timestamp on
                            # their listing card but omit it from the article.
                            story.published = candidate.published.isoformat()
                        parsed, reason = _police_recency_rejection_reason(
                            story.published
                        )
                        if reason is None:
                            stories.append(story)
                        else:
                            diagnostics["article_date_rejections"] += 1
                            LOGGER.debug(
                                "Rejecting police story title=%r url=%s "
                                "raw_date=%r parsed_date=%s reason=%s",
                                story.title,
                                article_url,
                                story.published,
                                parsed,
                                reason,
                            )

                except Exception as error:
                    LOGGER.exception(
                        "Could not collect police article %s.",
                        article_url,
                    )

                    # One malformed article must not prevent all remaining
                    # police stories from being collected.
                    continue

        finally:
            diagnostics["stories_retained"] = len(stories)
            self._last_collection_diagnostics = diagnostics
            LOGGER.info(
                "Police recency collection: visited %s pages, discovered "
                "%s unique links, retained %s stories from the last 14 days.",
                diagnostics["pages_visited"],
                diagnostics["unique_links_discovered"],
                len(stories),
            )
            if not self.keep_browser_open:
                self.close()

        return stories

    def _discover_recent_candidates(
        self,
        first_response: ScrapeResponse,
    ) -> tuple[list[_ListingCandidate], dict[str, object]]:
        """Follow server-rendered pagination and retain recent candidates."""

        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=DEFAULT_MAX_AGE_DAYS)
        candidates: list[_ListingCandidate] = []
        seen_urls: set[str] = set()
        visited_urls: set[str] = set()
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
            page_key = self._query_free_url(page_url).casefold() + "?" + urlparse(page_url).query.casefold()
            if page_key in visited_urls:
                diagnostics["stop_reason"] = "pagination-loop"
                break
            visited_urls.add(page_key)
            diagnostics["pages_visited"] = page_number

            page_candidates = self._extract_listing_candidates(
                response.body,
                page_url,
            )
            new_candidates: list[_ListingCandidate] = []
            for candidate in page_candidates:
                key = self._query_free_url(candidate.url).casefold().rstrip("/")
                if key in seen_urls:
                    continue
                seen_urls.add(key)
                new_candidates.append(candidate)

            dated = [item.published for item in page_candidates if item.published is not None]
            newest = max(dated) if dated else None
            oldest = min(dated) if dated else None
            inside_count = 0
            old_count = 0
            for candidate in new_candidates:
                if candidate.published is None:
                    candidates.append(candidate)
                    continue
                _, reason = _police_recency_rejection_reason(
                    candidate.published,
                    now=now,
                )
                if reason == "story-too-old":
                    diagnostics["listing_old_rejections"] += 1
                    old_count += 1
                elif reason == "story-date-in-future":
                    diagnostics["listing_future_rejections"] += 1
                elif reason is None:
                    candidates.append(candidate)
                    inside_count += 1

            diagnostics["unique_links_discovered"] = len(seen_urls)
            LOGGER.debug(
                "Police listing page=%s url=%s links=%s new_unique=%s "
                "newest=%s oldest=%s inside_cutoff=%s rejected_old=%s",
                page_number,
                page_url,
                len(page_candidates),
                len(new_candidates),
                newest,
                oldest,
                inside_count,
                old_count,
            )

            all_dated = bool(page_candidates) and len(dated) == len(page_candidates)
            newest_to_oldest = all(
                dated[index] >= dated[index + 1]
                for index in range(len(dated) - 1)
            )
            if all_dated and newest_to_oldest and newest is not None and newest < cutoff:
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
        else:
            diagnostics["stop_reason"] = "maximum-page-safety-limit"

        LOGGER.debug("Police pagination stopped: %s", diagnostics["stop_reason"])
        return candidates, diagnostics

    def _extract_listing_candidates(
        self,
        html: str,
        page_url: str,
    ) -> list[_ListingCandidate]:
        soup = BeautifulSoup(html, "html.parser")
        candidates: list[_ListingCandidate] = []
        seen: set[str] = set()
        for anchor in soup.find_all("a", href=True):
            absolute_url = self._normalise_url(str(anchor.get("href") or ""))
            if not self._is_article_url(absolute_url):
                continue
            key = self._query_free_url(absolute_url).casefold().rstrip("/")
            if key in seen:
                continue
            seen.add(key)
            context: Tag | None = anchor
            raw_published = ""
            for _ in range(6):
                if context is None:
                    break
                time_element = context.select_one("time[datetime], time")
                if time_element is not None:
                    raw_published = str(
                        time_element.get("datetime")
                        or time_element.get_text(" ", strip=True)
                        or ""
                    ).strip()
                if not raw_published:
                    match = re.search(
                        r"\bPublished\s*:\s*("
                        r"(?:\d{1,2}:\d{2}\s+)?\d{1,2}/\d{1,2}/\d{4}"
                        r"|(?:\d{1,2}:\d{2}\s+)?\d{1,2}\s+"
                        r"[A-Za-z]+\s+\d{4})",
                        context.get_text("\n", strip=True),
                        flags=re.IGNORECASE,
                    )
                    if match:
                        raw_published = match.group(1).strip()
                if raw_published:
                    break
                context = context.parent if isinstance(context.parent, Tag) else None
            candidates.append(
                _ListingCandidate(
                    url=absolute_url,
                    title=self._clean_text(anchor.get_text(" ", strip=True)),
                    published=_parse_police_publication_datetime(raw_published),
                    raw_published=raw_published,
                )
            )
        return candidates

    def _extract_next_listing_url(self, html: str, page_url: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        for anchor in soup.find_all("a", href=True):
            label = " ".join(
                filter(
                    None,
                    (
                        anchor.get_text(" ", strip=True),
                        str(anchor.get("aria-label") or ""),
                        str(anchor.get("title") or ""),
                    ),
                )
            ).casefold()
            rel = {str(value).casefold() for value in (anchor.get("rel") or [])}
            if "next" in rel or "next page" in label:
                return self._normalise_url(urljoin(page_url, str(anchor.get("href") or "")))
        return ""

    @staticmethod
    def _query_free_url(url: str) -> str:
        parsed = urlparse(url)
        return parsed._replace(query="", fragment="").geturl()

    def extract_article_links(
        self,
        html: str,
        *,
        limit: int | None = None,
    ) -> list[str]:
        """
        Extract unique Lincolnshire Police article links.
        """

        maximum = self.limit if limit is None else int(limit)

        if maximum <= 0:
            return []

        soup = BeautifulSoup(html, "html.parser")

        links: list[str] = []
        seen: set[str] = set()

        for anchor in soup.find_all("a", href=True):
            href = str(anchor.get("href") or "").strip()

            if not href:
                continue

            absolute_url = self._normalise_url(href)

            if not self._is_article_url(absolute_url):
                continue

            key = absolute_url.lower().rstrip("/")

            if key in seen:
                continue

            seen.add(key)
            links.append(absolute_url)

            if len(links) >= maximum:
                break

        return links

    def _normalise_url(self, url: str) -> str:
        absolute = urljoin(self.BASE_URL, url.strip())
        parsed = urlparse(absolute)

        # Remove fragments while retaining any meaningful query string.
        return parsed._replace(fragment="").geturl()

    def _is_article_url(self, url: str) -> bool:
        parsed = urlparse(url)

        if parsed.netloc.lower() not in {
            "www.lincs.police.uk",
            "lincs.police.uk",
        }:
            return False

        path = parsed.path.lower()

        if self.ARTICLE_PATH_MARKER not in path:
            return False

        if path.rstrip("/") == self.ARTICLE_PATH_MARKER.rstrip("/"):
            return False

        return True

    # ------------------------------------------------------------------
    # Individual article parsing
    # ------------------------------------------------------------------

    def parse_article(
        self,
        response: ScrapeResponse,
    ) -> Story | None:
        """
        Convert an individual police article page into a Story.
        """

        soup = BeautifulSoup(response.body, "html.parser")

        self._remove_unwanted_elements(soup)

        title = self._extract_title(soup)

        if not title:
            LOGGER.warning(
                "Skipping police article with no title: %s",
                response.url,
            )
            return None

        published = self._extract_published(soup)
        summary = self._extract_summary(soup)
        image = self._extract_image(soup, response.url)
        body = self._extract_body(soup)

        if not body:
            body = summary

        if not body:
            LOGGER.warning(
                "Skipping police article with no article text: %s",
                response.url,
            )
            return None

        if summary and not self._starts_with_text(body, summary):
            body = f"{summary}\n\n{body}"

        return Story(
            title=title,
            body=body,
            url=response.url,
            source=self.source_name,
            published=published,
            scraped_at=response.fetched_at,
            image_url=image["url"],
            image_caption=image["caption"],
            image_credit=image["credit"],
            image_alt_text=image["alt_text"],
        )

    @staticmethod
    def _remove_unwanted_elements(soup: BeautifulSoup) -> None:
        for element in soup.select(
            "script, style, noscript, svg, form, nav, footer, "
            "button, iframe, dialog"
        ):
            element.decompose()

    def _extract_title(self, soup: BeautifulSoup) -> str:
        for selector in self.TITLE_SELECTORS:
            element = soup.select_one(selector)

            if element is None:
                continue

            text = self._clean_text(
                element.get_text(" ", strip=True)
            )

            if text:
                return text

        metadata_title = soup.select_one(
            'meta[property="og:title"]'
        )

        if metadata_title is not None:
            return self._clean_text(
                str(metadata_title.get("content") or "")
            )

        return ""

    def _extract_published(self, soup: BeautifulSoup) -> str:
        for selector in self.DATE_SELECTORS:
            element = soup.select_one(selector)

            if element is None:
                continue

            datetime_value = str(
                element.get("datetime") or ""
            ).strip()

            if datetime_value:
                return datetime_value

            text = self._clean_text(
                element.get_text(" ", strip=True)
            )

            text = re.sub(
                r"^published\s*:\s*",
                "",
                text,
                flags=re.IGNORECASE,
            )

            if text:
                return text

        metadata_date = soup.select_one(
            'meta[property="article:published_time"]'
        )

        if metadata_date is not None:
            return str(
                metadata_date.get("content") or ""
            ).strip()

        page_text = soup.get_text(" ", strip=True)

        match = re.search(
            r"Published\s*:\s*"
            r"(\d{1,2}:\d{2}\s+\d{1,2}/\d{1,2}/\d{4})",
            page_text,
            flags=re.IGNORECASE,
        )

        if match:
            return match.group(1).strip()

        return ""

    def _extract_summary(self, soup: BeautifulSoup) -> str:
        for selector in self.SUMMARY_SELECTORS:
            element = soup.select_one(selector)

            if element is None:
                continue

            text = self._clean_text(
                element.get_text(" ", strip=True)
            )

            if self._is_usable_paragraph(text):
                return text

        description = soup.select_one(
            'meta[name="description"]'
        )

        if description is not None:
            text = self._clean_text(
                str(description.get("content") or "")
            )

            if self._is_usable_paragraph(text):
                return text

        return ""

    def _extract_image(
        self,
        soup: BeautifulSoup,
        article_url: str,
    ) -> dict[str, str]:
        """Extract the best available article image and its metadata."""

        metadata_url = self._extract_metadata_image_url(soup, article_url)

        for selector in self.IMAGE_SELECTORS:
            for element in soup.select(selector):
                if not isinstance(element, Tag):
                    continue

                image_url = self._image_url_from_element(
                    element,
                    article_url,
                )

                if not image_url or self._is_rejected_image(image_url):
                    continue

                caption, credit = self._extract_image_caption(element)
                alt_text = self._clean_text(
                    str(element.get("alt") or "")
                )

                return {
                    "url": image_url,
                    "caption": caption,
                    "credit": credit,
                    "alt_text": alt_text,
                }

        if metadata_url and not self._is_rejected_image(metadata_url):
            return {
                "url": metadata_url,
                "caption": "",
                "credit": "",
                "alt_text": self._extract_metadata_image_alt(soup),
            }

        return {
            "url": "",
            "caption": "",
            "credit": "",
            "alt_text": "",
        }

    def _extract_metadata_image_url(
        self,
        soup: BeautifulSoup,
        article_url: str,
    ) -> str:
        for selector in self.IMAGE_META_SELECTORS:
            element = soup.select_one(selector)

            if element is None:
                continue

            value = str(
                element.get("content")
                or element.get("href")
                or ""
            ).strip()

            if value:
                return self._normalise_image_url(value, article_url)

        return ""

    def _image_url_from_element(
        self,
        element: Tag,
        article_url: str,
    ) -> str:
        for attribute in self.IMAGE_SOURCE_ATTRIBUTES:
            value = str(element.get(attribute) or "").strip()

            if value and not value.lower().startswith("data:"):
                return self._normalise_image_url(value, article_url)

        srcset = str(
            element.get("srcset")
            or element.get("data-srcset")
            or ""
        ).strip()

        if srcset:
            candidates: list[tuple[int, str]] = []

            for item in srcset.split(","):
                parts = item.strip().split()

                if not parts:
                    continue

                candidate_url = parts[0]
                width = 0

                if len(parts) > 1:
                    match = re.match(r"(\d+)w$", parts[1])
                    if match:
                        width = int(match.group(1))

                candidates.append((width, candidate_url))

            if candidates:
                _, best_url = max(candidates, key=lambda item: item[0])
                return self._normalise_image_url(best_url, article_url)

        return ""

    @staticmethod
    def _normalise_image_url(value: str, article_url: str) -> str:
        cleaned = value.strip().replace("&amp;", "&")

        if cleaned.startswith("//"):
            cleaned = f"https:{cleaned}"

        return urljoin(article_url, cleaned)

    def _is_rejected_image(self, image_url: str) -> bool:
        lowered = image_url.casefold()

        return any(
            term in lowered
            for term in self.REJECTED_IMAGE_TERMS
        )

    def _extract_image_caption(self, image: Tag) -> tuple[str, str]:
        figure = image.find_parent("figure")

        if figure is None:
            return "", ""

        caption_element = figure.find("figcaption")

        if caption_element is None:
            return "", ""

        caption = self._clean_text(
            caption_element.get_text(" ", strip=True)
        )

        if not caption:
            return "", ""

        credit = ""
        credit_match = re.search(
            r"(?:image|photo|picture)\s*(?:credit|by)\s*[:\-]?\s*(.+)$",
            caption,
            flags=re.IGNORECASE,
        )

        if credit_match:
            credit = self._clean_text(credit_match.group(1))

        return caption, credit

    def _extract_metadata_image_alt(self, soup: BeautifulSoup) -> str:
        for selector in (
            'meta[property="og:image:alt"]',
            'meta[name="twitter:image:alt"]',
        ):
            element = soup.select_one(selector)

            if element is not None:
                text = self._clean_text(
                    str(element.get("content") or "")
                )

                if text:
                    return text

        return ""

    def _extract_body(self, soup: BeautifulSoup) -> str:
        container = self._find_content_container(soup)

        if container is None:
            return ""

        paragraphs: list[str] = []
        seen: set[str] = set()

        for element in container.find_all(
            ["p", "h2", "h3", "blockquote", "li"]
        ):
            text = self._clean_text(
                element.get_text(" ", strip=True)
            )

            if not self._is_usable_paragraph(text):
                continue

            key = text.casefold()

            if key in seen:
                continue

            seen.add(key)
            paragraphs.append(text)

        return "\n\n".join(paragraphs).strip()

    def _find_content_container(
        self,
        soup: BeautifulSoup,
    ) -> Tag | None:
        candidates: list[Tag] = []

        for selector in self.CONTENT_SELECTORS:
            for element in soup.select(selector):
                if isinstance(element, Tag):
                    candidates.append(element)

        if not candidates:
            return None

        def content_score(element: Tag) -> int:
            paragraph_text = " ".join(
                paragraph.get_text(" ", strip=True)
                for paragraph in element.find_all("p")
            )

            return len(paragraph_text)

        return max(candidates, key=content_score)

    def _is_usable_paragraph(self, text: str) -> bool:
        cleaned = text.strip()

        if len(cleaned) < 20:
            return False

        lowered = cleaned.casefold()

        if any(
            lowered.startswith(prefix)
            for prefix in self.BLOCKED_PARAGRAPH_PREFIXES
        ):
            return False

        if lowered in {
            "news",
            "appeals",
            "campaigns",
            "safer neighbourhoods",
            "main article content",
        }:
            return False

        return True

    @staticmethod
    def _clean_text(value: str) -> str:
        text = value.replace("\xa0", " ")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\s*\n\s*", "\n", text)

        return text.strip()

    @staticmethod
    def _starts_with_text(body: str, prefix: str) -> bool:
        normalised_body = " ".join(
            body.casefold().split()
        )

        normalised_prefix = " ".join(
            prefix.casefold().split()
        )

        return normalised_body.startswith(normalised_prefix)

    # ------------------------------------------------------------------
    # Convenience methods
    # ------------------------------------------------------------------

    def fetch_latest_news(
        self,
        limit: int | None = None,
    ) -> list[Story]:
        """
        Collect the latest police stories without processing them.

        This preserves the familiar method name from the earlier scraper while
        returning shared NewsDesk Story objects.
        """

        original_limit = self.limit

        if limit is not None:
            if limit <= 0:
                raise ValueError("limit must be greater than zero.")

            self.limit = int(limit)

        try:
            try:
                rss_response = BaseScraper.fetch(self, self.RSS_URL)
                candidates = self._rss_candidates(rss_response.body)
            except (ScraperRequestError, ScraperParseError) as error:
                LOGGER.warning(
                    "Lincolnshire Police RSS was unavailable (%s); "
                    "falling back to the paginated official News Search.",
                    error,
                )
                return self.get_stories(refresh=True, deduplicate=True)
            stories: list[Story] = []
            for candidate in candidates[: self.limit]:
                try:
                    article_response = self.fetch(candidate.url)
                    story = self.parse_article(article_response)
                except Exception:
                    LOGGER.exception(
                        "Could not collect Lincolnshire Police article %s.",
                        candidate.url,
                    )
                    continue
                if story is None:
                    continue
                parsed, reason = _police_recency_rejection_reason(story.published)
                if reason is None:
                    stories.append(story)
            return stories
        finally:
            self.limit = original_limit
            if not self.keep_browser_open:
                self.close()

    def _rss_candidates(self, xml_text: str) -> list[_ListingCandidate]:
        """Return current, unique article candidates from the official RSS feed."""

        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as error:
            raise ScraperParseError(
                "Lincolnshire Police returned an unreadable RSS feed."
            ) from error

        candidates: list[_ListingCandidate] = []
        seen: set[str] = set()
        for item in root.findall(".//item"):
            url = self._normalise_url(str(item.findtext("link") or ""))
            if not self._is_article_url(url):
                continue
            key = self._query_free_url(url).casefold().rstrip("/")
            if key in seen:
                continue
            seen.add(key)
            raw_published = str(item.findtext("pubDate") or "").strip()
            published, reason = _police_recency_rejection_reason(raw_published)
            if reason is not None:
                continue
            candidates.append(
                _ListingCandidate(
                    url=url,
                    title=self._clean_text(str(item.findtext("title") or "")),
                    published=published,
                    raw_published=raw_published,
                )
            )
        candidates.sort(
            key=lambda item: item.published or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        if not candidates:
            raise ScraperParseError(
                "No current Lincolnshire Police articles were found in the RSS feed."
            )
        return candidates

    def run(
        self,
        *,
        refresh: bool = True,
        continue_on_error: bool = True,
    ):
        """
        Collect stories and process them through StoryEngine.
        """

        try:
            return super().run(
                refresh=refresh,
                continue_on_error=continue_on_error,
            )
        finally:
            if not self.keep_browser_open:
                self.close()


__all__ = [
    "PoliceScraper",
]
