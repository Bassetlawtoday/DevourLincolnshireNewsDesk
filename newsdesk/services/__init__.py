"""Application service exports for Devour Lincolnshire NewsDesk.

The package keeps service imports lazy so importing ``newsdesk.services`` does
not eagerly initialise scraper, image-processing, or browser dependencies.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from newsdesk.services.fire_service import (
        FireCollectionResult,
        FireCollectionService,
    )
    from newsdesk.services.image_service import ImageAsset, ImageService
    from newsdesk.services.police_collection import (
        PoliceCollectionResult,
        PoliceCollectionService,
    )

__all__ = [
    "FireCollectionResult",
    "FireCollectionService",
    "ImageAsset",
    "ImageService",
    "PoliceCollectionResult",
    "PoliceCollectionService",
]


def __getattr__(name: str) -> Any:
    """Resolve public service classes only when they are requested."""

    if name in {"FireCollectionResult", "FireCollectionService"}:
        from newsdesk.services.fire_service import (
            FireCollectionResult,
            FireCollectionService,
        )

        exports = {
            "FireCollectionResult": FireCollectionResult,
            "FireCollectionService": FireCollectionService,
        }
        return exports[name]

    if name in {"ImageAsset", "ImageService"}:
        from newsdesk.services.image_service import ImageAsset, ImageService

        exports = {
            "ImageAsset": ImageAsset,
            "ImageService": ImageService,
        }
        return exports[name]

    if name in {"PoliceCollectionResult", "PoliceCollectionService"}:
        from newsdesk.services.police_collection import (
            PoliceCollectionResult,
            PoliceCollectionService,
        )

        exports = {
            "PoliceCollectionResult": PoliceCollectionResult,
            "PoliceCollectionService": PoliceCollectionService,
        }
        return exports[name]

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    """Include lazily exported service names in interactive discovery."""

    return sorted(set(globals()) | set(__all__))