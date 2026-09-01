from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import asdict

from .scheduler import HarvestScheduler
from .source_catalog import SourceCatalog, scheduled_source
from .storage import EventStore


def batch_report(catalog: SourceCatalog, batch: int) -> dict:
    rows = catalog.batch(batch)
    return {
        "batch": batch,
        "sources": len(rows),
        "runnable": sum(1 for s in rows if s.runnable),
        "states": dict(Counter(s.activation_state for s in rows)),
        "connectors": dict(Counter(s.connector for s in rows)),
        "items": [
            {
                "id": s.id,
                "name": s.name,
                "priority": s.priority,
                "connector": s.connector,
                "state": s.activation_state,
                "schedule": s.schedule_profile,
                "runnable": s.runnable,
            }
            for s in rows
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="EventsDesk 374-source staged rollout")
    parser.add_argument("--summary", action="store_true", help="Show registry summary")
    parser.add_argument("--status", action="store_true", help="Show connector health for selected batches")
    parser.add_argument("--list-batches", action="store_true", help="Show batch counts")
    parser.add_argument("--batch", type=int, action="append", default=[], help="Select rollout batch (repeatable)")
    parser.add_argument("--dry-run", action="store_true", help="Print selected runnable sources without fetching")
    parser.add_argument("--database", default="eventsdesk.sqlite")
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument("--force", action="store_true", help="Run selected sources even if their normal cadence is not due")
    args = parser.parse_args()

    catalog = SourceCatalog.load_default()
    if args.summary:
        print(json.dumps(catalog.summary(), indent=2, ensure_ascii=False))
        return 0
    if args.list_batches:
        payload = [batch_report(catalog, n) for n in range(1, catalog.summary()["batches"] + 1)]
        for row in payload:
            row.pop("items", None)
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    if args.status:
        if not args.batch:
            parser.error("--status requires at least one --batch")
        selected_names = {s.name for s in catalog.select(batches=set(args.batch))}
        with EventStore(args.database) as store:
            rows = [dict(r) for r in store.connector_health_rows(1000) if r["source"] in selected_names]
        print(json.dumps({"batches": sorted(set(args.batch)), "health": rows}, indent=2, ensure_ascii=False))
        return 0
    if not args.batch:
        parser.error("choose --summary, --list-batches, or at least one --batch")

    selected = catalog.select(batches=set(args.batch), runnable_only=True)
    scheduled = [scheduled_source(s) for s in selected]
    if args.dry_run:
        print(json.dumps({
            "selected": len(selected),
            "sources": [
                {"name": s.name, "connector": s.connector, "schedule": s.schedule_profile, "batch": s.batch}
                for s in selected
            ],
        }, indent=2, ensure_ascii=False))
        return 0

    with EventStore(args.database) as store:
        scheduler = HarvestScheduler(store, max_workers=args.max_workers)
        if args.force:
            original_due = scheduler.due
            scheduler.due = lambda source, now=None: True  # type: ignore[method-assign]
        result = scheduler.run_due(scheduled)
    result["selected"] = len(selected)
    result["batches"] = sorted(set(args.batch))
    result["duplicate_rate"] = (
        round(1 - (result["harvest"]["deduplicated"] / result["raw"]), 4)
        if result.get("harvest") and result.get("raw") else 0.0
    )
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
