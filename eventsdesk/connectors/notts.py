from __future__ import annotations

from datetime import date, timedelta
from urllib.parse import urlencode

from .structured_html import StructuredHtmlConnector
from ..models import EventRecord


class NottsEventsConnector(StructuredHtmlConnector):
    """Harvest Notts.com's high-volume Nottingham events catalogue in date windows.

    Date-window requests keep each result set bounded and avoid relying on an
    undocumented page-number parameter. The site publishes explicit date,
    venue, category, price and time text in server-rendered results.
    """

    def __init__(self, url: str = "https://notts.com/events/", *, source_name: str = "Notts.com",
                 window_days: int = 7, horizon_days: int = 365, source_rank: int = 28, **kwargs):
        super().__init__(url, source_name=source_name, source_rank=source_rank, area="Nottinghamshire", **kwargs)
        self.window_days = max(1, int(window_days))
        self.horizon_days = max(self.window_days, int(horizon_days))

    def fetch(self) -> list[EventRecord]:
        start = date.today()
        end_horizon = start + timedelta(days=self.horizon_days)
        out: list[EventRecord] = []
        cursor = start
        while cursor <= end_horizon:
            window_end = min(cursor + timedelta(days=self.window_days - 1), end_horizon)
            query = urlencode({"dateFrom": cursor.isoformat(), "dateTo": window_end.isoformat()})
            page_url = f"https://notts.com/events?{query}"
            html = self.get(page_url).text
            original = self.url
            self.url = page_url
            try:
                out.extend(self.parse_cards(html))
            finally:
                self.url = original
            cursor = window_end + timedelta(days=1)
        return self.normalize(self._unique(out))
