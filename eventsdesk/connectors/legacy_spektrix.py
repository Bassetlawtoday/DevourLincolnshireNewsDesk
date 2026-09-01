from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urljoin, urlparse, parse_qs

from bs4 import BeautifulSoup

from ..base import BaseConnector
from ..models import EventRecord
from ..event_quality import is_cta_title

_MONTH_SELECT = re.compile(r"MonthSelect=(20\d{2})(\d{1,2})", re.I)
_DISPLAY_RANGE = re.compile(r"Displaying events between\s+\d{1,2}\s+([A-Za-z]+)\s+(20\d{2})", re.I)
_DAY_RE = re.compile(r"\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+(\d{1,2})\b", re.I)

_MONTHS = {
    'january': 1, 'february': 2, 'march': 3, 'april': 4, 'may': 5, 'june': 6,
    'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11, 'december': 12,
}

_EXCLUDE = {
    'ticket protection', 'watchword glasses',
}


class LegacySpektrixEventListConnector(BaseConnector):
    """Parser for older Spektrix ``website/EventList.aspx`` catalogues.

    These pages expose a month selector plus rows in the form
    ``TITLE Dates: Thu 20, Fri 21``.  The month/year belongs to the selected
    catalogue page rather than each event row, so a generic event-card parser
    cannot safely reconstruct dates.  This connector follows a bounded number
    of month links and creates one occurrence per listed day.
    """

    source_name = 'legacy_spektrix'

    def __init__(self, url: str, *, source_name: str, source_rank: int = 10,
                 area: str | None = None, max_months: int = 12, **kwargs):
        super().__init__(**kwargs)
        self.url = url
        self.source_name = source_name
        self.source_rank = source_rank
        self.area = area
        self.max_months = max_months

    def fetch(self) -> list[EventRecord]:
        first = self.get(self.url).text
        month_urls = self._month_urls(first)
        pages = [(self.url, first)]
        seen = {self.url}
        for url in month_urls[: self.max_months]:
            if url in seen:
                continue
            seen.add(url)
            pages.append((url, self.get(url).text))
        events: list[EventRecord] = []
        for url, html in pages:
            events.extend(self.parse_page(html, page_url=url))
        return self.normalize(self._unique(events))

    def _month_urls(self, html: str) -> list[str]:
        soup = BeautifulSoup(html, 'html.parser')
        out = []
        for a in soup.find_all('a', href=True):
            href = str(a.get('href'))
            if 'MonthSelect=' not in href:
                continue
            out.append(urljoin(self.url, href))
        return out

    def parse_page(self, html: str, *, page_url: str | None = None) -> list[EventRecord]:
        page_url = page_url or self.url
        soup = BeautifulSoup(html, 'html.parser')
        year, month = self._page_year_month(soup.get_text(' ', strip=True), page_url)
        if not year or not month:
            return []
        out: list[EventRecord] = []
        for a in soup.find_all('a', href=True):
            title = ' '.join(a.get_text(' ', strip=True).split())
            if not title or title.casefold() in _EXCLUDE or is_cta_title(title):
                continue
            parent_text = ' '.join((a.parent.get_text(' ', strip=True) if a.parent else '').split())
            if 'Dates:' not in parent_text:
                # On some templates the date text is in the next sibling.
                nxt = a.next_sibling
                sibling_text = str(nxt).strip() if nxt is not None else ''
                combined = f'{parent_text} {sibling_text}'.strip()
            else:
                combined = parent_text
            if 'Dates:' not in combined:
                continue
            dates_text = combined.split('Dates:', 1)[1]
            days = [int(x) for x in _DAY_RE.findall(dates_text)]
            if not days:
                continue
            event_url = urljoin(page_url, str(a.get('href')))
            event_id = self._event_id(event_url) or event_url
            for day in days:
                try:
                    start = datetime(year, month, day)
                except ValueError:
                    continue
                out.append(EventRecord(
                    source=self.source_name,
                    source_event_id=f'{event_id}:{start.date().isoformat()}',
                    title=title,
                    start=start,
                    county=self.area,
                    event_url=event_url,
                    ticket_url=event_url,
                    source_rank=self.source_rank,
                    series_key=f'{self.source_name}:{event_id}',
                    occurrence_key=f'{self.source_name}:{event_id}:{start.date().isoformat()}',
                    raw={'fallback': 'legacy-spektrix-eventlist', 'catalogue_url': page_url},
                ))
        return out

    @staticmethod
    def _page_year_month(text: str, page_url: str) -> tuple[int | None, int | None]:
        m = _MONTH_SELECT.search(page_url)
        if m:
            return int(m.group(1)), int(m.group(2))
        m = _DISPLAY_RANGE.search(text)
        if m:
            return int(m.group(2)), _MONTHS.get(m.group(1).casefold())
        return None, None

    @staticmethod
    def _event_id(url: str) -> str | None:
        q = parse_qs(urlparse(url).query)
        for key in ('resize', 'EventId', 'eventid', 'EventID', 'id'):
            if q.get(key):
                return str(q[key][0])
        return None

    @staticmethod
    def _unique(events: list[EventRecord]) -> list[EventRecord]:
        seen = set()
        out = []
        for e in events:
            key = (e.title.casefold(), e.start.isoformat() if e.start else '', e.event_url or '')
            if key in seen:
                continue
            seen.add(key)
            out.append(e)
        return out
