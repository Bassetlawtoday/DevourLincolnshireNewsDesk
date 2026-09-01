# System Architecture

NewsDesk Pro uses explicit layers rather than a universal module engine:

1. `app.py` configures logging, creates the database and starts Tk.
2. `modules/dashboard.py` presents Home and orchestrates user actions.
3. `newsdesk/dashboard/` owns scheduling, collection coordination, current-process payloads, operational state and the Planning cache.
4. `modules/` owns each intelligence workspace and its presentation.
5. Module-specific services and collectors own collection, normalisation and editorial processing.
6. Shared UI infrastructure owns lifecycle callbacks, queues, theme values and image previews.

Dependencies flow from modules toward shared services. Shared services contain no Police, Fire, Sport or Planning editorial rules.

## Ownership

- Collectors own source access and raw-to-processed conversion.
- `DashboardRefreshCoordinator` runs collectors and records refresh outcomes.
- `DashboardResultRepository` owns complete current-process payloads.
- `DashboardStateStore` owns lightweight operational metadata.
- `PlanningResultCache` alone persists the full Planning briefing.
- Dashboard owns references to visible module windows.
- Modules own visible filters, selection and detail workspaces.
- `NewsDeskStoryQueue` owns card rendering and render cancellation.
- `ImagePreviewCache` owns bounded resized PIL previews; widgets own Tk images.

Planning remains specialised because it has a downloader and report window, Selenium collection and a persistent daily cache.

Council Intelligence follows the standard module path: `CouncilCollectionService`
collects three official HTTP sources, the Dashboard repository owns the current
processed payload, and `CouncilIntelligenceWindow` owns filtering and review.
Council priority classification is a small module-specific rules service, not
part of the shared editorial engines.

## Consolidation audit

Centralised: theme constants, search debounce, intelligence-window callback lifecycle, optional dashboard notification, live-window focus, story-queue rendering, image previews, and dashboard module metadata.

Deliberately local: filtering, scoring, publication output, source health wording, collection progress, headers with module-specific controls, and Planning lifecycle.

Already centralised: scheduling, repository storage, dashboard refresh coordination and Planning cache validation.

Presentation-only date conversion is centralised in `newsdesk.display_dates`.
It leaves stored timestamps, recency comparisons and scheduler values unchanged.

`newsdesk.facebook` is a dormant central ingestion boundary: official provider,
normalisation, identity/update handling, bounded atomic store and transparent
one-to-many routing. Current modules and dashboard orchestration do not consume it.

Facebook source ownership is newsroom-aware. Schema-v2 definitions carry formal
identity, organisation type, area/coverage, collection flags and route metadata;
the router consumes this evidence without assigning editorial priority.
# Facebook Operations boundary

`modules/facebook_operations.py` is a tools-level UI over `newsdesk.facebook.operations.FacebookOperationsController`. The controller composes the existing registry, official provider, store, diagnostic fixture, and health models. Local inspection never invokes the live provider; explicit provider/source actions are the only network-capable path. Facebook remains outside collectors, dashboard refresh orchestration, schedules, and intelligence-module adapters.

# System Health architecture

`newsdesk.health` separates serialisable models, local probes, bounded history, and snapshot assembly from `modules/system_health.py`. Authoritative sources are the dashboard state store and scheduler, current-process result repository, Refresh Coordinator, Planning cache, shared image cache, read-only SQLite query, Facebook Operations controller/registry/store, and local configuration/documentation files. Opening and refreshing Health never invokes content collectors or live providers.
# Controlled Facebook boundary

The Facebook subsystem separates browser OAuth (`oauth.py`), OS credential storage (`credentials.py`), non-secret Operations state, atomic registry metadata, the official Graph provider and the existing central ingestion pipeline. Only Devour Lincolnshire is connectable in v1; no publishing boundary is present.

# Facebook authentication service — Stage 1

`auth_service/` is a standalone HTTPS-callback backend for Facebook Login for
Business. It owns short-lived start/callback/status sessions and server-side
Meta exchange, but is not yet connected to the desktop. A reverse proxy owns
public TLS and forwards to one local service instance. Existing desktop OAuth,
collectors, routing, scheduling, stores and publishing boundaries are unchanged.
