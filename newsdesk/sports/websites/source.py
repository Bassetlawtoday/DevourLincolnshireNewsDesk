"""Configuration model for generic sports website sources."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class WebsiteSource:
    """Describe one website listing that can be collected generically."""

    name: str
    sport: str
    listing_url: str

    enabled: bool = True
    organisation: str = ""
    location: str = "Bassetlaw"
    max_stories: int = 20
    timeout: float = 30.0
    request_delay: float = 0.0
    same_domain_only: bool = True

    article_link_selectors: list[str] = field(default_factory=list)
    standalone_item_selectors: list[str] = field(default_factory=list)
    card_selectors: list[str] = field(default_factory=list)
    title_selectors: list[str] = field(default_factory=list)
    summary_selectors: list[str] = field(default_factory=list)
    date_selectors: list[str] = field(default_factory=list)
    image_selectors: list[str] = field(default_factory=list)

    include_url_patterns: list[str] = field(default_factory=list)
    exclude_url_patterns: list[str] = field(default_factory=list)
    exclude_title_patterns: list[str] = field(default_factory=list)

    tags: list[str] = field(default_factory=list)
    headers: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.name = str(self.name or "").strip()
        self.sport = str(self.sport or "Sport").strip() or "Sport"
        self.listing_url = str(self.listing_url or "").strip()
        self.organisation = str(self.organisation or self.name).strip()
        self.location = str(self.location or "Bassetlaw").strip()
        self.max_stories = int(self.max_stories)
        self.timeout = float(self.timeout)
        self.request_delay = float(self.request_delay)

        if not self.name:
            raise ValueError("Website source name cannot be empty.")
        if not self.listing_url:
            raise ValueError("Website source listing_url cannot be empty.")
        if self.max_stories <= 0:
            raise ValueError("Website source max_stories must be positive.")
        if self.timeout <= 0:
            raise ValueError("Website source timeout must be positive.")
        if self.request_delay < 0:
            raise ValueError("Website source request_delay cannot be negative.")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WebsiteSource":
        """Create a validated source definition from JSON-compatible data."""

        if not isinstance(data, dict):
            raise TypeError("Website source configuration must be a dictionary.")

        known = set(cls.__dataclass_fields__)
        values = {key: value for key, value in data.items() if key in known}
        unknown = {key: value for key, value in data.items() if key not in known}

        metadata = dict(values.get("metadata") or {})
        metadata.update(unknown)
        values["metadata"] = metadata

        return cls(**values)


__all__ = ["WebsiteSource"]
