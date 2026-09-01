from __future__ import annotations

from typing import Any

from ..base import BaseConnector, MissingCredentialError
from ..html_utils import parse_datetime
from ..models import EventRecord


class AllEventsApiConnector(BaseConnector):
    """Official AllEvents API connector.

    Access is commercial. The concrete subscription endpoint can vary by API
    product, so api_url is configurable. The mapper accepts common AllEvents
    response shapes and is ready for live validation once credentials are issued.
    """

    source_name = 'allevents'

    def __init__(self, api_key: str | None, *, api_url: str | None = None,
                 cities: list[str] | None = None, source_name: str = 'AllEvents.in',
                 source_rank: int = 45, **kwargs):
        super().__init__(**kwargs)
        self.api_key = api_key
        self.api_url = api_url
        self.cities = cities or ['Nottingham','Derby','Leicester','Lincoln','Birmingham','Coventry','Wolverhampton','Stoke-on-Trent','Worcester','Shrewsbury','Northampton']
        self.source_name = source_name
        self.source_rank = source_rank

    def fetch(self) -> list[EventRecord]:
        if not self.api_key:
            raise MissingCredentialError('AllEvents API key is required')
        if not self.api_url:
            raise MissingCredentialError('AllEvents API URL/product endpoint is required')
        out: list[EventRecord] = []
        for city in self.cities:
            payload = self.get(
                self.api_url,
                params={'city': city},
                headers={'Ocp-Apim-Subscription-Key': self.api_key, 'Accept': 'application/json'},
            ).json()
            rows = self._rows(payload)
            out.extend(self._map(row, city) for row in rows)
        return self.normalize(out)

    @staticmethod
    def _rows(payload: Any) -> list[dict]:
        if isinstance(payload, list): return [x for x in payload if isinstance(x, dict)]
        if not isinstance(payload, dict): return []
        for key in ('events','data','results','items'):
            value = payload.get(key)
            if isinstance(value, list): return [x for x in value if isinstance(x, dict)]
            if isinstance(value, dict):
                for nested in ('events','data','results','items'):
                    rows = value.get(nested)
                    if isinstance(rows, list): return [x for x in rows if isinstance(x, dict)]
        return []

    def _map(self, raw: dict, city_hint: str) -> EventRecord:
        venue = raw.get('venue') or raw.get('location') or {}
        if isinstance(venue, str): venue = {'name': venue}
        start = parse_datetime(raw.get('start_time') or raw.get('startDate') or raw.get('start_date') or raw.get('start'))
        end = parse_datetime(raw.get('end_time') or raw.get('endDate') or raw.get('end_date') or raw.get('end'))
        event_url = raw.get('event_url') or raw.get('url') or raw.get('link')
        return EventRecord(
            source=self.source_name,
            source_event_id=str(raw.get('event_id') or raw.get('id') or event_url or '') or None,
            title=raw.get('eventname') or raw.get('name') or raw.get('title') or 'Untitled event',
            start=start,
            end=end,
            venue=venue.get('name') or venue.get('venue'),
            address=venue.get('address'),
            town=venue.get('city') or raw.get('city') or city_hint,
            postcode=venue.get('postcode') or venue.get('postal_code'),
            category=raw.get('category') or raw.get('event_category'),
            description=raw.get('description'),
            image_url=raw.get('image') or raw.get('image_url') or raw.get('thumb_url'),
            event_url=event_url,
            ticket_url=raw.get('ticket_url') or event_url,
            price_text=raw.get('price') or raw.get('price_text'),
            source_rank=self.source_rank,
            raw=raw,
        )
