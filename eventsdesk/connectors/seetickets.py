from __future__ import annotations

import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup

from ..base import BaseConnector
from ..html_utils import parse_datetime
from ..models import EventRecord


MIDLANDS_TERMS = {
    'nottingham','nottinghamshire','derby','derbyshire','leicester','leicestershire',
    'lincoln','lincolnshire','northampton','northamptonshire','birmingham','coventry',
    'warwick','warwickshire','stratford-upon-avon','wolverhampton','walsall','dudley',
    'sandwell','stoke-on-trent','stoke','stafford','staffordshire','worcester','worcestershire',
    'shrewsbury','shropshire','telford','hereford','herefordshire','solihull','tamworth',
    'lichfield','burton','chesterfield','mansfield','newark','worksop','retford','rugby',
    'nuneaton','leamington','kettering','corby','wellingborough','malvern','kidderminster',
}

_DATE = re.compile(
    r'(?P<date>(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)(?:day)?\s+' 
    r'\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]{3,9}\s+\d{4}'
    r'(?:\s*,?\s*\d{1,2}:\d{2}(?:\s*[AP]M)?)?)', re.I
)


class SeeTicketsMidlandsConnector(BaseConnector):
    """Harvest See Tickets' public Event Finder and retain Midlands results.

    The Event Finder is server-rendered and paginated. We crawl a bounded number
    of result pages and keep events whose visible venue/location text contains a
    Midlands place term. This deliberately avoids checkout/account pages.
    """

    source_name = 'see_tickets'
    SEARCH_ROOT = 'https://purchase.seetickets.com/search/{page}?lang=en-GB'

    def __init__(self, url: str | None = None, *, source_name: str = 'See Tickets',
                 source_rank: int = 35, max_pages: int = 100, terms: set[str] | None = None,
                 **kwargs):
        super().__init__(**kwargs)
        self.url = url or self.SEARCH_ROOT.format(page=1)
        self.source_name = source_name
        self.source_rank = source_rank
        self.max_pages = max(1, max_pages)
        self.terms = {x.casefold() for x in (terms or MIDLANDS_TERMS)}

    def fetch(self) -> list[EventRecord]:
        out: list[EventRecord] = []
        seen_urls: set[str] = set()
        for page in range(1, self.max_pages + 1):
            url = self.SEARCH_ROOT.format(page=page)
            html = self.get(url).text
            events = self.parse_page(html, url)
            if not events:
                # Page 1 can legitimately require a filter; later empty pages end pagination.
                if page > 1:
                    break
                continue
            new = 0
            for event in events:
                key = event.event_url or f'{event.title}|{event.start}'
                if key not in seen_urls:
                    seen_urls.add(key); out.append(event); new += 1
            if new == 0 and page > 1:
                break
        return self.normalize(out)

    def parse_page(self, html: str, base_url: str) -> list[EventRecord]:
        soup = BeautifulSoup(html, 'html.parser')
        out: list[EventRecord] = []
        for link in soup.find_all('a', href=True):
            href = str(link.get('href') or '')
            if '/event/' not in href and '/rd/event/' not in href:
                continue
            title = link.get_text(' ', strip=True)
            if not title or title.casefold() in {'find tickets','tickets','more info'}:
                # Event title is often in a nearby heading rather than the booking link.
                parent = link.find_parent(['li','article','div'])
                heading = parent.find(['h2','h3','h4']) if parent else None
                title = heading.get_text(' ', strip=True) if heading else title
            parent = link.find_parent(['li','article','div'])
            text = parent.get_text(' ', strip=True) if parent else link.parent.get_text(' ', strip=True)
            if not self._is_midlands(text):
                continue
            m = _DATE.search(text)
            start = parse_datetime(m.group('date')) if m else None
            if not start:
                continue
            absolute = urljoin(base_url, href)
            venue = self._venue_from_text(text, title)
            out.append(EventRecord(
                source=self.source_name,
                source_event_id=absolute,
                title=title.strip(),
                start=start,
                venue=venue,
                event_url=absolute,
                ticket_url=absolute,
                source_rank=self.source_rank,
                raw={'listing_text': text, 'page': base_url},
            ))
        return self._unique(out)

    def _is_midlands(self, text: str) -> bool:
        folded = text.casefold()
        return any(term in folded for term in self.terms)

    def _venue_from_text(self, text: str, title: str) -> str | None:
        # Conservative: strip title/date and return short residual prefix only when useful.
        cleaned = text.replace(title, ' ', 1)
        cleaned = _DATE.sub(' ', cleaned)
        cleaned = re.sub(r'\b(?:Find Tickets|On Sale Soon|Sold Out|Artists?:.*?)\b', ' ', cleaned, flags=re.I)
        cleaned = ' '.join(cleaned.split()).strip(' -–—,|')
        return cleaned[:180] or None

    @staticmethod
    def _unique(events: list[EventRecord]) -> list[EventRecord]:
        seen = set(); out = []
        for e in events:
            key = (e.event_url, e.start.isoformat() if e.start else '')
            if key not in seen:
                seen.add(key); out.append(e)
        return out
