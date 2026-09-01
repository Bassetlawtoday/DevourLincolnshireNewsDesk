"""Chronological first-party Government and national announcement feeds."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import html
import json
import logging
import re
from typing import Callable
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

from .models import GovernmentAnnouncement


LOGGER = logging.getLogger(__name__)
TAG_PATTERN = re.compile(r"<[^>]+>")


@dataclass(frozen=True, slots=True)
class OfficialFeedSource:
    publisher: str
    endpoint: str
    source_type: str
    organisation_slug: str = ""


@dataclass(slots=True)
class GovernmentFeedResult:
    announcements: list[GovernmentAnnouncement]
    attempted: int
    successful: int
    failures: list[str]


GOVUK_SEARCH = "https://www.gov.uk/api/search.json"
OFFICIAL_SOURCES = (
    OfficialFeedSource("Prime Minister's Office, 10 Downing Street", GOVUK_SEARCH, "GOV.UK Search API", "prime-ministers-office-10-downing-street"),
    OfficialFeedSource("Cabinet Office", GOVUK_SEARCH, "GOV.UK Search API", "cabinet-office"),
    OfficialFeedSource("Home Office", GOVUK_SEARCH, "GOV.UK Search API", "home-office"),
    OfficialFeedSource("Department for Environment, Food & Rural Affairs", GOVUK_SEARCH, "GOV.UK Search API", "department-for-environment-food-rural-affairs"),
    OfficialFeedSource("Department for Transport", GOVUK_SEARCH, "GOV.UK Search API", "department-for-transport"),
    OfficialFeedSource("Department of Health and Social Care", GOVUK_SEARCH, "GOV.UK Search API", "department-of-health-and-social-care"),
    OfficialFeedSource("Environment Agency", GOVUK_SEARCH, "GOV.UK Search API", "environment-agency"),
    OfficialFeedSource("UK Health Security Agency", GOVUK_SEARCH, "GOV.UK Search API", "uk-health-security-agency"),
    OfficialFeedSource("Ofgem", "https://www.ofgem.gov.uk/rss.xml", "RSS"),
    OfficialFeedSource("Ofwat", "https://www.ofwat.gov.uk/feed/", "RSS"),
    OfficialFeedSource("NHS England", "https://www.england.nhs.uk/feed/", "RSS"),
)


class GovernmentFeedService:
    def __init__(
        self,
        sources: tuple[OfficialFeedSource, ...] = OFFICIAL_SOURCES,
        opener: Callable[..., object] = urlopen,
    ) -> None:
        self.sources = sources
        self.opener = opener

    def collect(
        self,
        *,
        hours: int = 48,
        now: datetime | None = None,
    ) -> GovernmentFeedResult:
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        cutoff = current.astimezone(timezone.utc) - timedelta(hours=hours)
        announcements: list[GovernmentAnnouncement] = []
        failures: list[str] = []
        successful = 0
        for source in self.sources:
            try:
                announcements.extend(self._collect_source(source))
                successful += 1
            except Exception as error:
                failures.append(f"{source.publisher}: {error}")
                LOGGER.warning("Government feed failed for %s: %s", source.publisher, error)
        retained = [
            item for item in announcements
            if cutoff <= item.published_at.astimezone(timezone.utc) <= current + timedelta(hours=24)
        ]
        return GovernmentFeedResult(
            announcements=self.deduplicate_and_sort(retained),
            attempted=len(self.sources), successful=successful, failures=failures,
        )

    def _collect_source(self, source: OfficialFeedSource) -> list[GovernmentAnnouncement]:
        if source.source_type == "GOV.UK Search API":
            query = urlencode({
                "filter_organisations": source.organisation_slug,
                "order": "-public_timestamp",
                "count": 100,
                "fields": "title,description,link,public_timestamp,content_id",
            })
            payload = self._request_json(f"{source.endpoint}?{query}")
            return [self._govuk_item(source.publisher, item) for item in payload.get("results", [])]
        return self._request_rss(source)

    def _request_json(self, url: str) -> dict:
        request = Request(url, headers={"User-Agent": "NewsDeskPro/1.0"})
        with self.opener(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))

    def _request_rss(self, source: OfficialFeedSource) -> list[GovernmentAnnouncement]:
        request = Request(source.endpoint, headers={"User-Agent": "NewsDeskPro/1.0"})
        with self.opener(request, timeout=20) as response:
            root = ET.fromstring(response.read())
        output = []
        for item in root.findall(".//item"):
            title = self._element_text(item, "title")
            link = self._element_text(item, "link")
            raw_date = self._element_text(item, "pubDate")
            if not title or not link or not raw_date:
                continue
            output.append(GovernmentAnnouncement(
                publisher=source.publisher,
                title=html.unescape(title.strip()),
                published_at=parsedate_to_datetime(raw_date).astimezone(timezone.utc),
                canonical_url=self._query_free_url(link.strip()),
                description=self._clean_description(self._element_text(item, "description")),
                content_id=self._element_text(item, "guid").strip(),
            ))
        return output

    @staticmethod
    def _govuk_item(publisher: str, item: dict) -> GovernmentAnnouncement:
        link = str(item.get("link") or "")
        if link.startswith("/"):
            link = f"https://www.gov.uk{link}"
        return GovernmentAnnouncement(
            publisher=publisher,
            title=str(item.get("title") or "").strip(),
            published_at=GovernmentFeedService._parse_datetime(str(item.get("public_timestamp") or "")),
            canonical_url=GovernmentFeedService._query_free_url(link),
            description=GovernmentFeedService._clean_description(str(item.get("description") or "")),
            content_id=str(item.get("content_id") or ""),
        )

    @staticmethod
    def _parse_datetime(value: str) -> datetime:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return (parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)

    @staticmethod
    def _element_text(item: ET.Element, name: str) -> str:
        child = item.find(name)
        return child.text if child is not None and child.text else ""

    @staticmethod
    def _clean_description(value: str) -> str:
        return " ".join(html.unescape(TAG_PATTERN.sub(" ", value)).split())[:300]

    @staticmethod
    def _query_free_url(value: str) -> str:
        parts = urlsplit(value)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))

    @staticmethod
    def deduplicate_and_sort(items: list[GovernmentAnnouncement]) -> list[GovernmentAnnouncement]:
        seen: set[tuple[str, str]] = set()
        output = []
        for item in sorted(items, key=lambda value: value.published_at, reverse=True):
            identifiers = {
                ("id", item.content_id) if item.content_id else ("url", item.canonical_url),
                ("url", GovernmentFeedService._query_free_url(item.canonical_url)),
                ("fallback", f"{item.publisher.casefold()}|{item.title.casefold()}|{item.published_at.isoformat()}"),
            }
            if seen.intersection(identifiers):
                continue
            seen.update(identifiers)
            output.append(item)
        return output
