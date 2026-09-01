# Folder Structure

```text
app.py                         Application bootstrap
modules/                       Intelligence windows and Home presentation
newsdesk/dashboard/            Home orchestration services and module registry
newsdesk/services/             Module collection and processing services
newsdesk/sources/              Police, Fire and general source implementations
modules/council.py             Council Intelligence window
newsdesk/services/council_service.py Council priority and collection orchestration
newsdesk/sources/council_scraper.py Three official Council HTTP parsers
newsdesk/sports/               Sport-specific sources and discovery
newsdesk/story_queue.py        Shared progressive editorial queue
newsdesk/ui_support.py         Shared window lifecycle and debounce helpers
newsdesk/image_preview_cache.py Shared bounded PIL preview cache
newsdesk/theme.py              Stable shared visual constants
editorial/                     Editorial priority and ranking rules
config/                        Operational, source and branding configuration
database/                      Existing persistence schema and access
tests/                         Permanent non-live regression tests
tests/fixtures/council/        Representative official-source HTML fixtures
docs/                          Maintained technical documentation
```

Dependencies should point from `modules` into `newsdesk` services. Low-level shared helpers must not import module UI files. Static dashboard registry metadata does not dynamically import or discover modules.

Historical backup files remain untouched unless separately proven generated and safe to remove.

`newsdesk/display_dates.py` contains safe presentation-only UK date formatting.

`newsdesk/facebook/` owns provider, models, normalisation, deduplication, routing,
registry, store, service and adapter boundaries. Diagnostics live under `tools/`.

`docs/facebook_source_registry.md` is the operational schema and source-addition reference.
# Facebook Operations additions

- `modules/facebook_operations.py` — single-instance operational UI and read-only store viewer.
- `newsdesk/facebook/operations.py` — safe controller, diagnostic records, and atomic non-secret state.
- `docs/facebook_operations_centre.md` — operator guide.
- `tests/test_facebook_operations.py` — dormant-state and operations-boundary tests.

# System Health additions

- `newsdesk/health/` — status models, local probes, snapshot service, and bounded state.
- `modules/system_health.py` — single-instance read-oriented Health Centre.
- `docs/system_health_centre.md` — operator guide.
- `tests/test_system_health.py` — local health and safety tests.
# Facebook connection files

`newsdesk/facebook/oauth.py` owns browser OAuth and Page discovery. `newsdesk/facebook/credentials.py` owns OS secret storage. Operations coordinates them; registry JSON contains metadata only.

# Authentication service files

- `auth_service/` — standalone FastAPI app, environment configuration, models,
  bounded memory sessions, security helpers and server-side Meta client.
- `auth_service/Dockerfile` and requirements files — minimal single-service
  deployment and isolated dependencies.
- `docs/facebook_auth_service.md` — security, endpoint and reverse-proxy guide.
- `tests/test_facebook_auth_service.py` — mocked permanent service tests.
