from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

from ..base import BaseConnector
from ..html_utils import parse_datetime
from ..models import EventRecord


class PazazProjectsConnector(BaseConnector):
    """Connector for PAZAZ dynamic arts/event sites.

    PAZAZ sites expose project objects to the browser and use project fields such
    as ``project_name`` and ``project_startdate_large``. Deployments differ, so
    the connector probes a small set of first-party project endpoints and only
    accepts JSON-shaped responses. No browser automation is required.
    """

    source_name = "pazaz_projects"
    endpoint_candidates = (
        "/api/projects",
        "/api/projects?page=1",
        "/api/projects?limit=500",
        "/api/whats-on",
        "/api/events",
    )

    def __init__(self, base_url: str, *, source_name: str, source_rank: int = 12,
                 area: str | None = None, **kwargs):
        super().__init__(**kwargs)
        self.base_url = base_url.rstrip("/") + "/"
        self.source_name = source_name
        self.source_rank = source_rank
        self.area = area

    def fetch(self) -> list[EventRecord]:
        errors: list[str] = []
        for suffix in self.endpoint_candidates:
            url = urljoin(self.base_url, suffix.lstrip("/"))
            try:
                response = self.get(url)
                data = response.json()
            except Exception as exc:
                errors.append(f"{url}: {type(exc).__name__}")
                continue
            rows = self._rows(data)
            if rows:
                events = [e for row in rows if (e := self._event(row, url))]
                if events:
                    return self.normalize(events)
        raise RuntimeError("No validated PAZAZ project endpoint produced events; " + "; ".join(errors[-3:]))

    @staticmethod
    def _rows(data: Any) -> list[dict]:
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
        if isinstance(data, dict):
            for key in ("projects", "results", "data", "items", "events"):
                value = data.get(key)
                if isinstance(value, list):
                    return [x for x in value if isinstance(x, dict)]
                if isinstance(value, dict):
                    for nested in ("projects", "results", "items"):
                        rows = value.get(nested)
                        if isinstance(rows, list):
                            return [x for x in rows if isinstance(x, dict)]
        return []

    def _event(self, row: dict, endpoint: str) -> EventRecord | None:
        title = row.get("project_name") or row.get("name") or row.get("title")
        raw_start = row.get("project_startdate_large") or row.get("startDate") or row.get("start_date") or row.get("date")
        start = parse_datetime(raw_start)
        if not title or not start:
            return None
        slug = row.get("project_slug") or row.get("slug")
        href = row.get("project_url") or row.get("url")
        if href:
            href = urljoin(self.base_url, str(href))
        elif slug:
            href = urljoin(self.base_url, f"whats-on/{slug}/about")
        else:
            href = self.base_url
        venue = row.get("venue_name") or row.get("venue") or row.get("microsite_name")
        return EventRecord(
            source=self.source_name,
            source_event_id=str(row.get("project_id") or row.get("id") or href),
            title=str(title),
            start=start,
            venue=str(venue) if venue else None,
            county=self.area,
            event_url=href,
            ticket_url=href,
            image_url=row.get("project_image") or row.get("image"),
            price_text=row.get("project_price") or row.get("price"),
            source_rank=self.source_rank,
            raw={"endpoint": endpoint, "pazaz_project": row},
        )
