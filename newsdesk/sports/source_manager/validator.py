"""Validation and URL-safety rules for managed Sport website sources."""

from __future__ import annotations

from dataclasses import dataclass, field
import ipaddress
import re
import socket
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


REGEX_FIELDS = (
    "include_url_patterns",
    "exclude_url_patterns",
    "exclude_title_patterns",
)
LIST_FIELDS = (
    "tags",
    "article_link_selectors",
    "card_selectors",
    "include_url_patterns",
    "exclude_url_patterns",
    "exclude_title_patterns",
    "standalone_item_selectors",
)


@dataclass(slots=True)
class SourceValidation:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.errors


class SourceValidator:
    """Validate form values without executing site content."""

    MAX_STORIES = 100

    def validate(
        self,
        values: dict[str, Any],
        existing: list[dict[str, Any]],
        *,
        current_id: str = "",
        resolve_dns: bool = False,
    ) -> SourceValidation:
        result = SourceValidation()
        name = str(values.get("name") or "").strip()
        url = str(values.get("listing_url") or "").strip()
        if not name:
            result.errors.append("Source name is required.")
        result.errors.extend(self._url_errors(url, resolve_dns=resolve_dns))
        for field_name in ("listing_warmup_url", "content_api_url"):
            optional_url = str(values.get(field_name) or "").strip()
            if optional_url:
                result.errors.extend(
                    f"{field_name}: {error}"
                    for error in self._url_errors(
                        optional_url,
                        resolve_dns=resolve_dns,
                    )
                )

        try:
            maximum = int(values.get("max_stories", 20))
            if maximum < 1 or maximum > self.MAX_STORIES:
                raise ValueError
        except (TypeError, ValueError):
            result.errors.append("Maximum story count must be between 1 and 100.")

        for field_name in REGEX_FIELDS:
            for pattern in self._list(values.get(field_name)):
                try:
                    re.compile(pattern)
                except re.error as error:
                    result.errors.append(
                        f"Invalid regular expression in {field_name}: {error}"
                    )

        for field_name in (
            "article_link_selectors",
            "card_selectors",
            "standalone_item_selectors",
        ):
            if any(not item.strip() for item in self._list(values.get(field_name))):
                result.errors.append(f"{field_name} contains an empty selector.")

        name_key = name.casefold()
        url_key = self.normalise_url(url)
        for source in existing:
            source_id = str(source.get("source_id") or "")
            if current_id and source_id == current_id:
                continue
            if str(source.get("name") or "").strip().casefold() == name_key:
                result.errors.append("Another source has the same name.")
            if url_key and self.normalise_url(source.get("listing_url", "")) == url_key:
                result.errors.append("Another source has the same listing URL.")
        return result

    @staticmethod
    def _url_errors(url: str, *, resolve_dns: bool) -> list[str]:
        errors: list[str] = []
        try:
            parsed = urlparse(url)
            port = parsed.port
        except ValueError:
            return ["The URL contains a malformed port."]
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return ["A valid HTTP or HTTPS URL is required."]
        if parsed.username or parsed.password:
            errors.append("URLs containing embedded credentials are prohibited.")
        host = parsed.hostname.casefold()
        if host == "localhost" or host.endswith(".localhost"):
            errors.append("Localhost URLs are prohibited.")
        if port is not None and not 1 <= port <= 65535:
            errors.append("The URL contains a malformed port.")

        addresses: list[str] = []
        try:
            addresses.append(str(ipaddress.ip_address(host)))
        except ValueError:
            if resolve_dns:
                try:
                    addresses.extend(
                        item[4][0]
                        for item in socket.getaddrinfo(host, port or 443)
                    )
                except OSError as error:
                    errors.append(f"DNS lookup failed: {error}")
        for address in set(addresses):
            ip = ipaddress.ip_address(address)
            if not ip.is_global:
                errors.append("Private, loopback and non-public network URLs are prohibited.")
                break
        return errors

    @staticmethod
    def normalise_url(value: Any) -> str:
        try:
            parsed = urlparse(str(value or "").strip())
        except ValueError:
            return ""
        query = urlencode(
            [
                (key, val)
                for key, val in parse_qsl(parsed.query, keep_blank_values=True)
                if not key.casefold().startswith("utm_")
                and key.casefold() not in {"fbclid", "gclid"}
            ]
        )
        path = parsed.path.rstrip("/") or "/"
        return urlunparse(
            (parsed.scheme.casefold(), parsed.netloc.casefold(), path, "", query, "")
        )

    @staticmethod
    def _list(value: Any) -> list[str]:
        if isinstance(value, str):
            return [item.strip() for item in value.splitlines() if item.strip()]
        if isinstance(value, (list, tuple)):
            return [str(item).strip() for item in value]
        return []


__all__ = ["LIST_FIELDS", "REGEX_FIELDS", "SourceValidation", "SourceValidator"]
