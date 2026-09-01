# Developer Guide

## Adding an intelligence module

1. Keep source collection and editorial rules in module-specific services.
2. Add static Home metadata to `newsdesk.dashboard.registry` if the module belongs on Home.
3. Add its collector adapter to `DashboardRefreshCoordinator`.
4. Add an explicit Home opener and payload loader.
5. Use `IntelligenceWindowSupport` only when the lifecycle matches Police, Fire and Sport.
6. Use `NewsDeskStoryQueue` for a compatible editorial list and keep filter logic in the module.
7. Use `ImagePreviewCache` for local detail previews; create Tk images only on the Tk thread.
8. Preserve an optional dashboard callback so the module remains independently testable.

Do not add dynamic plugin loading, a universal scraper, generic scoring, or cross-module business-rule imports.

Council demonstrates the extension pattern: add static registry metadata,
one coordinator adapter, an explicit Home opener/payload adapter, a
module-specific collection service, source-specific parsers, and a focused UI
using shared lifecycle components. New source failures should be isolated and
represented in source-health metadata rather than hidden.

## Safety checks

Run `py -m py_compile` for every modified Python file, `git diff --check`, and focused pytest suites. Mock GUI and network boundaries in permanent tests. Confirm failed refreshes retain the previous repository payload and window destruction cancels tracked callbacks.

## Current locality hard-coding

Bassetlaw names occur in Police and Fire locality patterns, Sport editorial scoring and aliases, source configuration, branding, output copy and some filenames. Treat this as an inventory for a future profile phase, not permission to generalise it piecemeal.

Council workspace changes should preserve `NewsDeskActionBar`, `StoryEngine`,
the Fire/Police-compatible image operations and `IMAGE_PREVIEW_CACHE`. Keep raw
publication timestamps on `Story`; format dates only at Council presentation
and output boundaries.

Use `newsdesk.display_dates` for visible dates and `newsdesk.theme` for shared
editorial geometry. Production diagnostics use module loggers rather than
`print`. Preserve specialised Planning and Government structures.

Facebook work must use approved Meta access only. Never add browser scraping,
cookies or credentials. Use `--fixtures` for development; `--live` is explicit.
Phase 2 must use the adapter boundary instead of module-owned collectors.

New registry entries start disabled and must use verified Page IDs. Validate
unique canonical URLs, normalised tags, newsroom keys and secret safety before
review. Do not infer numeric Page IDs from public URLs.
# Developing Facebook Operations

Keep local status methods network-free. New live actions must remain behind an explicit user action and confirmation, use only the official provider, redact secrets, and run off the Tk thread. Never register Facebook with startup, schedules, REFRESH ALL, or active module routing without a separately approved phase. Registry mutations must use `FacebookSourceRegistry.save_document()` or `replace_source()` so full validation, backup, and atomic replacement remain intact.

Operations display values must be human-readable without mutating registry values: identifiers use title casing, Booleans use Yes/No, and missing fields use Required, None, Never, or Not available. Status always has a text label and never relies on colour alone. Disabled controls use the shared dark muted treatment with no active hover colour.

## Completion rule

A material feature, architectural change, or operational workflow change is not complete until:

1. tests are updated;
2. affected technical documents are updated;
3. the changelog is updated.

System Health probes must remain cheap, local, bounded, and observational. Unknown values must be labelled honestly. Active diagnostics require an explicit action, run off the Tk thread, and may not contact live websites or providers in v1. Exported health data must be redacted and must not include complete editorial payloads.

Every enabled operational button must provide visible progress and a clear success or failure result. Background actions must prevent overlapping calls, preserve the last valid result on failure, restore busy controls, ignore late UI results after close, and never rely solely on console output. UNKNOWN list text should state the operational cause—never observed, awaiting refresh, not persisted, or not tracked—while Safe Details may retain the technical explanation.
# Testing Facebook connection work

Mock browser, callback, credential store and Meta HTTP responses. Permanent tests must never perform live Meta calls or contain realistic tokens. Run the focused Facebook/Operations/System Health tests before the full suite.

# Developing the authentication service

Install `auth_service/requirements-dev.txt` separately. Construct the app with
injected configuration, session store and Meta client in tests. Never enable a
live Meta request in pytest. Preserve the four-route surface, fixed safe HTML,
bounded inputs, safe error categories, disabled access logging and absence of
wildcard CORS. Run one worker while storage is in memory. Desktop integration is
out of scope until Stage 2.
