from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict

from .connectors import TicketmasterConnector, SkiddleConnector, SpektrixConnector
from .dedupe import deduplicate
from .occurrences import OccurrenceExpander
from .registry import build_network_connectors, build_venue_connectors
from .storage import EventStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch, normalize and persist Midlands events")
    parser.add_argument("--ticketmaster", action="store_true")
    parser.add_argument("--skiddle", action="store_true")
    parser.add_argument("--venues", action="store_true")
    parser.add_argument("--networks", action="store_true", help="Tourism / National Trust / English Heritage")
    parser.add_argument("--spektrix-client", action="append", default=[], metavar="CLIENT=SOURCE",
                        help="Add a public Spektrix v3 client, e.g. clientname='Venue Name'")
    parser.add_argument("--output", default="events.json")
    parser.add_argument("--database", default="eventsdesk.sqlite",
                        help="SQLite database path; use --no-database to disable persistence")
    parser.add_argument("--no-database", action="store_true")
    args = parser.parse_args()

    connectors = []
    if args.ticketmaster:
        connectors.append(TicketmasterConnector(os.getenv("TICKETMASTER_API_KEY")))
    if args.skiddle:
        connectors.append(SkiddleConnector(os.getenv("SKIDDLE_API_KEY"), latitude=52.9548, longitude=-1.1581, radius_miles=90))
    if args.venues:
        connectors.extend(build_venue_connectors())
    if args.networks:
        connectors.extend(build_network_connectors())
    for spec in args.spektrix_client:
        client, sep, name = spec.partition("=")
        if not sep:
            name = client
        connectors.append(SpektrixConnector(client, source_name=name or client))

    all_events = []
    failures = []
    successful_sources = []
    for connector in connectors:
        try:
            fetched = connector.fetch()
            all_events.extend(fetched)
            successful_sources.append(connector.source_name)
        except Exception as exc:
            failures.append({"source": connector.source_name, "error": str(exc)})

    all_events = OccurrenceExpander.expand_many(all_events)
    merged = deduplicate(all_events)
    persistence = None
    if not args.no_database:
        with EventStore(args.database) as store:
            persistence = asdict(store.harvest(
                all_events,
                failures=failures,
                successful_sources=successful_sources,
            ))

    payload = {
        "events": [asdict(e) | {"start": e.start.isoformat() if e.start else None, "end": e.end.isoformat() if e.end else None} for e in merged],
        "failures": failures,
        "stats": {"raw": len(all_events), "deduplicated": len(merged), "failures": len(failures)},
        "persistence": persistence,
    }
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False, default=str)
    print(json.dumps(payload["stats"] | ({"database": persistence} if persistence else {})))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
