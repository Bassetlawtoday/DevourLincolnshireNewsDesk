from __future__ import annotations

from ..base import BaseConnector, ConnectorError
from .spektrix import SpektrixConnector
from .spektrix_discovery import SpektrixDiscovery


class AutoSpektrixConnector(BaseConnector):
    """Resolve a venue's Spektrix client name at runtime, then harvest its API.

    The connector never trusts a guessed client name: every candidate must
    return valid JSON from the public Spektrix v3 events endpoint before use.
    """

    source_name = "auto_spektrix"

    def __init__(self, website_url: str, *, source_name: str,
                 candidate_client_names: list[str] | tuple[str, ...] | None = None,
                 source_rank: int = 12, **kwargs):
        super().__init__(**kwargs)
        self.website_url = website_url
        self.source_name = source_name
        self.source_rank = source_rank
        self.candidate_client_names = list(candidate_client_names or [])
        self._resolved_client_name: str | None = None

    def resolve_client_name(self) -> str:
        if self._resolved_client_name:
            return self._resolved_client_name
        discovery = SpektrixDiscovery(
            self.website_url,
            candidate_client_names=self.candidate_client_names,
            session=self.session,
            options=self.options,
        )
        fingerprint = discovery.discover()
        if not fingerprint.confirmed or not fingerprint.client_name:
            raise ConnectorError(
                f"Could not validate a public Spektrix client endpoint for {self.source_name}"
            )
        self._resolved_client_name = fingerprint.client_name
        return self._resolved_client_name

    def fetch(self):
        client_name = self.resolve_client_name()
        connector = SpektrixConnector(
            client_name,
            source_name=self.source_name,
            source_rank=self.source_rank,
            session=self.session,
            options=self.options,
        )
        return connector.fetch()
