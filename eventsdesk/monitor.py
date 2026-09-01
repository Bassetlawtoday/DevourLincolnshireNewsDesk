from __future__ import annotations

import argparse
import json
from pathlib import Path

from .storage import EventStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect the EventsDesk local event database")
    parser.add_argument("--database", default="eventsdesk.sqlite")
    parser.add_argument("--changes", action="store_true", help="Show recent created/changed/missing/reactivated events")
    parser.add_argument("--active", action="store_true", help="Show active canonical events")
    parser.add_argument("--upcoming", action="store_true", help="Show scheduled/postponed upcoming events only")
    parser.add_argument("--series", help="Show all occurrences for a series_key")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--output", help="Optional JSON output path")
    args = parser.parse_args()

    with EventStore(args.database) as store:
        if args.series:
            rows = store.series_occurrences(args.series)[:args.limit]
        elif args.changes:
            rows = store.recent_changes(args.limit)
        elif args.upcoming:
            rows = store.upcoming_events(args.limit)
        else:
            rows = store.active_events(args.limit)
        payload = [dict(row) for row in rows]

    text = json.dumps(payload, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
