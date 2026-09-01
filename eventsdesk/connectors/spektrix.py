from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

from ..base import BaseConnector
from ..html_utils import parse_datetime
from ..models import EventRecord


class SpektrixConnector(BaseConnector):
    """Public Spektrix API v3 event connector.

    Spektrix Web/Public API endpoints expose public event data without
    authentication. A venue-specific Spektrix client name is required.
    """

    source_name = "spektrix"

    def __init__(self, client_name: str, *, source_name: str, source_rank: int = 12,
                 system_host: str = "https://system.spektrix.com", **kwargs):
        super().__init__(**kwargs)
        if not client_name or not client_name.strip():
            raise ValueError("Spektrix client_name is required")
        self.client_name = client_name.strip()
        self.source_name = source_name
        self.source_rank = source_rank
        self.base_url = f"{system_host.rstrip('/')}/{self.client_name}/api/v3"

    def fetch(self) -> list[EventRecord]:
        # Public v3 events are available without authentication. Instances are
        # fetched explicitly when they are not embedded in the event payload.
        response = self.get(f"{self.base_url}/events")
        payload = response.json()
        items = payload if isinstance(payload, list) else payload.get("items") or payload.get("results") or []
        hydrated: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            row = dict(item)
            instances = row.get("instances") or row.get("Instances")
            event_id = row.get("id") or row.get("Id")
            if not isinstance(instances, list) and event_id:
                try:
                    ir = self.get(f"{self.base_url}/events/{event_id}/instances")
                    ip = ir.json()
                    instances = ip if isinstance(ip, list) else ip.get("items") or ip.get("results") or []
                except Exception:
                    instances = []
                row["instances"] = instances
            hydrated.append(row)
        return self.normalize(self._parse_events(hydrated))

    def _parse_events(self, items: list[dict[str, Any]]) -> list[EventRecord]:
        out: list[EventRecord] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            event_id = item.get("id") or item.get("Id")
            title = item.get("name") or item.get("Name") or item.get("title") or item.get("Title")
            if not title:
                continue
            instances = item.get("instances") or item.get("Instances") or []
            if not isinstance(instances, list):
                instances = []
            if not instances:
                out.append(self._record(item, event_id, title, None))
                continue
            for instance in instances:
                if isinstance(instance, dict):
                    out.append(self._record(item, event_id, title, instance))
        return out

    def _record(self, item: dict[str, Any], event_id: Any, title: str,
                instance: dict[str, Any] | None) -> EventRecord:
        instance = instance or {}
        instance_id = instance.get("id") or instance.get("Id")
        start = (
            instance.get("start") or instance.get("Start") or instance.get("startTime")
            or instance.get("StartTime") or item.get("start") or item.get("Start")
        )
        end = instance.get("end") or instance.get("End") or instance.get("endTime") or instance.get("EndTime")
        venue_obj = instance.get("venue") or item.get("venue") or {}
        if not isinstance(venue_obj, dict):
            venue_obj = {}
        plan_obj = instance.get("plan") or {}
        if not isinstance(plan_obj, dict):
            plan_obj = {}
        image = item.get("imageUrl") or item.get("ImageUrl") or item.get("image")
        web_url = item.get("webUrl") or item.get("WebUrl") or item.get("url") or item.get("Url")
        if not web_url and event_id:
            web_url = f"https://tickets.{self.client_name}.com/events/{event_id}"
        description = item.get("description") or item.get("Description") or item.get("html") or item.get("Html")
        return EventRecord(
            source=self.source_name,
            source_event_id=str(instance_id or event_id) if (instance_id or event_id) is not None else None,
            title=str(title),
            start=parse_datetime(start),
            end=parse_datetime(end),
            venue=venue_obj.get("name") or venue_obj.get("Name"),
            room=plan_obj.get("name") or plan_obj.get("Name"),
            category=item.get("type") or item.get("Type") or item.get("genre") or item.get("Genre"),
            description=str(description) if description else None,
            image_url=urljoin(self.base_url, str(image)) if image else None,
            event_url=str(web_url) if web_url else None,
            ticket_url=str(web_url) if web_url else None,
            status=instance.get("status") or instance.get("Status"),
            series_key=f"{self.source_name}:{event_id}" if event_id is not None else None,
            occurrence_key=(f"{self.source_name}:{event_id}:{instance_id}" if event_id is not None and instance_id is not None else None),
            source_rank=self.source_rank,
            raw={"event": item, "instance": instance},
        )
