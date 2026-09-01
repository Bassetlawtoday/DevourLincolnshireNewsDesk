from __future__ import annotations

from dataclasses import dataclass

from bs4 import BeautifulSoup

from .endpoint_discovery import EndpointCandidate, EventEndpointDiscovery
from .platform_fingerprint import PlatformDiscovery, PlatformFingerprint
from ..html_utils import jsonld_objects


@dataclass(slots=True, frozen=True)
class CouncilExtractionPlan:
    mode: str
    platform: str
    platform_confidence: str
    event_jsonld: bool
    endpoint_candidates: int
    notes: str


class CouncilStrategy:
    """Choose the least fragile extraction route from static evidence."""

    @staticmethod
    def plan_from_html(html: str, page_url: str, endpoints: list[EndpointCandidate] | None = None) -> CouncilExtractionPlan:
        fp = PlatformDiscovery.fingerprint_html(html, page_url)
        event_jsonld = any(
            (obj.get("@type") == "Event") or
            (isinstance(obj.get("@type"), list) and "Event" in obj.get("@type"))
            for obj in jsonld_objects(html)
        )
        endpoints = endpoints or []
        high_json_like = [e for e in endpoints if e.confidence in {"high", "medium"}]

        if high_json_like:
            mode = "endpoint-first"
            notes = "Probe ranked first-party event endpoints; fall back to HTML if no endpoint validates as JSON."
        elif event_jsonld:
            mode = "jsonld-first"
            notes = "Use schema.org/Event records directly, with detail-page enrichment where useful."
        else:
            soup = BeautifulSoup(html or "", "html.parser")
            eventish = bool(soup.select("article, .event, .event-item, .listing, [class*='event'], [id*='event']"))
            if eventish:
                mode = "html-cards"
                notes = "Use generic council HTML card parser with CMS-specific selector overrides only if needed."
            else:
                mode = "html-discovery"
                notes = "Locate the council's dedicated events/what's-on page before considering a bespoke adapter."

        return CouncilExtractionPlan(
            mode=mode,
            platform=fp.platform,
            platform_confidence=fp.confidence,
            event_jsonld=event_jsonld,
            endpoint_candidates=len(endpoints),
            notes=notes,
        )
