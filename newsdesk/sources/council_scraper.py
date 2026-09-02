"""HTTP collectors for official Greater Lincolnshire council news."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
import json
import re
from time import perf_counter
from urllib.parse import parse_qs, quote_plus, unquote, urljoin, urlsplit, urlunsplit
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup, Tag
import requests

from newsdesk.story import Story


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "council.json"
DEFAULT_MAX_AGE_DAYS = 14
USER_AGENT = "DevourLincolnshireNewsDesk-Council/1.0"


@dataclass(frozen=True, slots=True)
class CouncilSource:
    key: str
    name: str
    url: str
    enabled: bool = True
    detail_path_patterns: tuple[str, ...] | list[str] = ()
    search_fallback_query: str = ""


@dataclass(slots=True)
class CouncilCandidate:
    title: str
    url: str
    published_at: datetime | None
    summary: str = ""
    image_url: str = ""
    image_alt_text: str = ""


@dataclass(slots=True)
class CouncilSourceHealth:
    source_key: str
    source_name: str
    attempted: bool = True
    successful: bool = False
    listing_pages_requested: int = 0
    articles_found: int = 0
    articles_retained: int = 0
    direct_lincolnshire_matches: int = 0
    failures: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0


def load_council_config(path: str | Path | None = None) -> dict:
    config_path = Path(path or DEFAULT_CONFIG_PATH)
    data = json.loads(config_path.read_text(encoding="utf-8"))
    data["recency_days"] = max(1, int(data.get("recency_days", DEFAULT_MAX_AGE_DAYS)))
    data["max_listing_pages"] = max(1, int(data.get("max_listing_pages", 3)))
    data["request_timeout_seconds"] = max(
        1, int(data.get("request_timeout_seconds", 20))
    )
    data["sources"] = [CouncilSource(**item) for item in data.get("sources", [])]
    return data


class CouncilSourceScraper:
    """Collect one configured official source using source-specific selectors."""

    def __init__(self, source: CouncilSource, *, session=None, config=None):
        self.source = source
        self.config = config or load_council_config()
        self.session = session or requests.Session()
        self._owns_session = session is None
        self._listing_failures: list[str] = []
        self.session.headers.update({"User-Agent": USER_AGENT})
        self.session.headers.update({
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-GB,en;q=0.9",
        })

    def close(self) -> None:
        if self._owns_session:
            self.session.close()

    def collect(
        self,
        *,
        now: datetime | None = None,
    ) -> tuple[list[Story], CouncilSourceHealth]:
        current = self._utc(now or datetime.now(timezone.utc))
        cutoff = current - timedelta(days=self.config["recency_days"])
        health = CouncilSourceHealth(self.source.key, self.source.name)
        started = perf_counter()
        stories: list[Story] = []
        seen_urls: set[str] = set()
        self._listing_failures.clear()
        next_url = self.source.url
        try:
            for _page in range(self.config["max_listing_pages"]):
                html, resolved_url = self._request(next_url)
                health.listing_pages_requested += 1
                candidates, discovered_next = self.parse_listing(html, resolved_url)
                if self._listing_failures:
                    health.failures.extend(self._listing_failures)
                    self._listing_failures.clear()
                health.articles_found += len(candidates)
                page_has_old_story = False
                for candidate in candidates:
                    if candidate.published_at is not None and candidate.published_at < cutoff:
                        page_has_old_story = True
                        continue
                    if candidate.published_at is not None and candidate.published_at > current + timedelta(days=1):
                        continue
                    canonical = self.canonical_url(candidate.url)
                    if canonical in seen_urls:
                        continue
                    seen_urls.add(canonical)
                    try:
                        story = self._collect_detail(candidate)
                    except Exception as error:
                        health.failures.append(f"{candidate.title}: {error}")
                        continue
                    published = self.parse_date(story.published)
                    if published is None:
                        health.failures.append(
                            f"{candidate.title}: article publication date not found"[:300]
                        )
                        continue
                    if published < cutoff:
                        page_has_old_story = True
                        continue
                    if published <= current + timedelta(days=1):
                        stories.append(story)
                if page_has_old_story or not discovered_next:
                    break
                next_url = discovered_next
            health.articles_retained = len(stories)
            health.successful = True
        except Exception as error:
            health.failures.append(str(error)[:300])
            if self.source.search_fallback_query:
                try:
                    fallback = self._collect_search_fallback(current, cutoff)
                    stories.extend(fallback)
                    health.articles_found += len(fallback)
                    health.articles_retained = len(stories)
                    health.successful = bool(fallback)
                    if fallback:
                        health.failures.append(
                            f"Loaded {len(fallback)} search-index summaries because the official site was blocked"
                        )
                except Exception as fallback_error:
                    health.failures.append(f"Search fallback: {fallback_error}"[:300])
        finally:
            health.duration_seconds = perf_counter() - started
        return stories, health

    def _collect_search_fallback(
        self, current: datetime, cutoff: datetime
    ) -> list[Story]:
        """Discover recent official items through Google News when a site blocks access.

        Google's RSS entry links open through Google News and then redirect to the
        original council page.  We only retain entries whose ``source`` element
        names the configured council and whose source URL is on that council's
        official domain.  This avoids treating general web-search matches as
        council releases.
        """

        query = quote_plus(self.source.search_fallback_query)
        feed_url = (
            "https://news.google.com/rss/search"
            f"?q={query}&hl=en-GB&gl=GB&ceid=GB:en"
        )
        response = self.session.get(
            feed_url,
            timeout=self.config["request_timeout_seconds"],
            headers={"User-Agent": USER_AGENT},
        )
        response.raise_for_status()
        root = ET.fromstring(response.content)
        retained: list[Story] = []
        seen: set[str] = set()
        for item in root.findall(".//item"):
            title = re.sub(r"\s+", " ", item.findtext("title") or "").strip()
            raw_link = (item.findtext("link") or "").strip()
            description_html = item.findtext("description") or ""
            source_node = item.find("source")
            source_name = (source_node.text or "").strip() if source_node is not None else ""
            source_url = (source_node.get("url") or "").strip() if source_node is not None else ""
            if not title or not raw_link or not self._google_source_matches(source_name, source_url):
                continue
            canonical = self.canonical_url(raw_link)
            if canonical in seen:
                continue
            published = self._rss_date(item.findtext("pubDate"))
            if published is None or published < cutoff or published > current + timedelta(days=1):
                continue
            suffix = f" - {self.source.name}"
            if title.casefold().endswith(suffix.casefold()):
                title = title[:-len(suffix)].strip()
            description = "Full article text is currently blocked by the official council website."
            notice = "SUMMARY ONLY — open the official source for the complete article."
            retained.append(
                Story(
                    title=title,
                    summary=f"{notice} {description}".strip(),
                    body=f"{description}\n\n{notice}".strip(),
                    source=self.source.name,
                    url=canonical,
                    published=published.isoformat(),
                    classification="SUMMARY ONLY",
                    scraped_at=datetime.now(timezone.utc).isoformat(),
                    extras={
                        "source_key": self.source.key,
                        "content_completeness": "summary_only",
                        "search_index_fallback": True,
                    },
                )
            )
            seen.add(canonical)
        return retained

    def _google_source_matches(self, source_name: str, source_url: str) -> bool:
        """Require Google News to identify the configured official publisher."""

        if not source_name or not source_url or not self._same_source_url(source_url):
            return False
        expected = re.sub(r"[^a-z0-9]+", " ", self.source.name.casefold()).strip()
        actual = re.sub(r"[^a-z0-9]+", " ", source_name.casefold()).strip()
        return actual == expected or expected in actual or actual in expected

    def _official_result_url(self, raw_link: str, description_html: str) -> str:
        candidates = [raw_link]
        parsed = urlsplit(raw_link)
        for values in parse_qs(parsed.query).values():
            candidates.extend(unquote(value) for value in values)
        candidates.extend(
            re.findall(r"https?://[^\s\"'<>]+", description_html, re.I)
        )
        patterns = tuple(self.source.detail_path_patterns or ())
        for candidate in candidates:
            candidate = candidate.replace("&amp;", "&").rstrip(".,);]")
            if not self._same_source_url(candidate):
                continue
            path = urlsplit(candidate).path
            if patterns and not any(re.search(pattern, path, re.I) for pattern in patterns):
                continue
            return candidate
        return ""

    @staticmethod
    def _rss_date(value: str | None) -> datetime | None:
        try:
            return CouncilSourceScraper._utc(parsedate_to_datetime(str(value or "")))
        except (TypeError, ValueError):
            return None

    def _request(self, url: str) -> tuple[str, str]:
        if not self._same_source_url(url):
            raise ValueError(f"Refusing off-source Council URL: {url}")
        try:
            response = self.session.get(
                url,
                timeout=self.config["request_timeout_seconds"],
            )
            response.raise_for_status()
            if not self._same_source_url(response.url):
                raise ValueError(f"Council source redirected off-site: {response.url}")
            lowered = response.text.casefold()
            if self._is_challenge(lowered):
                raise RuntimeError("Council source returned an anti-bot challenge")
            return response.text, response.url
        except Exception:
            raise

    @staticmethod
    def _is_challenge(text: str) -> bool:
        return (
            "verifying that you are not a robot" in text
            or "enable javascript and cookies to continue" in text
        )

    def parse_listing(
        self, html: str, page_url: str | None = None
    ) -> tuple[list[CouncilCandidate], str | None]:
        soup = BeautifulSoup(html, "html.parser")
        base_url = page_url or self.source.url
        return self._parse_generic_listing(soup, base_url)

    def _parse_generic_listing(self, soup, base_url):
        """Discover article cards across Jadu, Drupal, GOSS and WordPress."""

        candidates: list[CouncilCandidate] = []
        seen: set[str] = set()
        patterns = tuple(self.source.detail_path_patterns or ())
        for anchor in soup.select(
            "main h2 a[href], main h3 a[href], main h4 a[href], "
            "#main h2 a[href], #main h3 a[href], #main h4 a[href], article a[href]"
        ):
            href = str(anchor.get("href") or "").strip()
            absolute = urljoin(base_url, href)
            if not href or not self._same_source_url(absolute):
                continue
            path = urlsplit(absolute).path
            if patterns and not any(re.search(pattern, path, re.I) for pattern in patterns):
                continue
            canonical = self.canonical_url(absolute)
            if canonical in seen or canonical == self.canonical_url(self.source.url):
                continue
            title_node = anchor.select_one("h2, h3, h4")
            title = self._text(title_node or anchor)
            title = re.sub(r"^Image\s+", "", title, flags=re.I)
            title = re.sub(
                r"^(?:\d{1,2}\s+)?(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}\s+",
                "", title, flags=re.I,
            )
            if len(title) < 18:
                continue
            container = anchor.find_parent(("article", "li")) or anchor.find_parent("div")
            context = self._text(container)
            published = self.parse_date(context)
            image = container.select_one("img[src], img[data-src]") if container else None
            summary = ""
            if container is not None:
                summary = self._text(container.select_one("p, .summary, .description"))
            candidates.append(
                CouncilCandidate(
                    title=title,
                    url=absolute,
                    published_at=published,
                    summary=summary,
                    image_url=urljoin(
                        base_url,
                        str(image.get("data-src") or image.get("src") or ""),
                    ) if image else "",
                    image_alt_text=str(image.get("alt", "")).strip() if image else "",
                )
            )
            seen.add(canonical)
        return candidates, self._next_link(soup, base_url)

    def _parse_bassetlaw_listing(self, soup, base_url):
        candidates = []
        for anchor in soup.select("main a.fptext[href]"):
            title = self._text(anchor)
            row = anchor.find_parent("div", class_="row")
            if not title or row is None:
                continue
            date_row = row.find_next_sibling("div", class_="row")
            published = self._listing_date(title, self._text(date_row))
            if published is None:
                continue
            image = row.select_one("img[src]")
            summary_node = anchor.find_parent("div").select_one("p")
            candidates.append(
                CouncilCandidate(
                    title,
                    urljoin(base_url, anchor["href"]),
                    published,
                    self._text(summary_node),
                    urljoin(base_url, image["src"]) if image else "",
                    str(image.get("alt", "")).strip() if image else "",
                )
            )
        return candidates, None

    def _parse_nottinghamshire_listing(self, soup, base_url):
        candidates = []
        for item in soup.select("main li.news-list-item"):
            anchor = item.select_one("a[href]")
            title_node = item.select_one("h2, h3")
            title = self._text(title_node)
            published = self._listing_date(
                title, self._text(item.select_one(".dateline, time"))
            )
            if anchor is None or title_node is None or published is None:
                continue
            image = item.select_one("img[src]")
            candidates.append(
                CouncilCandidate(
                    title,
                    urljoin(base_url, anchor["href"]),
                    published,
                    self._text(item.select_one(".item-desc-container, p")),
                    urljoin(base_url, image["src"]) if image else "",
                    str(image.get("alt", "")).strip() if image else "",
                )
            )
        return candidates, self._next_link(soup, base_url)

    def _parse_emcca_listing(self, soup, base_url):
        candidates = []
        for item in soup.select("article.c-post"):
            title_node = item.select_one("h2, h3")
            anchor = title_node.find_parent("a", href=True) if title_node else None
            title = self._text(title_node)
            published = self._listing_date(title, self._text(item))
            if anchor is None or title_node is None or published is None:
                continue
            image = item.select_one("img[src]")
            candidates.append(
                CouncilCandidate(
                    title,
                    urljoin(base_url, anchor["href"]),
                    published,
                    "",
                    urljoin(base_url, image["src"]) if image else "",
                    str(image.get("alt", "")).strip() if image else "",
                )
            )
        return candidates, self._next_link(soup, base_url)

    def _collect_detail(self, candidate: CouncilCandidate) -> Story:
        html, resolved_url = self._request(candidate.url)
        soup = BeautifulSoup(html, "html.parser")
        content = (
            soup.select_one("main article")
            or soup.select_one("article")
            or soup.select_one("main .content")
            or soup.select_one("main .c-editable")
            or soup.select_one("main")
            or soup.select_one("#main")
        )
        if content is None:
            raise ValueError("article content not found")
        for unwanted in content.select(
            "nav, footer, form, script, style, noscript, .pagination, "
            ".share, .social-share, .related, .breadcrumbs, .cookie"
        ):
            unwanted.decompose()
        paragraphs = []
        for node in content.select("p, li"):
            text = self._text_with_links(node, resolved_url)
            lowered = text.casefold()
            if (
                len(text) >= 20
                and "last updated on" not in lowered
                and text != "<END>"
                and not lowered.startswith(("share this", "cookie", "privacy", "accessibility"))
            ):
                paragraphs.append(text)
        body = "\n\n".join(dict.fromkeys(paragraphs))
        if not body:
            raise ValueError("article body is empty")
        title = self._text(soup.select_one("h1")) or candidate.title
        summary = candidate.summary
        if not summary:
            summary = self._text(soup.select_one(".lede")) or paragraphs[0]
        image = soup.select_one("meta[property='og:image'][content]") or content.select_one(
            "figure img[src], img[src], img[data-src]"
        )
        image_url = candidate.image_url
        image_alt = candidate.image_alt_text
        if image is not None:
            source_value = image.get("src") or image.get("data-src") or image.get("content")
            if source_value:
                image_url = urljoin(resolved_url, source_value)
            image_alt = str(image.get("alt", image_alt)).strip()
        collected_at = datetime.now(timezone.utc).isoformat()
        published = candidate.published_at or self._detail_date(soup)
        return Story(
            title=title,
            summary=summary,
            body=body,
            source=self.source.name,
            url=self.canonical_url(resolved_url),
            published=published.isoformat() if published else "",
            image_url=image_url,
            image_caption=image_alt,
            image_credit=self.source.name,
            image_alt_text=image_alt,
            scraped_at=collected_at,
            extras={"source_key": self.source.key, "collected_at": collected_at},
        )

    def _detail_date(self, soup: BeautifulSoup) -> datetime | None:
        for selector, attribute in (
            ("time[datetime]", "datetime"),
            ("meta[property='article:published_time'][content]", "content"),
            ("meta[name='date'][content]", "content"),
            ("meta[name='publish-date'][content]", "content"),
        ):
            node = soup.select_one(selector)
            if node is not None:
                parsed = self.parse_date(node.get(attribute) or node.get_text(" ", strip=True))
                if parsed is not None:
                    return parsed
        page_text = soup.get_text(" ", strip=True)
        labelled = re.search(
            r"(?:Published|Posted|Article posted on|Publication date)\s*:?\s*"
            r"((?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)?[,]?\s*"
            r"\d{1,2}(?:st|nd|rd|th)?\s+"
            r"(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4})",
            page_text, re.I,
        )
        if labelled:
            parsed = self.parse_date(labelled.group(1))
            if parsed is not None:
                return parsed
        return self.parse_date(page_text)

    def _next_link(self, soup: BeautifulSoup, base_url: str) -> str | None:
        for anchor in soup.select("a[href]"):
            label = self._text(anchor).casefold()
            classes = {str(value).casefold() for value in anchor.get("class", [])}
            relations = {str(value).casefold() for value in anchor.get("rel", [])}
            aria_label = str(anchor.get("aria-label", "")).casefold()
            if (
                label == "next"
                or "next" in relations
                or aria_label.startswith("next")
                or any("next" in value for value in classes)
            ):
                candidate = urljoin(base_url, anchor["href"])
                if self._same_source_url(candidate):
                    return candidate
        return None

    def _same_source_url(self, url: str) -> bool:
        expected = urlsplit(self.source.url).netloc.casefold().removeprefix("www.")
        actual = urlsplit(url).netloc.casefold().removeprefix("www.")
        return bool(actual and actual == expected)

    def _listing_date(self, title: str, value: object) -> datetime | None:
        published = self.parse_date(value)
        if published is None:
            self._listing_failures.append(
                f"Listing item skipped: missing or invalid publication date: {title}"[:300]
            )
        return published

    @staticmethod
    def canonical_url(url: str) -> str:
        parts = urlsplit(str(url).strip())
        path = re.sub(r"/{2,}", "/", parts.path).rstrip("/") or "/"
        return urlunsplit((parts.scheme.casefold(), parts.netloc.casefold(), path, "", ""))

    @staticmethod
    def parse_date(value: object) -> datetime | None:
        text = re.sub(r"\s+", " ", str(value or "")).strip()
        if not text:
            return None
        relative = re.search(r"\b(\d+)\s+(day|hour|minute)s?\s+ago\b", text, re.I)
        if relative:
            amount = int(relative.group(1))
            unit = relative.group(2).casefold()
            delta = {
                "day": timedelta(days=amount),
                "hour": timedelta(hours=amount),
                "minute": timedelta(minutes=amount),
            }[unit]
            return datetime.now(timezone.utc) - delta
        text = re.sub(r"\b(\d{1,2})(?:st|nd|rd|th)\b", r"\1", text, flags=re.I)
        prefixes = ("Article posted on ", "Last Updated on ")
        for prefix in prefixes:
            if prefix.casefold() in text.casefold():
                position = text.casefold().rfind(prefix.casefold())
                text = text[position + len(prefix):].strip()
        for pattern in (
            "%A, %B %d, %Y", "%A %d %B %Y", "%d %B %Y",
            "%B %d, %Y", "%d %b %Y", "%Y-%m-%d",
            "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S",
        ):
            try:
                return CouncilSourceScraper._utc(datetime.strptime(text, pattern))
            except ValueError:
                continue
        embedded_patterns = (
            r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)[, ]+"
            r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
            r"\s+\d{1,2},\s+\d{4}",
            r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+"
            r"\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}",
            r"\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}",
            r"(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}",
        )
        for expression in embedded_patterns:
            match = re.search(expression, text, re.I)
            if match and match.group(0) != text:
                return CouncilSourceScraper.parse_date(match.group(0))
        return None

    @staticmethod
    def _utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @staticmethod
    def _text(node: Tag | None) -> str:
        return re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip() if node else ""

    @staticmethod
    def _text_with_links(node: Tag | None, base_url: str) -> str:
        """Extract readable text and retain useful links embedded in a block."""

        if node is None:
            return ""
        text = CouncilSourceScraper._text(node)
        text = re.sub(r"\s+([.,;:!?])", r"\1", text)
        links: list[str] = []
        for anchor in node.select("a[href]"):
            href = str(anchor.get("href") or "").strip()
            if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
                continue
            absolute = urljoin(base_url, href)
            if absolute.casefold() not in text.casefold() and absolute not in links:
                links.append(absolute)
        return f"{text} {' '.join(links)}".strip()


__all__ = [
    "CouncilCandidate", "CouncilSource", "CouncilSourceHealth",
    "CouncilSourceScraper", "DEFAULT_MAX_AGE_DAYS", "load_council_config",
]
