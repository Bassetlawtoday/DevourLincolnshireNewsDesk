from __future__ import annotations

from dataclasses import dataclass
import json
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from ..base import BaseConnector, ConnectorError


@dataclass(slots=True, frozen=True)
class EndpointCandidate:
    url: str
    method: str = "GET"
    confidence: str = "low"
    evidence: str = ""


class EventEndpointDiscovery(BaseConnector):
    """Find likely public event JSON/XHR endpoints in a web page.

    It does not execute arbitrary JavaScript. It inspects server-delivered page
    markup and referenced first-party scripts for common fetch/AJAX/API patterns,
    ranks event-looking URLs, and can probe candidates for JSON responses.
    """

    source_name = "event_endpoint_discovery"

    _url_patterns = [
        re.compile(r"fetch\(\s*['\"]([^'\"]+)['\"]", re.I),
        re.compile(r"(?:url|endpoint|apiUrl|api_url)\s*[:=]\s*['\"]([^'\"]+)['\"]", re.I),
        re.compile(r"axios\.(?:get|post)\(\s*['\"]([^'\"]+)['\"]", re.I),
        re.compile(r"\$\.get(?:JSON)?\(\s*['\"]([^'\"]+)['\"]", re.I),
        re.compile(r"['\"](/[^'\"]*(?:event|what.?s.?on)[^'\"]*(?:api|json|search|listing|query)[^'\"]*)['\"]", re.I),
        re.compile(r"['\"](/[^'\"]*(?:api|json)[^'\"]*(?:event|what.?s.?on)[^'\"]*)['\"]", re.I),
    ]

    def __init__(self, page_url: str, *, inspect_scripts: bool = True, max_scripts: int = 12, **kwargs):
        super().__init__(**kwargs)
        self.page_url = page_url
        self.inspect_scripts = inspect_scripts
        self.max_scripts = max_scripts

    def fetch(self):  # pragma: no cover
        raise ConnectorError("EventEndpointDiscovery returns endpoint candidates; call discover()")

    def discover(self) -> list[EndpointCandidate]:
        response = self.get(self.page_url)
        texts = [(response.url, response.text)]
        if self.inspect_scripts:
            soup = BeautifulSoup(response.text, "html.parser")
            script_urls = []
            page_host = urlparse(response.url).netloc.casefold()
            for script in soup.find_all("script", src=True):
                full = urljoin(response.url, str(script.get("src")))
                if urlparse(full).netloc.casefold() == page_host and full not in script_urls:
                    script_urls.append(full)
            for url in script_urls[: self.max_scripts]:
                try:
                    r = self.get(url)
                except Exception:
                    continue
                texts.append((r.url, r.text))

        candidates: dict[str, EndpointCandidate] = {}
        for evidence_url, text in texts:
            for raw in self.urls_from_text(text):
                full = urljoin(response.url, raw.replace("\\/", "/"))
                if not full.startswith(("http://", "https://")):
                    continue
                score = self._score(full)
                if score <= 0:
                    continue
                confidence = "high" if score >= 5 else "medium" if score >= 3 else "low"
                current = candidates.get(full)
                candidate = EndpointCandidate(full, confidence=confidence, evidence=evidence_url)
                if current is None or self._confidence_value(confidence) > self._confidence_value(current.confidence):
                    candidates[full] = candidate
        return sorted(candidates.values(), key=lambda x: (-self._confidence_value(x.confidence), x.url))

    def probe_json(self, candidate: EndpointCandidate, *, params: dict | None = None) -> bool:
        try:
            response = self.session.get(candidate.url, params=params or {}, timeout=self.options.timeout)
            if not response.ok:
                return False
            content_type = response.headers.get("content-type", "").casefold()
            if "json" in content_type:
                response.json()
                return True
            text = response.text.lstrip()
            if text.startswith(("{", "[")):
                json.loads(text)
                return True
        except Exception:
            return False
        return False

    @classmethod
    def urls_from_text(cls, text: str) -> list[str]:
        found: list[str] = []
        for pattern in cls._url_patterns:
            for match in pattern.finditer(text or ""):
                value = match.group(1).strip()
                if value and value not in found:
                    found.append(value)
        return found

    @staticmethod
    def _score(url: str) -> int:
        low = url.casefold()
        score = 0
        if "event" in low or "whatson" in low or "whats-on" in low or "what_s_on" in low:
            score += 3
        if any(x in low for x in ("/api/", "/api?", ".json", "format=json", "/search", "/query", "/listing")):
            score += 2
        if any(x in low for x in ("calendar", "date", "category", "venue")):
            score += 1
        if any(x in low for x in ("google", "facebook", "analytics", "doubleclick", "cookie")):
            score -= 4
        return score

    @staticmethod
    def _confidence_value(value: str) -> int:
        return {"low": 1, "medium": 2, "high": 3}.get(value, 0)
