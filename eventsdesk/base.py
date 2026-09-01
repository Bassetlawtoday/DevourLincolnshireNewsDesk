from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urlsplit
import requests

from .models import EventRecord


class ConnectorError(RuntimeError):
    pass


class MissingCredentialError(ConnectorError):
    pass


class AccessBlockedError(ConnectorError):
    """The remote site is reachable but refuses automated HTTP access."""
    pass


@dataclass(slots=True)
class FetchOptions:
    timeout: float = 15.0
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/151.0.0.0 Safari/537.36"
    )


class BaseConnector(ABC):
    source_name = "base"

    def __init__(self, *, options: FetchOptions | None = None, session: requests.Session | None = None):
        self.options = options or FetchOptions()
        self.session = session or requests.Session()
        self.session.headers["User-Agent"] = self.options.user_agent
        self.session.headers.setdefault("Accept-Language", "en-GB,en;q=0.9")
        self.session.headers.setdefault("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8")
        self.session.headers.setdefault("Cache-Control", "no-cache")
        self.session.headers.setdefault("Upgrade-Insecure-Requests", "1")

    def get(self, url: str, **kwargs) -> requests.Response:
        response = self.session.get(url, timeout=self.options.timeout, **kwargs)
        if getattr(response, "status_code", None) in (403, 406):
            parts = urlsplit(url)
            headers = dict(kwargs.pop("headers", {}) or {})
            headers.setdefault("Referer", f"{parts.scheme}://{parts.netloc}/")
            headers.setdefault("Sec-Fetch-Site", "same-origin")
            headers.setdefault("Sec-Fetch-Mode", "navigate")
            response = self.session.get(url, timeout=self.options.timeout, headers=headers, **kwargs)
            if getattr(response, "status_code", None) in (403, 406):
                raise AccessBlockedError(f"{response.status_code} access blocked for {url}")
        response.raise_for_status()
        return response

    @abstractmethod
    def fetch(self) -> list[EventRecord]:
        raise NotImplementedError

    def normalize(self, events: Iterable[EventRecord]) -> list[EventRecord]:
        return [event.normalize() for event in events]
