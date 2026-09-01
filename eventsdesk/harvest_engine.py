from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
import json
from pathlib import Path
import socket
from typing import Callable

from .dedupe import deduplicate
from .occurrences import OccurrenceExpander
from .source_catalog import SourceCatalog, connector_factory
from .storage import EventStore
from .enrichment import EventEnricher
from .event_quality import filter_false_events, repeated_title_anomalies
from .base import AccessBlockedError, MissingCredentialError


NETWORK_TEST_HOSTS = (
    "rock-city.co.uk",
    "www.trch.co.uk",
    "www.academymusicgroup.com",
)


def network_preflight(resolver: Callable = socket.getaddrinfo) -> dict:
    """Check whether the runtime can resolve public source hosts.

    This distinguishes an execution-environment outage from connector/parser
    failures. A source harvest should not poison connector health when DNS is
    unavailable globally.
    """
    results = []
    for host in NETWORK_TEST_HOSTS:
        try:
            resolver(host, 443)
            results.append({"host": host, "resolved": True})
        except Exception as exc:
            results.append({"host": host, "resolved": False, "error": str(exc)})
    available = any(row["resolved"] for row in results)
    return {"network_available": available, "checks": results}



def _event_dict(event) -> dict:
    data = asdict(event)
    data["start"] = event.start.isoformat() if event.start else None
    data["end"] = event.end.isoformat() if event.end else None
    return data


def stream_events_jsonl(events, path: str | Path) -> int:
    """Write events one record at a time without building a giant JSON string."""
    target = Path(path)
    count = 0
    with target.open("w", encoding="utf-8", newline="\n") as handle:
        for event in events:
            json.dump(_event_dict(event), handle, ensure_ascii=False, default=str)
            handle.write("\n")
            count += 1
    return count


def _default_events_output(summary_output: str | Path) -> str:
    p = Path(summary_output)
    return str(p.with_name(f"{p.stem}_events.jsonl"))

class MidlandsHarvestEngine:
    """Catalog-driven harvesting for the frozen Midlands source inventory."""

    def __init__(self, catalog: SourceCatalog | None = None):
        self.catalog = catalog or SourceCatalog.load_default()

    def select(self, *, priorities: set[str] | None = None, limit: int | None = None):
        rows = self.catalog.select(priorities=priorities, runnable_only=True)
        rows.sort(key=lambda s: (s.source_rank, s.priority, s.name.casefold()))
        return rows[:limit] if limit else rows

    def harvest(
        self,
        *,
        database="eventsdesk.sqlite",
        output="harvest.json",
        priorities=None,
        limit=None,
        source_ids=None,
        skip_network_preflight=False,
        events_output=None,
        progress_callback=None,
    ):
        selected = self.select(priorities=priorities, limit=None)
        if source_ids:
            wanted = set(source_ids)
            selected = [s for s in selected if s.id in wanted]
        if limit:
            selected = selected[:limit]

        preflight = network_preflight()
        if not skip_network_preflight and not preflight["network_available"]:
            payload = {
                "generated_at": datetime.now().astimezone().isoformat(),
                "status": "environment_network_unavailable",
                "selected_sources": len(selected),
                "successful_sources": 0,
                "failed_sources": 0,
                "raw_events": 0,
                "deduplicated_events": 0,
                "duplicate_reduction": 0,
                "network_preflight": preflight,
                "persistence": None,
                "sources": [],
                "events_export": None,
            }
            Path(output).write_text(
                json.dumps(payload, indent=2, ensure_ascii=False, default=str),
                encoding="utf-8",
            )
            return payload

        raw = []
        failures = []
        successful = []
        zero_yield = []
        access_blocked = []
        credential_missing = []
        per_source = []
        total_selected = len(selected)
        for source_index, config in enumerate(selected, start=1):
            if progress_callback:
                progress_callback({
                    "stage": "source_start",
                    "index": source_index,
                    "total": total_selected,
                    "source": config.name,
                })
            try:
                discovered = OccurrenceExpander.expand_many(connector_factory(config)().fetch())
                events, false_removed = filter_false_events(discovered)
                anomalies = repeated_title_anomalies(events)
                raw.extend(events)
                if events:
                    successful.append(config.name)
                    per_source.append({
                        "id": config.id, "source": config.name, "succeeded": True,
                        "status": "success", "events": len(events),
                        "false_events_removed": false_removed, "anomalies": anomalies,
                    })
                else:
                    zero_yield.append(config.name)
                    per_source.append({
                        "id": config.id, "source": config.name, "succeeded": True,
                        "status": "zero_yield", "events": 0,
                        "false_events_removed": false_removed, "anomalies": anomalies,
                    })
            except MissingCredentialError as exc:
                credential_missing.append(config.name)
                per_source.append({"id": config.id, "source": config.name, "succeeded": False, "status": "credential_missing", "events": 0, "error": str(exc)})
            except AccessBlockedError as exc:
                access_blocked.append(config.name)
                per_source.append({"id": config.id, "source": config.name, "succeeded": False, "status": "access_blocked", "events": 0, "error": str(exc)})
            except Exception as exc:
                failures.append({"source": config.name, "error": str(exc)})
                per_source.append(
                    {
                        "id": config.id,
                        "source": config.name,
                        "succeeded": False,
                        "status": "failed",
                        "events": 0,
                        "error": str(exc),
                    }
                )
            finally:
                if progress_callback:
                    latest = per_source[-1] if per_source else {}
                    progress_callback({
                        "stage": "source_done",
                        "index": source_index,
                        "total": total_selected,
                        "source": config.name,
                        "status": latest.get("status", "unknown"),
                        "events": latest.get("events", 0),
                    })

        enricher = EventEnricher({c.name: c.area for c in selected}, {c.name: c.type for c in selected})
        raw = [enricher.enrich(event) for event in raw]
        merged = deduplicate(raw)
        with EventStore(database) as store:
            persistence = asdict(
                store.harvest(raw, failures=failures, successful_sources=successful)
            )
        now = datetime.now().astimezone()
        current = [e for e in merged if EventStore.lifecycle_state_for(e, now) in ("scheduled", "postponed")]
        expired_count = len(merged) - len(current)
        event_export_path = events_output or _default_events_output(output)
        exported_count = stream_events_jsonl(current, event_export_path)

        payload = {
            "generated_at": datetime.now().astimezone().isoformat(),
            "status": "completed",
            "selected_sources": len(selected),
            "successful_sources": len(successful),
            "zero_yield_sources": len(zero_yield),
            "access_blocked_sources": len(access_blocked),
            "credential_missing_sources": len(credential_missing),
            "failed_sources": len(failures),
            "raw_events": len(raw),
            "deduplicated_events": len(merged),
            "current_events": len(current),
            "expired_or_past_events": expired_count,
            "duplicate_reduction": len(raw) - len(merged),
            "false_events_removed": sum(x.get("false_events_removed", 0) for x in per_source),
            "anomaly_sources": sum(1 for x in per_source if x.get("anomalies")),
            "network_preflight": preflight,
            "persistence": persistence,
            "sources": per_source,
            "events_export": {
                "format": "jsonl",
                "path": str(event_export_path),
                "records": exported_count,
            },
        }
        with Path(output).open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False, default=str)
        return payload
