"""Small, standard-library Metricool API client."""

from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class MetricoolError(RuntimeError):
    pass


class MetricoolClient:
    BASE = "https://app.metricool.com/api"

    def __init__(self, *, token: str, user_id: str, blog_id: str = "", timeout: int = 30) -> None:
        self.token = token.strip()
        self.user_id = user_id.strip()
        self.blog_id = blog_id.strip()
        self.timeout = timeout

    def _request(self, method: str, path: str, *, query: dict[str, str], body=None):
        url = f"{self.BASE}{path}?{urlencode(query)}"
        encoded = json.dumps(body).encode("utf-8") if body is not None else None
        request = Request(url, data=encoded, method=method, headers={"X-Mc-Auth": self.token, "Content-Type": "application/json"})
        try:
            with urlopen(request, timeout=self.timeout) as response:
                text = response.read().decode("utf-8", errors="replace")
                return json.loads(text) if text.strip() else {}
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise MetricoolError(f"Metricool returned HTTP {exc.code}: {detail or exc.reason}") from exc
        except (URLError, TimeoutError) as exc:
            raise MetricoolError(f"Metricool could not be reached: {exc}") from exc

    def list_brands(self):
        if not self.token or not self.user_id:
            raise MetricoolError("API token and user ID are required.")
        return self._request("GET", "/admin/simpleProfiles", query={"userId": self.user_id})

    def create_draft(self, *, text: str, providers: list[str], publication_datetime: str, timezone: str, image_url: str = ""):
        if not self.token or not self.user_id or not self.blog_id:
            raise MetricoolError("API token, user ID and brand/blog ID are required.")
        body = {
            "publicationDate": {"dateTime": publication_datetime, "timezone": timezone},
            "text": text,
            "providers": [{"network": value} for value in providers],
            "autoPublish": False,
            "draft": True,
            "shortener": False,
            "saveExternalMediaFiles": bool(image_url),
        }
        if image_url:
            body["media"] = [image_url]
        return self._request("POST", "/v2/scheduler/posts", query={"blogId": self.blog_id, "userId": self.user_id}, body=body)
