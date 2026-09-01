import html
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class OneNetworkClient:
    """
    Minimal client for discovering One.Network embedded map URLs.

    This class currently downloads the public embed page and extracts
    useful metadata. Parsing of individual roadwork records will be
    added later if a supported machine-readable source is available.
    """

    DEFAULT_TIMEOUT = 20

    def __init__(self, timeout: int = DEFAULT_TIMEOUT):
        self.timeout = timeout

    def download(self, url: str) -> str:
        request = Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/150.0 Safari/537.36"
                )
            },
        )

        with urlopen(request, timeout=self.timeout) as response:
            encoding = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(encoding, errors="replace")

    @staticmethod
    def normalise_url(url: str) -> str:
        if url.startswith("//"):
            return "https:" + url
        return url

    @staticmethod
    def extract_embed_id(url: str) -> str:
        match = re.search(r'embedID%22%3A%22([^%]+)', url)
        return html.unescape(match.group(1)) if match else ""

    @staticmethod
    def extract_organisation_id(url: str) -> str:
        match = re.search(r'organisationID%22%3A(\d+)', url)
        return match.group(1) if match else ""

    def diagnostics(self, embed_url: str) -> dict:
        embed_url = self.normalise_url(embed_url)

        return {
            "embed_url": embed_url,
            "organisation_id": self.extract_organisation_id(embed_url),
            "embed_id": self.extract_embed_id(embed_url),
        }
