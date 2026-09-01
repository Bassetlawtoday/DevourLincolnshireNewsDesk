from __future__ import annotations

from urllib.parse import urljoin
from bs4 import BeautifulSoup

from ..html_utils import parse_datetime
from ..models import EventRecord
from .structured_html import StructuredHtmlConnector


class RockCityConnector(StructuredHtmlConnector):
    """Rock City Nottingham gig guide connector."""

    def parse_cards(self, html: str) -> list[EventRecord]:
        soup = BeautifulSoup(html, "html.parser")
        out: list[EventRecord] = []
        for card in soup.find_all(["article", "li", "div"]):
            heading = card.find(["h2", "h3", "h4"])
            link = card.find("a", href=True)
            if not heading or not link:
                continue
            href = link.get("href")
            if not href:
                continue
            text = card.get_text(" | ", strip=True)
            if not any(k in text.casefold() for k in ["doors", "tickets", "support", "sold out"]):
                continue
            time_el = card.find("time")
            date_text = time_el.get("datetime") if time_el and time_el.has_attr("datetime") else (time_el.get_text(" ", strip=True) if time_el else None)
            out.append(EventRecord(
                source=self.source_name,
                source_event_id=urljoin(self.url, href),
                title=heading.get_text(" ", strip=True),
                start=parse_datetime(date_text),
                venue="Rock City",
                town="Nottingham",
                event_url=urljoin(self.url, href),
                ticket_url=urljoin(self.url, href),
                status="sold_out" if "sold out" in text.casefold() else None,
                source_rank=self.source_rank,
                raw={"card_text": text},
            ))
        seen, unique = set(), []
        for e in out:
            if e.event_url not in seen:
                seen.add(e.event_url); unique.append(e)
        return unique
