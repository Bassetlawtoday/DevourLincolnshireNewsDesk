"""
Application bootstrap for Devour Lincolnshire NewsDesk.

Responsible for wiring together the application's
dependencies and registering available scraper types.
"""

from __future__ import annotations

from newsdesk.sources import PoliceScraper
from newsdesk.sources.source_registry import SourceRegistry


def build_source_registry() -> SourceRegistry:
    """
    Create and populate the application's SourceRegistry.
    """

    registry = SourceRegistry()

    registry.register(
        "police",
        lambda source: PoliceScraper(),
    )

    return registry
