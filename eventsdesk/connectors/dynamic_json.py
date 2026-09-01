from __future__ import annotations

from typing import Any, Callable, Iterable

from ..base import BaseConnector
from ..models import EventRecord


JsonExtractor = Callable[[dict[str, Any]], EventRecord | None]


class JsonEventsConnector(BaseConnector):
    """Reusable connector for dynamic event-search JSON/XHR endpoints.

    The endpoint and row-to-EventRecord mapping are configuration, allowing
    councils and other dynamic sites to share the same transport/pagination
    implementation once their public XHR endpoint has been identified.
    """

    source_name = "json_events"

    def __init__(self, endpoint: str, *, source_name: str, extractor: JsonExtractor,
                 params: dict[str, Any] | None = None, items_path: tuple[str, ...] = ("items",),
                 page_param: str | None = None, start_page: int = 1, max_pages: int = 20,
                 source_rank: int = 25, **kwargs):
        super().__init__(**kwargs)
        self.endpoint = endpoint
        self.source_name = source_name
        self.extractor = extractor
        self.params = dict(params or {})
        self.items_path = items_path
        self.page_param = page_param
        self.start_page = start_page
        self.max_pages = max_pages
        self.source_rank = source_rank

    def fetch(self) -> list[EventRecord]:
        out: list[EventRecord] = []
        page = self.start_page
        for _ in range(self.max_pages):
            params = dict(self.params)
            if self.page_param:
                params[self.page_param] = page
            payload = self.get(self.endpoint, params=params).json()
            items = self._items(payload)
            if not items:
                break
            before = len(out)
            for item in items:
                if not isinstance(item, dict):
                    continue
                record = self.extractor(item)
                if record is not None:
                    if record.source_rank == 50:
                        record.source_rank = self.source_rank
                    out.append(record)
            if not self.page_param or len(out) == before:
                break
            page += 1
        return self.normalize(out)

    def _items(self, payload: Any) -> Iterable[Any]:
        current = payload
        for key in self.items_path:
            if not isinstance(current, dict):
                return []
            current = current.get(key)
        return current if isinstance(current, list) else []
