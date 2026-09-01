# Changelog

## Controlled Facebook Connection v1 — OAuth and Devour Lincolnshire test workflow — August 2026

- Added official browser consent with a temporary state-protected loopback callback.
- Added Windows Credential Manager token storage, managed-Page discovery, explicit Page confirmation and bounded validation.
- Restricted enablement and 10-post/one-page/30-day collection to Devour Lincolnshire, using the existing Review pipeline.
- Extended Facebook Operations, stored-post inspection and System Health without publishing or external-source access.
- Validation is mocked; no live Meta authorisation or request was performed automatically.

## Facebook Source Registry v1 — August 2026

- Advanced the registry from schema 1 to schema 2 with compatibility migration.
- Added 14 official Devour Lincolnshire source definitions, all disabled.
- Added validated metadata, deterministic registry queries and routing evidence.
- Kept all Page IDs blank and live Facebook collection inactive.

## Central Facebook Ingestion and Routing Core v1 — August 2026

- Added the dormant official-provider Facebook collection boundary.
- Added serialisable source, post, media, route and health models.
- Added edit-aware deduplication, atomic retention and one-to-many routing.
- Added a disabled registry template, safe diagnostics and fixture tests.
- No Pages are monitored and no module or Home integration is active in Phase 1.

## NewsDesk Pro Identity and Consistency Pass v1 — August 2026

- Added shared safe UK date and date/time presentation.
- Standardised shared header, logo, card, control and selected-card values.
- Reset editorial workspaces to the top on selection.
- Replaced temporary extraction console diagnostics with logging.
- Preserved module collection, scoring, schedules and payloads.

## Council Intelligence v1.1 — August 2026

- Reordered the workspace to headline, metadata, image, summary and article.
- Added Website Article, Facebook Post, Newsletter Copy and Story Pack actions.
- Added standard image controls, quality and credit display, and honest fallbacks.
- Added readable UK dates, clearer queue metadata and workspace scroll reset.
- Preserved Council collection, recency, prioritisation and dashboard behaviour.

## Council Intelligence v1 — August 2026

- Added recent official news collection for Bassetlaw District Council,
  Nottinghamshire County Council and EMCCA.
- Added 14-day recency, conservative deduplication and source-health reporting.
- Added transparent location-led priorities and simple subject categories.
- Added the Council review workspace, Home card, repository integration,
  Refresh All participation and a light 60-minute schedule.
- Added mocked HTML fixtures and Council regression tests.

Existing Police, Fire, Sport, Planning and Government behaviour is unchanged.

## Architecture Consolidation v1 — August 2026

- Added a static, validated dashboard module registry.
- Added focused intelligence-window lifecycle and debounce support.
- Consolidated Police, Fire and Sport theme imports.
- Consolidated optional manual-refresh notification payloads.
- Added live-window focus and destroyed-reference cleanup helpers.
- Preserved Planning's specialised downloader/report lifecycle.
- Retained the progressive story queue and bounded PIL preview cache ownership model.
- Added architecture, lifecycle, registry and regression tests.
- Documented system boundaries and future Bassetlaw-specific profile work.

No source definitions, scraping, scoring, ranking, recency, database schema, scheduling semantics or publication behaviour changed.
# Facebook Operations Centre v1

- Added a dormant single-instance Facebook Operations Centre from Home.
- Added local provider/readiness, registry/source, store/routing, and bounded post-viewer status.
- Added isolated fixture diagnostics and confirmation-gated provider/source validation.
- Added atomic Operations state and validated registry edit/backup support.
- Upgraded the registry to schema v3 and added disabled Devour Lincolnshire as the controlled fifteenth source.
- Facebook remains absent from startup collection, scheduling, REFRESH ALL, intelligence-module injection, and publishing.

## Facebook Operations Centre v1.1

- Fixed first-open foreground behaviour with a temporary, automatically released topmost pulse.
- Preserved single-instance restore/focus and Home-reference cleanup on both close paths.
- Reworked Provider, Registry, and System Readiness cards into aligned label/value summaries.
- Improved source-card hierarchy, human-readable metadata, selected-source sections, and Yes/No presentation.
- Added unmistakable disabled-action styling and a persisted Last Operation summary.
- Preserved dormant collection, provider, registry, routing, store, and fixture behaviour.

## System Health Centre v1

- Added a single-instance local operational view across modules, scheduler, coordinator, repositories, caches, SQLite, configuration, documentation, and Facebook.
- Added HEALTHY, INACTIVE, ATTENTION, DEGRADED, FAILED, and UNKNOWN status models with inactive services excluded from failure precedence.
- Added explicit isolated local diagnostics, redacted clipboard/report export, and bounded atomic snapshot history.
- Added **SYSTEM HEALTH** to Home without creating a card, collector, schedule, or network action.
- Confirmed the next milestone is controlled Meta Phase 2 setup and live validation for Devour Lincolnshire only; Phase 2 is not active.

## System Health Centre v1.1 — operational actions and user feedback

- Added visible progress, success, warning, and persistent failure feedback for every Health action.
- Moved local refresh into a guarded worker while preserving the last valid snapshot on failure.
- Added isolated partial diagnostic results with bounded timing/history metadata.
- Expanded redacted Markdown reports with operational sections, recommendations, application version, and safe local Git metadata under `exports/health/`.
- Made log/data folder behaviour explicit and routed Facebook Operations through Home ownership.
- Improved UNKNOWN wording and safe cause-specific recommendations without adding collection, network, or Meta activity.

## Facebook Authentication Service — Stage 1

- Added an isolated four-endpoint FastAPI backend for the Facebook Login for
  Business HTTPS callback and server-side code exchange.
- Added short-lived, bounded, single-use in-memory sessions with independent
  polling credentials and rate-limited creation.
- Kept user and Page tokens backend-only and exposed only safe Page identity in
  protected status responses.
- Added reverse-proxy/container guidance and fully mocked permanent tests.
- Left `LoopbackCallback`, Facebook Operations, collection, routing, stores,
  scheduling, System Health and publishing behavior unchanged. The backend is
  not connected to NewsDesk Pro; Stage 2 will add desktop start/poll wiring
  after deployment and live Meta validation.
