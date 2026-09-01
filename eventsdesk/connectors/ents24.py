from __future__ import annotations

from .structured_html import StructuredHtmlConnector
from ..models import EventRecord


class Ents24MidlandsConnector(StructuredHtmlConnector):
    """Aggregate server-rendered Ents24 listings for the principal Midlands cities.

    Ents24 exposes city-specific What's On pages without requiring browser
    automation. We query a conservative city set and deduplicate the combined
    result; direct venue records still outrank Ents24 in the global deduper.
    """

    DEFAULT_CITIES = ("birmingham", "nottingham", "leicester", "wolverhampton", "stoke-on-trent")

    def __init__(self, url: str = "https://www.ents24.com/whatson", *, source_name: str = "Ents24",
                 cities: tuple[str, ...] | None = None, source_rank: int = 35, **kwargs):
        super().__init__(url, source_name=source_name, source_rank=source_rank, **kwargs)
        self.cities = tuple(cities or self.DEFAULT_CITIES)

    def fetch(self) -> list[EventRecord]:
        out: list[EventRecord] = []
        base = "https://www.ents24.com/whatson"
        for city in self.cities:
            page_url = f"{base}/{city}"
            html = self.get(page_url).text
            original = self.url
            self.url = page_url
            try:
                out.extend(self.parse_cards(html))
            finally:
                self.url = original
        return self.normalize(self._unique(out))
