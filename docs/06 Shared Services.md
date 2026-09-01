# Shared Services

## Story queue

`NewsDeskStoryQueue` normalises queue mappings, updates counts, detects unchanged payloads, progressively renders cards and cancels stale rendering. Modules supply mappings and own filtering and selection meaning.

Payload identity is deterministic and based on inexpensive representations of story mapping fields. It is sensitive to meaningful metadata changes and never hashes image bytes.

## UI support

`IntelligenceWindowSupport` tracks only callbacks scheduled through it, installs consistent title-bar close behaviour, restores parent focus and optionally notifies Home. `DebouncedAction` guarantees at most one pending invocation.

The live-window helpers resolve both direct Toplevels and lightweight wrappers, focus existing windows and clear tracked references after destruction.

Council is the first post-consolidation module to use the lifecycle, debounce,
Story Queue, theme and image-preview services together. Council-specific
locations, priorities, categories and health records remain outside shared UI
services.

## Images

`ImagePreviewCache` is a 24-entry LRU cache keyed by file identity, modification metadata, requested size and resize mode. It owns PIL previews only. Failed images are not retained. Tk image creation remains on the UI thread and each widget owns its Tk reference.

Council uses the shared image service and preview cache throughout. Its
workspace reuses the established Fire/Police image operations and shared
publishing action bar. Certificate failures remain visible in source health;
TLS verification is not disabled globally.

`newsdesk.display_dates` supplies long UK dates, short dates and date/time labels
with a consistent `Date unavailable` fallback. `newsdesk.theme` holds shared
header, logo, panel, card and control dimensions. The Story Queue preserves
priority colours and uses a stable accent selected state.

## Theme

`newsdesk.theme` contains the stable shared dark palette and branding paths. Dashboard-specific colours may remain local where their values intentionally differ.

The Facebook service owns provider/source health, normalised posts, edit-aware
deduplication, routing evidence and bounded persistence. Media metadata is
retained without automatic download or Tk objects.

The registry service provides deterministic read-only queries by newsroom,
source type, module and area. Schema 1 is migrated in memory to schema 2 defaults;
future unsupported versions fail clearly.
# Facebook operations services

`FacebookOperationsController` provides local readiness, source filtering/status, registry edits, explicit validations, isolated fixture diagnostics, and bounded store summaries. `FacebookOperationsStateStore` atomically persists only non-secret UI and validation summaries. The existing ingestion, normalisation, deduplication, routing, and post-store services remain authoritative.

`present_window_foreground()` maps, lifts, and focuses a newly built window. On Windows it can use a temporary topmost pulse that is always released on idle; `focus_existing_window()` remains the restoration path for an existing instance.

`SystemHealthService` assembles local `HealthItem` objects into one `HealthSnapshot`. `HealthStateStore` retains at most 20 non-secret summaries atomically. Report and clipboard paths redact secret-like data and exclude complete editorial payloads. Local diagnostics are explicit and the Facebook fixture continues to use an isolated temporary store.

Health refresh and diagnostic execution use separate guarded worker operations. Local diagnostics isolate failures per check and persist bounded start/completion times, duration, status, totals, and redacted errors. Report export writes to `exports/health/`, includes bounded local Git metadata when available, and treats Git absence as informational rather than failure.
# Facebook connection services

Shared Facebook services now include a loopback OAuth coordinator and Windows Credential Manager abstraction. Non-secret connection metadata is available to Operations and System Health; raw credentials are not.

# Standalone Facebook authentication service

The Stage 1 `auth_service` exposes only health, start, callback and protected
status endpoints. Its bounded thread-safe memory store keeps separate session,
state and poll credentials; its Meta client performs time-bounded HTTPS code
exchange, token validation and managed-Page discovery. Token records remain
backend-only and expire with the session. This service is not a shared desktop
runtime dependency until Stage 2.
