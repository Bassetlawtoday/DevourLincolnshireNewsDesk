"""HTTP collectors for the three official Council Intelligence sources."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import re
from time import perf_counter
from urllib.parse import urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup, Tag
import requests

from newsdesk.story import Story


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "council.json"
DEFAULT_MAX_AGE_DAYS = 14
USER_AGENT = "NewsDeskPro-Council/1.0 (+https://www.bassetlawtoday.com/)"


@dataclass(frozen=True, slots=True)
class CouncilSource:
    key: str
    name: str
    url: str
    enabled: bool = True


@dataclass(slots=True)
class CouncilCandidate:
    title: str
    url: str
    published_at: datetime
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
    direct_bassetlaw_matches: int = 0
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
                    if candidate.published_at < cutoff:
                        page_has_old_story = True
                        continue
                    if candidate.published_at > current + timedelta(days=1):
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
                    stories.append(story)
                if page_has_old_story or not discovered_next:
                    break
                next_url = discovered_next
            health.articles_retained = len(stories)
            health.successful = True
        except Exception as error:
            health.failures.append(str(error)[:300])
        finally:
            health.duration_seconds = perf_counter() - started
        return stories, health

    def _request(self, url: str) -> tuple[str, str]:
        if not self._same_source_url(url):
            raise ValueError(f"Refusing off-source Council URL: {url}")
        response = self.session.get(
            url,
            timeout=self.config["request_timeout_seconds"],
        )
        response.raise_for_status()
        if not self._same_source_url(response.url):
            raise ValueError(f"Council source redirected off-site: {response.url}")
        return response.text, response.url

    def parse_listing(
        self, html: str, page_url: str | None = None
    ) -> tuple[list[CouncilCandidate], str | None]:
        soup = BeautifulSoup(html, "html.parser")
        base_url = page_url or self.source.url
        parser = {
            "bassetlaw_district_council": self._parse_bassetlaw_listing,
            "nottinghamshire_county_council": self._parse_nottinghamshire_listing,
            "east_midlands_cca": self._parse_emcca_listing,
        }.get(self.source.key)
        if parser is None:
            raise ValueError(f"Unsupported Council source: {self.source.key}")
        return parser(soup, base_url)

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
        if self.source.key == "bassetlaw_district_council":
            content = soup.select_one("main .content")
        elif self.source.key == "nottinghamshire_county_council":
            content = soup.select_one("main article")
        else:
            content = soup.select_one(".c-editable")
        if content is None:
            raise ValueError("article content not found")
        paragraphs = []
        for node in content.select("p"):
            text = self._text(node)
            lowered = text.casefold()
            if text and "last updated on" not in lowered and text != "<END>":
                paragraphs.append(text)
        body = "\n\n".join(dict.fromkeys(paragraphs))
        if not body:
            raise ValueError("article body is empty")
        title = self._text(soup.select_one("h1")) or candidate.title
        summary = candidate.summary
        if not summary:
            summary = self._text(soup.select_one(".lede")) or paragraphs[0]
        image = content.select_one("img[src]") or soup.select_one(
            "meta[property='og:image'][content]"
        )
        image_url = candidate.image_url
        image_alt = candidate.image_alt_text
        if image is not None:
            source_value = image.get("src") or image.get("content")
            if source_value:
                image_url = urljoin(resolved_url, source_value)
            image_alt = str(image.get("alt", image_alt)).strip()
        collected_at = datetime.now(timezone.utc).isoformat()
        return Story(
            title=title,
            summary=summary,
            body=body,
            source=self.source.name,
            url=self.canonical_url(resolved_url),
            published=candidate.published_at.isoformat(),
            image_url=image_url,
            image_caption=image_alt,
            image_credit=self.source.name,
            image_alt_text=image_alt,
            scraped_at=collected_at,
            extras={"source_key": self.source.key, "collected_at": collected_at},
        )

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
        text = re.sub(r"\b(\d{1,2})(?:st|nd|rd|th)\b", r"\1", text, flags=re.I)
        prefixes = ("Article posted on ", "Last Updated on ")
        for prefix in prefixes:
            if prefix.casefold() in text.casefold():
                position = text.casefold().rfind(prefix.casefold())
                text = text[position + len(prefix):].strip()
        for pattern in (
            "%A, %B %d, %Y", "%A %d %B %Y", "%d %B %Y",
            "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S",
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


__all__ = [
    "CouncilCandidate", "CouncilSource", "CouncilSourceHealth",
    "CouncilSourceScraper", "DEFAULT_MAX_AGE_DAYS", "load_council_config",
]
