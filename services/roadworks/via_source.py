from __future__ import annotations

import html
import re

from services.roadworks.base_source import BaseRoadworksSource
from services.roadworks.one_network_client import OneNetworkClient


class ViaSource(BaseRoadworksSource):
    """
    Via East Midlands source.

    Version 1:
    - Verifies the public Via pages are reachable.
    - Discovers embedded One.Network maps.
    - Returns diagnostics.
    - Live record extraction will be added in the next pass.
    """

    name = "Via East Midlands"

    ROADWORKS_URL = (
        "https://www.viaem.co.uk/via-in-nottinghamshire/"
        "roadworks-in-nottinghamshire/"
    )

    PROGRAMME_URL = (
        "https://www.viaem.co.uk/via-in-nottinghamshire/"
        "nottinghamshire-highways-programme/"
    )

    def __init__(self, timeout: int = 20):
        self.client = OneNetworkClient(timeout)
        self._diagnostics = {}

    def fetch(self):
        self._diagnostics = {
            "roadworks": self._inspect(self.ROADWORKS_URL),
            "programme": self._inspect(self.PROGRAMME_URL),
        }
        return []

    def diagnostics(self):
        return self._diagnostics

    def _inspect(self, page_url: str) -> dict:
        result = {
            "page": page_url,
            "page_available": False,
            "embed_found": False,
            "embed_url": "",
            "embed_id": "",
            "organisation_id": "",
            "error": "",
        }

        try:
            page = self.client.download(page_url)
            result["page_available"] = True

            embed = self._find_embed(page)
            if embed:
                embed = self.client.normalise_url(embed)
                result["embed_found"] = True
                result["embed_url"] = embed

                info = self.client.diagnostics(embed)
                result["embed_id"] = info.get("embed_id", "")
                result["organisation_id"] = info.get("organisation_id", "")
        except Exception as exc:
            result["error"] = str(exc)

        return result

    @staticmethod
    def _find_embed(page_html: str) -> str:
        patterns = (
            r'<iframe[^>]+src=["\']([^"\']+)["\']',
            r'href=["\']([^"\']*one\.network[^"\']+)["\']',
        )

        for pattern in patterns:
            match = re.search(pattern, page_html, flags=re.IGNORECASE)
            if match:
                return html.unescape(match.group(1))

        return ""