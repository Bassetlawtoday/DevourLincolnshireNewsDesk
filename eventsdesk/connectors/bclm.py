from __future__ import annotations

import re
from bs4 import BeautifulSoup, Tag
from urllib.parse import urljoin

from ..base import BaseConnector
from ..html_utils import parse_datetime
from ..models import EventRecord

_DATE = re.compile(
    r"(?:Mon(?:day)?|Tue(?:sday)?|Wed(?:nesday)?|Thu(?:rsday)?|Fri(?:day)?|Sat(?:urday)?|Sun(?:day)?)?\s*"
    r"(\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"(?:\s+(20\d{2}))?"
    r"",
    re.I,
)
_FULL_RANGE = re.compile(
    r"(\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"(?:\s+(20\d{2}))?\s*[-–—]\s*"
    r"(\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+(20\d{2})",
    re.I,
)

_RANGE = re.compile(
    r"(\d{1,2})(?:st|nd|rd|th)?\s*[-–—]\s*(\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+(20\d{2})",
    re.I,
)


class BlackCountryLivingMuseumConnector(BaseConnector):
    """Black Country Living Museum event calendar.

    The public calendar is server rendered and paginated. Individual cards may
    contain one date, a genuine multi-day range, or several explicit sessions.
    Explicit repeated dates are emitted as separate occurrences; true ranges
    remain one event record.
    """

    source_name = "Black Country Living Museum"

    def __init__(self, url: str, *, source_name: str = source_name, source_rank: int = 15,
                 area: str | None = "Dudley", max_pages: int = 4, **kwargs):
        super().__init__(**kwargs)
        self.url = url
        self.source_name = source_name
        self.source_rank = source_rank
        self.area = area
        self.max_pages = max_pages

    def fetch(self) -> list[EventRecord]:
        all_events: list[EventRecord] = []
        for page in range(1, self.max_pages + 1):
            sep = "&" if "?" in self.url else "?"
            page_url = f"{self.url}{sep}p={page}"
            response = self.get(page_url)
            events = self.parse_page(response.text, page_url=page_url)
            if not events:
                if page > 1:
                    break
            all_events.extend(events)
            # Current calendar exposes only a small number of numbered pages.
            soup = BeautifulSoup(response.text, "html.parser")
            if page > 1 and not self._has_next_page(soup, page + 1):
                break
        return self.normalize(self._unique(all_events))

    def parse_page(self, html: str, *, page_url: str | None = None) -> list[EventRecord]:
        soup = BeautifulSoup(html, "html.parser")
        out: list[EventRecord] = []
        # Prefer cards/entries around headings. The site uses numbered calendar
        # entries but this remains tolerant of theme/CMS class changes.
        for heading in soup.find_all(["h3", "h4"]):
            title = heading.get_text(" ", strip=True)
            if not title or title.casefold() in {"what's on", "featured event", "full events calendar"}:
                continue
            container = self._container_for(heading)
            text = container.get_text(" ", strip=True) if container else heading.parent.get_text(" ", strip=True)
            link = heading.find("a", href=True) or (container.find("a", href=True) if container else None)
            href = urljoin(page_url or self.url, link.get("href")) if link and link.get("href") else None
            dates = self._extract_dates(text)
            if not dates:
                continue
            series_key = f"{self.source_name}:{href or title.casefold()}"
            for index, start in enumerate(dates):
                out.append(EventRecord(
                    source=self.source_name,
                    source_event_id=f"{href or title}#{index + 1}" if len(dates) > 1 else (href or title),
                    title=title,
                    start=start,
                    venue=self.source_name,
                    town="Dudley",
                    county=self.area,
                    event_url=href,
                    ticket_url=href,
                    source_rank=self.source_rank,
                    series_key=series_key if len(dates) > 1 else None,
                    occurrence_key=f"{series_key}:{start.isoformat()}" if len(dates) > 1 else None,
                    raw={"calendar": "bclm", "explicit_occurrences": len(dates) > 1},
                ))
        return self._unique(out)

    @staticmethod
    def _container_for(heading: Tag) -> Tag | None:
        for parent in heading.parents:
            if not isinstance(parent, Tag):
                continue
            if parent.name in {"li", "article"}:
                return parent
            cls = " ".join(parent.get("class", []))
            if "event" in cls.casefold() or "card" in cls.casefold():
                return parent
        return heading.parent if isinstance(heading.parent, Tag) else None

    @staticmethod
    def _extract_dates(text: str):
        # Preserve genuine ranges as a single start date. Multiple separate
        # bullet/session dates become independent occurrences.
        full = _FULL_RANGE.search(text)
        if full:
            year = full.group(3) or full.group(6)
            dt = parse_datetime(f"{full.group(1)} {full.group(2)} {year}")
            return [dt] if dt else []
        r = _RANGE.search(text)
        if r:
            dt = parse_datetime(f"{r.group(1)} {r.group(3)} {r.group(4)}")
            return [dt] if dt else []
        matches = list(_DATE.finditer(text))
        if not matches:
            return []
        explicit_years = [m.group(3) for m in matches if m.group(3)]
        fallback_year = explicit_years[-1] if explicit_years else None
        dates = []
        seen = set()
        for m in matches:
            year = m.group(3) or fallback_year
            if not year:
                continue
            raw = f"{m.group(1)} {m.group(2)} {year}"
            # Start time is deliberately not appended here because the generic
            # datetime parser is inconsistent across strings such as 9.30pm.
            dt = parse_datetime(raw)
            if dt and dt.isoformat() not in seen:
                seen.add(dt.isoformat())
                dates.append(dt)
        return dates

    @staticmethod
    def _has_next_page(soup: BeautifulSoup, page: int) -> bool:
        return any(a.get_text(" ", strip=True) == str(page) for a in soup.find_all("a"))

    @staticmethod
    def _unique(events: list[EventRecord]) -> list[EventRecord]:
        seen = set()
        out = []
        for event in events:
            key = (event.title.casefold(), event.start.isoformat(), event.event_url or "")
            if key not in seen:
                seen.add(key)
                out.append(event)
        return out
