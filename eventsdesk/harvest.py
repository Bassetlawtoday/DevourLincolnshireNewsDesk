from __future__ import annotations
import argparse
import json
from .harvest_engine import MidlandsHarvestEngine, network_preflight


def main():
    p = argparse.ArgumentParser(description="Run the frozen Midlands EventsDesk source inventory")
    p.add_argument("--database", default="eventsdesk.sqlite")
    p.add_argument("--output", default="harvest.json", help="Compact run summary JSON")
    p.add_argument("--events-output", help="Streamed event JSONL path (defaults beside --output)")
    p.add_argument("--priority", action="append", choices=["P1", "P2", "P3", "P4"])
    p.add_argument("--limit", type=int)
    p.add_argument("--source-id", action="append", default=[])
    p.add_argument("--list", action="store_true")
    p.add_argument("--network-check", action="store_true")
    p.add_argument("--skip-network-preflight", action="store_true")
    a = p.parse_args()
    engine = MidlandsHarvestEngine()

    if a.network_check:
        print(json.dumps(network_preflight(), indent=2))
        return 0
    if a.list:
        rows = engine.select(priorities=set(a.priority) if a.priority else None, limit=a.limit)
        print(
            json.dumps(
                [
                    {"id": s.id, "name": s.name, "priority": s.priority, "connector": s.connector}
                    for s in rows
                ],
                indent=2,
            )
        )
        return 0

    result = engine.harvest(
        database=a.database,
        output=a.output,
        priorities=set(a.priority) if a.priority else None,
        limit=a.limit,
        source_ids=a.source_id or None,
        skip_network_preflight=a.skip_network_preflight,
        events_output=a.events_output,
    )
    keys = [
        "status",
        "selected_sources",
        "successful_sources",
        "failed_sources",
        "raw_events",
        "deduplicated_events",
        "current_events",
        "expired_or_past_events",
        "duplicate_reduction",
    ]
    print(json.dumps({k: result[k] for k in keys}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
