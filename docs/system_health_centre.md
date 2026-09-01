# System Health Centre

System Health is NewsDesk Pro's read-oriented operational view. Open **SYSTEM HEALTH** from Home. Opening it or selecting **REFRESH HEALTH** performs local probes only: it does not collect news, contact providers, alter schedules, repair data, or clear caches.

## Status meanings

- **HEALTHY** — functioning normally.
- **INACTIVE** — deliberately disabled or not configured; this is not a failure.
- **ATTENTION** — setup or maintenance may be needed.
- **DEGRADED** — part of the service remains available.
- **FAILED** — the service is currently unusable.
- **UNKNOWN** — the project has insufficient authoritative evidence.

The overall result uses FAILED, DEGRADED, ATTENTION, then HEALTHY precedence. INACTIVE alone does not make the platform unhealthy.

## What is shown

The overview summarises Modules, Scheduler, Data and Cache, and Providers. The health list can be searched or filtered; select an item for its status, safe bounded details, authoritative source, check times, related path, and a non-executing recommended action.

Module health comes from dashboard state, scheduler policy, and the current-process result repository. Planning persistence comes from the versioned Planning cache. Council source evidence comes from the retained Council repository payload when available; an EMCCA image certificate problem is shown separately from article collection. Scheduler and concurrency values come from the existing scheduler, coordinator, and dashboard runtime.

Data health covers bounded repository metadata, Planning cache, image-preview cache capacity, and a read-only SQLite query. Configuration and documentation probes read local files only.

## Authoritative health-source map

| Health area | Authoritative source |
|---|---|
| Application runtime | Dashboard/window runtime state |
| Scheduler | `DashboardScheduler` and dashboard state policies |
| Active collections | `DashboardRefreshCoordinator` |
| Module counts and refresh times | `DashboardStateStore` |
| Current payload presence | `DashboardResultRepository` |
| Planning persistence | `PlanningResultCache` |
| Configuration | Existing JSON loaders and validation |
| Database | Read-only SQLite schema/count query |
| Image previews | Shared `ImagePreviewCache` metadata |
| Documentation | Expected local documentation file set |
| Test status | Not displayed because no authoritative persisted test result exists |

Queued jobs, image-cache eviction counts, and other untracked metrics are labelled Not tracked or Unknown rather than inferred.

## Safe actions

- **RUN LOCAL DIAGNOSTICS** checks configuration, cache readability, SQLite, and documentation in a background worker.
- **COPY HEALTH SUMMARY** copies a short redacted status summary.
- **EXPORT HEALTH REPORT** writes a timestamped, redacted Markdown report under `diagnostics/`; it contains no full editorial payloads.
- Folder buttons open existing local log/data folders.

Every action reports progress and completion in the header status area. Health refresh and diagnostics prevent overlapping runs and restore their controls afterward. A failed refresh preserves the last valid snapshot. Diagnostic checks are failure-isolated so safe remaining checks continue and partial completion identifies the failed check.

Reports are written only after an explicit export to `exports/health/newsdesk_health_YYYY-MM-DD_HHMMSS.md`. They contain the generated time, application version, safe bounded Git branch/commit/working-tree information where available, operational category summaries, latest diagnostic result, actionable items, and recommendations. Git unavailability does not fail the report. Credentials, environment secrets, full logs, provider responses, and editorial payloads are excluded and redacted.

NewsDesk Pro currently logs to the console, so **OPEN LOG FOLDER** reports that no log folder is configured instead of inventing a location. **OPEN DATA FOLDER** opens the actual application `data` directory.

No destructive maintenance actions are included. Health cannot clear caches, reset the database, force jobs, kill workers, purge payloads, or repair configuration.

## History and troubleshooting

The latest 20 bounded snapshot summaries are stored atomically in `data/system_health_state.json`; only times, aggregate counts, duration, and item statuses are retained. If this state is corrupt, the original is preserved, history starts empty, and an Attention item explains the issue.

For an Attention or Degraded item, follow its recommended action and inspect the named authoritative source. UNKNOWN means the evidence is unavailable—not that the component failed.

User-facing UNKNOWN summaries distinguish between “Never observed in this process”, “No runtime evidence available yet”, and telemetry that is “Not tracked”. Recommendations remain specific and non-destructive: refresh the affected module, review retained source health, or wait for an external certificate correction as appropriate.
