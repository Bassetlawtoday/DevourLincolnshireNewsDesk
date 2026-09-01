# Configuration

Configuration ownership is intentionally narrow:

- `config/dashboard.json` and `DashboardStateStore` own schedule policies, startup refresh and the two-heavy-worker limit.
- `config/branding.json` owns current newsroom branding read by Home.
- Source configuration files own source availability and extraction settings.
- `config/council.json` owns the three Council source identities and URLs,
  14-day recency, request bounds, Bassetlaw location terms and simple impact
  vocabulary.
- Scoring configuration and editorial modules own editorial thresholds.

Stable performance defaults currently live beside their owning implementation:

- Story render batch: 5 cards
- Progressive render interval: 50 ms
- Search debounce: 180 ms
- Image preview cache: 24 entries

These are internal defaults rather than user-facing newsroom settings.

Council defaults to `Every 60 minutes`. Available Council schedule choices are
Off, 30 minutes, 60 minutes, two hours and Manual only. Existing module
schedules are unchanged.

## Future newsroom profile inventory

The following remain Bassetlaw-specific and require a later, explicit profile design: application name and logo; locality lists and regexes; Bassetlaw editorial zones; local club aliases; source lists; output branding; file/export destinations; and some UI copy. Multi-newsroom support is not implemented.

Identity dimensions remain code-level constants in `newsdesk.theme`, not new
settings. No source, schedule or module-policy configuration changed.

`config/facebook_sources.json` is versioned and contains disabled source definitions.
Credentials use local environment variables listed empty in `.env.example`.

The registry now uses schema version 2 and contains 14 disabled Devour Lincolnshire
sources. Page IDs are deliberately blank. Validated metadata includes source
type, coverage, priority hint, media flags, tags and newsroom assignments.
# Facebook Operations configuration

`config/facebook_sources.json` uses schema version 3 and contains 15 disabled official sources. All Page IDs remain blank. `controlled_by_newsroom` identifies operational control without changing routing. Approved credentials come only from the process environment; no token or secret belongs in configuration or Operations state.

System Health validates local JSON syntax, required configuration presence, Facebook registry structure, and secret-like committed values without contacting sources or modifying configuration. Health history is versioned separately at `data/system_health_state.json`.
# Meta development configuration

Set `NEWSDESK_META_APP_ID`, `NEWSDESK_META_APP_SECRET`, and optionally `NEWSDESK_META_REDIRECT_PORT` outside Git, then restart. Tokens belong in Windows Credential Manager. Graph API version remains explicit in the Facebook registry.

# Facebook authentication service configuration

The isolated backend additionally requires `NEWSDESK_META_CONFIG_ID`, explicit
`NEWSDESK_META_API_VERSION`, and an HTTPS-only
`NEWSDESK_AUTH_PUBLIC_BASE_URL`. Session TTL, maximum sessions and per-minute
starts have bounded environment settings documented in
`facebook_auth_service.md`. The callback path is derived, never configured
independently. The repository default remains `v23.0`; deployment must reconcile
that explicit value with the Meta dashboard before live validation.
