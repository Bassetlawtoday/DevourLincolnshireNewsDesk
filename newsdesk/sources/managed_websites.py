"""Shared generic-website configuration and collection for module profiles."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from newsdesk.sports.source_manager import SourceManagerService
from newsdesk.sports.websites import default_website_scrapers
from newsdesk.story import Story
from newsdesk.geography import story_matches_lincolnshire


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SUPPORTED_MODULES = ("sport", "police", "fire", "council")
MODULE_LABELS = {
    "sport": "Sport",
    "police": "Police",
    "fire": "Fire",
    "council": "Council",
    "planning": "Planning",
}
RECENCY_DAYS = {"sport": 3, "police": 14, "fire": 14, "council": 14}

SPECIALIST_SOURCES = {
    "planning": (
        {
            "source_id": "bassetlaw_planning_portal",
            "name": "Bassetlaw Planning Portal",
            "organisation": "Bassetlaw District Council",
            "listing_url": "https://publicaccess.bassetlaw.gov.uk/",
            "sport": "Planning applications",
            "location": "Bassetlaw",
            "enabled": True,
        },
    ),
    "police": (
        {
            "source_id": "lincolnshire_police_news",
            "name": "Lincolnshire Police",
            "organisation": "Lincolnshire Police",
            "listing_url": "https://www.lincs.police.uk/news/lincolnshire/news/",
            "sport": "Police news",
            "location": "Lincolnshire",
            "enabled": True,
        },
        {
            "source_id": "lincolnshire_alert",
            "name": "Lincolnshire Alert",
            "organisation": "Lincolnshire Police and community partners",
            "listing_url": "https://www.lincolnshirealert.co.uk/",
            "sport": "Neighbourhood policing",
            "location": "Lincolnshire",
            "enabled": True,
        },
        {
            "source_id": "lincolnshire_pcc_news",
            "name": "Lincolnshire Police and Crime Commissioner",
            "organisation": "Office of the Police and Crime Commissioner for Lincolnshire",
            "listing_url": "https://lincolnshire-pcc.gov.uk/news/",
            "sport": "Policing policy and community safety",
            "location": "Lincolnshire",
            "enabled": True,
        },
        {
            "source_id": "humberside_police_northern_lincolnshire",
            "name": "Humberside Police - northern Lincolnshire",
            "organisation": "Humberside Police",
            "listing_url": "https://www.humberside.police.uk/news/news-search/",
            "sport": "Police news",
            "location": "North and North East Lincolnshire",
            "enabled": True,
        },
    ),
    "fire": (
        {
            "source_id": "nottinghamshire_fire_news",
            "name": "Nottinghamshire Fire and Rescue Service",
            "organisation": "Nottinghamshire Fire and Rescue Service",
            "listing_url": "https://www.notts-fire.gov.uk/news/",
            "sport": "Fire and rescue news",
            "location": "Nottinghamshire / Bassetlaw",
            "enabled": True,
        },
    ),
}


def config_path(module_profile: str) -> Path:
    module = str(module_profile or "").strip().casefold()
    if module == "sport":
        return PROJECT_ROOT / "config" / "sport_websites.json"
    return PROJECT_ROOT / "config" / f"{module}_websites.json"


def ensure_config(module_profile: str) -> Path:
    path = config_path(module_profile)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"version": 1, "sources": []}, indent=2),
            encoding="utf-8",
        )
    return path


def manager_service(module_profile: str) -> SourceManagerService:
    return SourceManagerService(ensure_config(module_profile))


def protected_sources(module_profile: str) -> list[dict[str, Any]]:
    """Return visible, immutable definitions for a module's core collectors."""

    module = str(module_profile or "").strip().casefold()
    definitions = [dict(item) for item in SPECIALIST_SOURCES.get(module, ())]
    if module == "council":
        council_path = PROJECT_ROOT / "config" / "council.json"
        if council_path.is_file():
            try:
                payload = json.loads(council_path.read_text(encoding="utf-8-sig"))
            except (OSError, ValueError, TypeError):
                payload = {}
            for item in payload.get("sources", []):
                definitions.append(
                    {
                        "source_id": str(item.get("key") or ""),
                        "name": str(item.get("name") or "Council source"),
                        "organisation": str(item.get("name") or ""),
                        "listing_url": str(item.get("url") or ""),
                        "sport": "Council news",
                        "location": "Bassetlaw / Nottinghamshire",
                        "enabled": bool(item.get("enabled", True)),
                    }
                )
    for definition in definitions:
        definition.update(
            {
                "module_profile": module,
                "managed_by": "core",
                "protected": True,
                "connection_status": (
                    "Configured and enabled"
                    if definition.get("enabled", True)
                    else "Configured but disabled"
                ),
            }
        )
    return definitions


def collect_managed_websites(
    module_profile: str,
) -> tuple[list[Story], list[str]]:
    """Collect enabled compatible generic sources without affecting built-ins."""

    module = str(module_profile or "").strip().casefold()
    if module not in SUPPORTED_MODULES or module == "sport":
        return [], []
    path = config_path(module)
    if not path.is_file():
        return [], []
    stories: list[Story] = []
    errors: list[str] = []
    for scraper in default_website_scrapers(path):
        scraper.DEFAULT_MAX_AGE_DAYS = RECENCY_DAYS[module]
        try:
            collected = scraper.get_stories(refresh=True, deduplicate=True)
            geographic_filter = str(
                scraper.definition.metadata.get("geographic_filter", "") or ""
            ).strip().casefold()
            if geographic_filter == "lincolnshire":
                geographically_retained: list[Story] = []
                for story in collected:
                    match = story_matches_lincolnshire(story)
                    if not match.matched:
                        continue
                    story.extras.setdefault("geographic_filter", "lincolnshire")
                    story.extras.setdefault("geographic_matches", list(match.places))
                    geographically_retained.append(story)
                collected = geographically_retained
            for story in collected:
                story.category = story.category or MODULE_LABELS[module]
                story.extras.setdefault("module_profile", module)
                story.extras.setdefault("managed_generic_source", True)
                story.extras.setdefault(
                    "source_key",
                    scraper.definition.metadata.get("source_id", ""),
                )
            stories.extend(collected)
        except Exception as error:
            errors.append(f"{scraper.definition.name}: {error}")
        finally:
            close = getattr(scraper, "close", None)
            if callable(close):
                close()
    return stories, errors


def new_source_defaults(module_profile: str) -> dict[str, Any]:
    module = str(module_profile or "").strip().casefold()
    return {
        "sport": MODULE_LABELS.get(module, module.title()),
        "max_stories": 20,
        "enabled": True,
        "location": "Bassetlaw",
        "module_profile": module,
        "max_age_days": RECENCY_DAYS.get(module, 14),
        "managed_by": "newsroom",
    }
