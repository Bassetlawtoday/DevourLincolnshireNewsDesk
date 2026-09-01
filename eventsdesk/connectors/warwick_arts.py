from __future__ import annotations

import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup, Tag

from .structured_html import StructuredHtmlConnector, _start_from_text
from ..models import EventRecord


class WarwickArtsCentreConnector(StructuredHtmlConnector):
    """First-party Warwick Arts Centre live-events listing parser."""

    def parse_cards(self, html: str) -> list[EventRecord]:
        soup = BeautifulSoup(html, "html.parser")
        out: list[EventRecord] = []
        for heading in soup.find_all(["h2", "h3"]):
            link = heading.find("a", href=True)
            if not link:
                continue
            title = " ".join(link.get_text(" ", strip=True).split())
            if not self._plausible_title(title):
                continue
            start = None
            context = None
            node: Tag | None = heading
            for _ in range(6):
                node = node.parent if isinstance(node, Tag) else None
                if not isinstance(node, Tag):
                    break
                start = _start_from_text(node.get_text(" ", strip=True))
                if start:
                    context = node
                    break
            if not start:
                continue
            href = urljoin(self.url, str(link.get("href")))
            event = EventRecord(source=self.source_name, source_event_id=href, title=title, start=start, county=self.area, event_url=href, ticket_url=href, source_rank=self.source_rank, raw={"fallback": "warwick-heading-date"})
            if context is not None:
                self._enrich_from_node(event, context)
            out.append(event)
        if out:
            return self._unique(out)
        generic = super().parse_cards(html)
        if generic:
            return generic
        for link in soup.find_all("a", href=True):
            raw_title = " ".join(link.get_text(" ", strip=True).split())
            m = re.match(r"find\s+out\s+more\s*[-–—:]\s*(.+)$", raw_title, re.I)
            if not m:
                continue
            title = m.group(1).strip()
            if not self._plausible_title(title):
                continue
            start = None
            node: Tag | None = link
            for _ in range(7):
                node = node.parent if isinstance(node, Tag) else None
                if not isinstance(node, Tag):
                    break
                start = _start_from_text(node.get_text(" ", strip=True))
                if start:
                    break
            if not start:
                continue
            href = urljoin(self.url, str(link.get("href")))
            out.append(EventRecord(source=self.source_name, source_event_id=href, title=title, start=start, county=self.area, event_url=href, ticket_url=href, source_rank=self.source_rank, raw={"fallback": "warwick-find-out-more"}))
        return self._unique(out)
