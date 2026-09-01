from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from ..base import BaseConnector, ConnectorError


_CLIENT_PATTERNS = [
    re.compile(r"system\.spektrix\.com/([A-Za-z0-9_-]+)", re.I),
    re.compile(r"(?:clientName|client_name|spektrixClientName|spektrix_client_name)\s*[:=]\s*['\"]([A-Za-z0-9_-]+)['\"]", re.I),
    re.compile(r"Spektrix(?:Client)?\s*[:=]\s*['\"]([A-Za-z0-9_-]+)['\"]", re.I),
]


@dataclass(slots=True, frozen=True)
class SpektrixFingerprint:
    website_url: str
    confirmed: bool
    client_name: str | None = None
    evidence_url: str | None = None
    evidence: str | None = None


class SpektrixDiscovery(BaseConnector):
    """Discover and validate a Spektrix client name from a public venue site.

    This is intentionally separate from :class:`SpektrixConnector`. It lets
    EventsDesk turn a venue website into a configured API connector without
    hard-coding client names that have not been verified.
    """

    source_name = "spektrix_discovery"

    def __init__(self, website_url: str, *, max_link_checks: int = 8,
                 candidate_client_names: list[str] | tuple[str, ...] | None = None, **kwargs):
        super().__init__(**kwargs)
        self.website_url = website_url
        self.max_link_checks = max_link_checks
        self.candidate_client_names = list(candidate_client_names or [])

    def fetch(self):  # pragma: no cover - discovery helper, not EventRecord source
        raise ConnectorError("SpektrixDiscovery returns fingerprints; call discover()")

    def discover(self) -> SpektrixFingerprint:
        response = self.get(self.website_url)
        html = response.text
        direct = self.client_names_from_html(html)
        for client in direct:
            if self.validate_client(client):
                return SpektrixFingerprint(
                    website_url=self.website_url,
                    confirmed=True,
                    client_name=client,
                    evidence_url=response.url,
                    evidence="client name found in venue page markup and API validated",
                )

        # Follow only likely ticket/account/booking links. Many venues proxy
        # Spektrix through a branded tickets.* host and expose the client name
        # there even when the public marketing page does not.
        for link in self._ticket_links(html, response.url)[: self.max_link_checks]:
            try:
                ticket_response = self.get(link)
            except Exception:
                continue
            for client in self.client_names_from_html(ticket_response.text):
                if self.validate_client(client):
                    return SpektrixFingerprint(
                        website_url=self.website_url,
                        confirmed=True,
                        client_name=client,
                        evidence_url=ticket_response.url,
                        evidence="client name found on linked ticketing page and API validated",
                    )

        # Explicit candidates are useful where the venue has publicly confirmed
        # Spektrix but the marketing site hides its booking links client-side.
        # Candidates are never accepted without a live public API validation.
        for client in self.candidate_client_names:
            if self.validate_client(client):
                return SpektrixFingerprint(
                    website_url=self.website_url,
                    confirmed=True,
                    client_name=client,
                    evidence_url=f"https://system.spektrix.com/{client}/api/v3/events",
                    evidence="configured client candidate validated against public API",
                )

        # Last resort: validate conservative slug candidates derived from the
        # hostname. This never marks a venue as confirmed without a live API 200.
        for client in self.slug_candidates(self.website_url):
            if self.validate_client(client):
                return SpektrixFingerprint(
                    website_url=self.website_url,
                    confirmed=True,
                    client_name=client,
                    evidence_url=f"https://system.spektrix.com/{client}/api/v3/events",
                    evidence="hostname-derived client candidate validated against public API",
                )

        return SpektrixFingerprint(self.website_url, False)

    def validate_client(self, client_name: str) -> bool:
        url = f"https://system.spektrix.com/{client_name}/api/v3/events"
        try:
            response = self.session.get(url, timeout=self.options.timeout)
            if not response.ok:
                return False
            payload = response.json()
            return isinstance(payload, (list, dict))
        except Exception:
            return False

    @staticmethod
    def client_names_from_html(html: str) -> list[str]:
        found: list[str] = []
        for pattern in _CLIENT_PATTERNS:
            for match in pattern.finditer(html or ""):
                value = match.group(1).strip()
                if value and value.casefold() not in {x.casefold() for x in found}:
                    found.append(value)
        return found

    @staticmethod
    def slug_candidates(url: str) -> list[str]:
        host = urlparse(url).netloc.casefold().split(":", 1)[0]
        host = host.removeprefix("www.")
        labels = [x for x in host.split(".") if x and x not in {"co", "uk", "com", "org", "net"}]
        base = labels[-1] if labels else ""
        candidates = []
        for value in (base, re.sub(r"[^a-z0-9]", "", base)):
            if value and value not in candidates:
                candidates.append(value)
        return candidates

    @staticmethod
    def _ticket_links(html: str, base_url: str) -> list[str]:
        soup = BeautifulSoup(html or "", "html.parser")
        links: list[str] = []
        for a in soup.find_all("a", href=True):
            href = str(a.get("href") or "").strip()
            text = a.get_text(" ", strip=True).casefold()
            full = urljoin(base_url, href)
            host = urlparse(full).netloc.casefold()
            marker = " ".join((href.casefold(), text, host))
            if any(k in marker for k in ("ticket", "book", "basket", "account", "spektrix")):
                if full not in links:
                    links.append(full)
        return links
