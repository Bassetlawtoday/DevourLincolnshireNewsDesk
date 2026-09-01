from __future__ import annotations

from dataclasses import dataclass
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from ..base import BaseConnector, ConnectorError


@dataclass(slots=True, frozen=True)
class PlatformFingerprint:
    platform: str
    confidence: str
    evidence: tuple[str, ...]


class PlatformDiscovery(BaseConnector):
    """Conservative CMS/platform fingerprinting for public event websites.

    The detector only reports a named platform when server-delivered markup or
    asset URLs contain a recognisable fingerprint. Unknown is a valid result.
    """

    source_name = "platform_discovery"

    _RULES: tuple[tuple[str, tuple[re.Pattern[str], ...]], ...] = (
        ("LocalGov Drupal", (
            re.compile(r"localgov[_-]drupal|localgov_base|localgov_core", re.I),
            re.compile(r"/modules/(?:contrib/)?localgov_", re.I),
        )),
        ("Drupal", (
            re.compile(r"<meta[^>]+name=[\"']Generator[\"'][^>]+content=[\"'][^\"']*Drupal", re.I),
            re.compile(r"/sites/(?:default|[^/]+)/files/", re.I),
            re.compile(r"drupalSettings|/core/(?:assets|modules|themes)/", re.I),
        )),
        ("Jadu", (
            re.compile(r"jadu(?:\.net|_cms|cms|continuum)", re.I),
            re.compile(r"/site/scripts/|/site/styles/", re.I),
            re.compile(r"powered by jadu", re.I),
        )),
        ("GOSS iCM", (
            re.compile(r"gossinteractive|goss\.icm|goss icm", re.I),
            re.compile(r"/goss\.ashx|/icm/", re.I),
        )),
        ("Umbraco", (
            re.compile(r"umbraco", re.I),
            re.compile(r"/umbraco/", re.I),
        )),
        ("WordPress", (
            re.compile(r"<meta[^>]+name=[\"']generator[\"'][^>]+content=[\"']WordPress", re.I),
            re.compile(r"/wp-(?:content|includes)/", re.I),
        )),
        ("Civica", (
            re.compile(r"civica(?:\.com|digital|web)", re.I),
        )),
        ("Granicus", (
            re.compile(r"granicus|govdelivery", re.I),
        )),
    )

    def __init__(self, page_url: str, **kwargs):
        super().__init__(**kwargs)
        self.page_url = page_url

    def fetch(self):  # pragma: no cover
        raise ConnectorError("PlatformDiscovery returns fingerprints; call discover()")

    def discover(self) -> PlatformFingerprint:
        response = self.get(self.page_url)
        return self.fingerprint_html(response.text, response.url)

    @classmethod
    def fingerprint_html(cls, html: str, page_url: str = "") -> PlatformFingerprint:
        soup = BeautifulSoup(html or "", "html.parser")
        haystacks = [html or "", page_url]
        generator = soup.find("meta", attrs={"name": re.compile(r"^generator$", re.I)})
        if generator and generator.get("content"):
            haystacks.append(str(generator.get("content")))
        for tag in soup.find_all(["script", "link"], src=True):
            haystacks.append(str(tag.get("src") or ""))
        for tag in soup.find_all("link", href=True):
            haystacks.append(str(tag.get("href") or ""))
        text = "\n".join(haystacks)

        matches: list[tuple[str, list[str]]] = []
        for name, patterns in cls._RULES:
            evidence: list[str] = []
            for pattern in patterns:
                m = pattern.search(text)
                if m:
                    evidence.append(m.group(0)[:160])
            if evidence:
                matches.append((name, evidence))

        # LocalGov is a Drupal distribution, so prefer the more specific label.
        if matches:
            name, evidence = matches[0]
            confidence = "high" if len(evidence) >= 2 or name in {"LocalGov Drupal", "WordPress"} else "medium"
            return PlatformFingerprint(name, confidence, tuple(dict.fromkeys(evidence)))

        host = urlparse(page_url).netloc.casefold()
        return PlatformFingerprint("Unknown", "low", (host,) if host else ())
