from __future__ import annotations

import html
import re
from urllib.error import HTTPError, URLError

from services.roadworks.base_source import BaseRoadworksSource
from services.roadworks.one_network_client import OneNetworkClient
from services.roadworks_models import RoadworkRecord


class NottinghamshireCountyCouncilSource(BaseRoadworksSource):
    """
    Nottinghamshire Highways public roadworks source.

    Phase 1
    -------
    * Download public page
    * Locate embedded One.Network map
    * Return diagnostics

    Phase 2
    -------
    * Parse live public roadworks
    """

    name = "Nottinghamshire County Council"

    ROADWORKS_PAGE_URL = (
        "https://www.nottshighways.co.uk/roadworks-in-notts/"
    )

    DEFAULT_TIMEOUT = 20

    def __init__(self, timeout: int = DEFAULT_TIMEOUT):

        self.timeout = timeout

        self.client = OneNetworkClient(timeout)

        self.records: list[RoadworkRecord] = []

        self.page_available = False

        self.embed_url = ""

        self.embed_id = ""

        self.organisation_id = ""

        self.last_error = ""

    def fetch(self) -> list[RoadworkRecord]:

        self.records = []

        self.page_available = False

        self.embed_url = ""

        self.embed_id = ""

        self.organisation_id = ""

        self.last_error = ""

        try:

            page = self.client.download(self.ROADWORKS_PAGE_URL)

            self.page_available = True

            self.embed_url = self._find_embed(page)

            if self.embed_url:

                info = self.client.diagnostics(self.embed_url)

                self.embed_id = info.get("embed_id", "")

                self.organisation_id = info.get(
                    "organisation_id", ""
                )

        except (HTTPError, URLError, TimeoutError, OSError) as exc:

            self.last_error = str(exc)

        return self.records

    @staticmethod
    def _find_embed(page_html: str) -> str:

        patterns = (

            r'<iframe[^>]+src=["\']([^"\']*one\.network[^"\']*)',

            r'href=["\']([^"\']*one\.network[^"\']*)',

            r'(//api-gb\.one\.network/embedded/[^\s"\']*)',

        )

        for pattern in patterns:

            match = re.search(
                pattern,
                page_html,
                flags=re.IGNORECASE,
            )

            if match:

                return html.unescape(match.group(1))

        return ""

    def diagnostic_summary(self):

        return {

            "source": self.name,

            "page_available": self.page_available,

            "organisation_id": self.organisation_id,

            "embed_id": self.embed_id,

            "embed_found": bool(self.embed_url),

            "records_returned": len(self.records),

            "last_error": self.last_error,
        }
