from __future__ import annotations

import argparse
import json

from .connectors.endpoint_discovery import EventEndpointDiscovery
from .connectors.platform_fingerprint import PlatformDiscovery
from .connectors.council_strategy import CouncilStrategy
from .connectors.spektrix_discovery import SpektrixDiscovery
from .council_inventory import COUNCIL_EVENT_SOURCES
from .theatre_inventory import THEATRE_PLATFORMS


def discover_theatres() -> list[dict]:
    rows = []
    for item in THEATRE_PLATFORMS:
        if "Spektrix" not in item.platform:
            continue
        try:
            fp = SpektrixDiscovery(item.website).discover()
            rows.append({
                "name": item.name,
                "website": item.website,
                "platform": item.platform,
                "confirmed_client_name": fp.client_name,
                "api_confirmed": fp.confirmed,
                "evidence_url": fp.evidence_url,
            })
        except Exception as exc:
            rows.append({"name": item.name, "website": item.website, "platform": item.platform, "error": str(exc)})
    return rows


def discover_councils() -> list[dict]:
    rows = []
    for item in COUNCIL_EVENT_SOURCES:
        try:
            finder = EventEndpointDiscovery(item.events_url)
            response = finder.get(item.events_url)
            candidates = finder.discover()
            platform = PlatformDiscovery.fingerprint_html(response.text, response.url)
            plan = CouncilStrategy.plan_from_html(response.text, response.url, candidates)
            rows.append({
                "name": item.name,
                "events_url": item.events_url,
                "area": item.area,
                "source_type": item.source_type,
                "platform": platform.platform,
                "platform_confidence": platform.confidence,
                "recommended_mode": plan.mode,
                "event_jsonld": plan.event_jsonld,
                "plan_notes": plan.notes,
                "candidates": [
                    {
                        "url": c.url,
                        "confidence": c.confidence,
                        "evidence": c.evidence,
                        "json_confirmed": finder.probe_json(c),
                    }
                    for c in candidates[:10]
                ],
            })
        except Exception as exc:
            rows.append({"name": item.name, "events_url": item.events_url, "area": item.area, "error": str(exc)})
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Discover reusable EventsDesk source configuration")
    parser.add_argument("mode", choices=("theatres", "councils", "all"), nargs="?", default="all")
    parser.add_argument("--output", help="Optional JSON output path")
    args = parser.parse_args()

    payload = {}
    if args.mode in {"theatres", "all"}:
        payload["theatres"] = discover_theatres()
    if args.mode in {"councils", "all"}:
        payload["councils"] = discover_councils()

    text = json.dumps(payload, indent=2, ensure_ascii=False)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
