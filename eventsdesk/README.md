# EventsDesk connector prototype — wave 2

Production-oriented starter package for a Midlands event discovery system.

## Included connectors

### API / aggregator
- Ticketmaster Discovery API
- Skiddle API
- Spektrix Public API v3 (venue client name required; public event data needs no authentication)

### Direct venue/network
- Academy Music Group / O2 Academy
- ATG
- Theatre Royal & Royal Concert Hall Nottingham
- Rock City Nottingham

### Reusable destination / heritage
- Tourism/destination calendar parser, including Visit Nottinghamshire
- National Trust property event-calendar parser
- English Heritage regional event-list parser
- Generic JSON/XHR event connector for dynamic council/event-search endpoints
- JSON-LD `schema.org/Event` parser with HTML-card fallbacks

## Source precedence

Lower `source_rank` wins during deduplication. Direct venue sources should normally rank ahead of aggregators. Missing fields from lower-priority duplicates may still enrich the winning record.

## Credentials

Set environment variables only when using credential-gated API connectors:

- `TICKETMASTER_API_KEY`
- `SKIDDLE_API_KEY`

Spektrix Web/Public API mode exposes public online event information without authentication. A venue's Spektrix `client_name` is still required to build its endpoint.

## Run

```bash
python -m eventsdesk.run --venues --output events.json
python -m eventsdesk.run --networks --output events.json
python -m eventsdesk.run --ticketmaster --venues --networks --output events.json
python -m eventsdesk.run --spektrix-client clientname="Venue Name" --output events.json
```

## Tests

```bash
pytest -q
```

## Dynamic council sites

`JsonEventsConnector` is the shared implementation for council/event-search pages that load results through JSON/XHR. Each council only needs configuration for:

1. the public endpoint;
2. query/paging parameters;
3. the JSON path containing results; and
4. a small row-to-`EventRecord` extractor.

This is intentionally separated from browser automation. The next discovery task for dynamic council sites is to identify their public XHR endpoints and configure this connector.

## Next implementation wave

1. Fingerprint Spektrix client names across the theatre inventory.
2. Identify council XHR endpoints and create configuration-only adapters.
3. Add persistence/source-history tables in SQLite.
4. Add recurring-event expansion for National Trust and other multi-date events.
5. Add validation/reporting so failed or changed source layouts are surfaced automatically.

## Wave 3: platform fingerprinting and endpoint discovery

Wave 3 adds two discovery utilities so EventsDesk can convert more of the source map into configuration rather than bespoke scraper code.

### Spektrix discovery

`SpektrixDiscovery` inspects a venue site and likely ticket/account links for a Spektrix client name, then validates the candidate against the public Spektrix v3 events API before it is treated as confirmed. It deliberately does **not** guess a client name and persist it without a successful API response.

`eventsdesk.theatre_inventory.THEATRE_PLATFORMS` contains the first Midlands theatre platform inventory. Platform membership and API client-name validation are kept separate.

### Council/dynamic endpoint discovery

`EventEndpointDiscovery` scans the server-delivered page and first-party JavaScript for likely event API/XHR URLs (`fetch`, Axios, jQuery, endpoint variables, `/api/...events...`, JSON search routes). Candidates are ranked and can be probed for JSON before being handed to `JsonEventsConnector`.

This gives council sites an API/XHR-first route while keeping Selenium/browser automation as a last resort.

Run live discovery on a machine with internet access:

```bash
python -m eventsdesk.discover theatres --output theatre-discovery.json
python -m eventsdesk.discover councils --output council-discovery.json
```

The discovery commands are read-only. They do not log in, submit forms, bypass anti-bot controls, or require browser automation.

## Wave 4 additions

- `CouncilHtmlConnector`: browser-free fallback for council/public-sector calendars when endpoint discovery does not find a usable JSON/XHR source. It tries JSON-LD first, then semantic event cards, then a conservative anchor/date proximity heuristic.
- Theatre platform inventory expanded with confirmed Spektrix usage for Lincoln Arts Centre and Lichfield Garrick.
- Recommended council order is now: validated JSON/XHR -> JSON-LD -> generic council HTML fallback -> source-specific adapter -> browser automation only as a last resort.

## Wave 5: council/public-sector platform fingerprinting

Wave 5 expands `COUNCIL_EVENT_SOURCES` to all 67 council/public-sector sources in the Midlands source map and adds runtime CMS fingerprinting plus extraction-strategy selection.

New components:

- `PlatformDiscovery`: conservative fingerprints for LocalGov Drupal/Drupal, Jadu, GOSS iCM, Umbraco, WordPress, Civica and Granicus.
- `CouncilStrategy`: selects endpoint-first, JSON-LD-first, HTML-card, or discovery mode from the actual page evidence.
- `CouncilHtmlConnector` labelled-block fallback: supports common council layouts that render headings followed by Cost / Date / Time labels.
- `discover councils`: now emits platform, confidence, recommended mode and endpoint candidates for every council source.

The guiding rule remains: prefer a validated first-party JSON endpoint, then structured data/server-rendered HTML, and use browser automation only when those routes fail.

## Wave 6: persistence and monitoring

Wave 6 turns connector output into a maintained local event database using SQLite.

New components:

- `EventStore`: canonical event persistence plus per-source aliases.
- First-seen, last-seen and last-changed timestamps.
- Change history for created, changed, missing and reactivated events.
- `harvest_runs` and `harvest_sources` tables for operational monitoring.
- Missing-event safety: a failed source run never marks that source's events missing.
- Multi-source provenance: deduplicated events retain every source alias that observed them.
- `eventsdesk.monitor`: simple CLI for active events and recent changes.

Default harvest command now persists to `eventsdesk.sqlite` as well as writing JSON:

```bash
python -m eventsdesk.run --venues --networks --database eventsdesk.sqlite --output events.json
```

Disable persistence when required:

```bash
python -m eventsdesk.run --venues --no-database --output events.json
```

Inspect recent changes:

```bash
python -m eventsdesk.monitor --database eventsdesk.sqlite --changes --limit 50
```

Inspect currently active events:

```bash
python -m eventsdesk.monitor --database eventsdesk.sqlite --active --limit 100
```

### SQLite tables

- `events`: one canonical deduplicated event record.
- `event_sources`: every source-specific observation/alias for that event.
- `event_changes`: created/changed/missing/reactivated audit history.
- `harvest_runs`: per-run totals and status.
- `harvest_sources`: per-source success/failure and event counts.

A canonical event becomes inactive only when all currently known source aliases are missing. If one connector fails, no disappearance is inferred from that failure.


## Wave 7: recurring occurrences and lifecycle

Wave 7 adds explicit occurrence expansion and parent-series tracking.

- `OccurrenceExpander` splits only explicit occurrence arrays (`occurrences`, `performances`, `sessions`, `dates`, `instances`). Plain multi-day ranges are left intact so festivals and exhibitions are not incorrectly fragmented.
- Every expanded performance gets a stable `occurrence_key` and shares a `series_key` with sibling dates/performances.
- Spektrix instances now carry series/occurrence identity directly.
- Deduplication preserves separate performances on the same date even when title and venue are identical.
- SQLite stores `series_key`, `occurrence_key` and `lifecycle_state`; Wave 6 databases are migrated automatically.
- Lifecycle states are `scheduled`, `postponed`, `cancelled` and `expired`. Expired/cancelled events stay in history but are excluded from `upcoming_events()`.
- Time-based lifecycle transitions are logged in `event_changes` with change type `lifecycle`.

Inspect only upcoming events:

```bash
python -m eventsdesk.monitor --database eventsdesk.sqlite --upcoming --limit 100
```

Inspect all performances belonging to a known series:

```bash
python -m eventsdesk.monitor --database eventsdesk.sqlite --series SERIES_KEY
```

## Wave 8: scheduling, retries and connector health

Wave 8 adds a production-oriented orchestration layer without introducing browser automation.

- `HarvestScheduler` runs only sources that are due according to their individual cadence.
- Bounded thread concurrency prevents the whole source estate from launching at once.
- Exponential retry/backoff is configurable per source family, with optional jitter.
- Failed connectors are passed to `EventStore.harvest()` as failures, so a transient outage never marks existing events missing.
- `connector_health` stores last attempt/success/failure, consecutive failures, totals, event count, attempts, duration and last error.
- Default policy profiles are included for high-volume aggregators, venues, theatres, tourism, councils and heritage sources.

Suggested starting cadences:

- high-volume aggregators: every 30 minutes;
- direct venues: every 2 hours;
- theatres: every 3 hours;
- tourism portals: every 6 hours;
- councils and heritage: every 12 hours.

These are configuration defaults, not hard limits. They can be tuned source-by-source once live run history shows how frequently each source actually changes.

Inspect connector health:

```bash
python -m eventsdesk.scheduler --database eventsdesk.sqlite --health
```

## Wave 9 — 374-source registry and staged rollout

Wave 9 adds a machine-readable registry for all 374 researched Midlands event sources.
Each source has a connector family, schedule profile, priority, activation state and rollout batch.
The registry deliberately distinguishes:

- `ready` — connector route exists and may be run now;
- `probe` — reusable route is plausible but must be validated against the live source first;
- `hold` — no production connector exists yet.

Current registry totals: 374 sources, 15 batches, 111 currently runnable. Batches 1–4 contain 100 runnable sources; Batch 5 contains the final 11 runnable sources plus probe rows. Later batches are validation/adapter work.

Useful commands:

```bash
python -m eventsdesk.rollout --summary
python -m eventsdesk.rollout --list-batches
python -m eventsdesk.rollout --batch 1 --dry-run
python -m eventsdesk.rollout --batch 1 --database eventsdesk.sqlite
python -m eventsdesk.rollout --batch 1 --status --database eventsdesk.sqlite
```

`--force` ignores normal cadence for a deliberately requested test run. Normal operation honours the scheduler profile for each source. A completed batch reports raw yield, deduplicated yield, failure count and duplicate rate; connector health remains queryable afterwards.

Ticketmaster and Skiddle remain credential-gated through `TICKETMASTER_API_KEY` and `SKIDDLE_API_KEY`. Probe and hold sources cannot be run accidentally through the rollout command.

## Wave 10: live rollout probe

Use the one-shot probe before a persistent harvest. It does not retry or write events,
and classifies failures so a missing API key is not confused with a parser defect:

    python -m eventsdesk.probe --batch 1 --workers 8 --timeout 10 --output batch1_probe.json

Statuses: `success`, `zero_yield`, `credential_blocked`, `network_unavailable`,
`http_error`, and `parse_or_connector_error`.

Wave 10 also corrects several registry start URLs to their actual event calendars
(Rock City gig guide, TRCH What's On, Clumber Park events, and English Heritage Midlands).

## Wave 11 - validated structured HTML rollout

Wave 11 converts a first tranche of previously `probe` P1 sources into production-ready structured HTML sources using live 2026 listing evidence. The generic `StructuredHtmlConnector` now supports schema.org/Event JSON-LD, semantic event cards, heading-plus-date layouts, compact UK date ranges (including formats such as `Tue 1 - Sat 5 Sep 2026`), and dated-anchor list views.

Fourteen sources were promoted from `probe` to `ready`: Rescue Rooms, Motorpoint Arena Nottingham, Nottingham Playhouse, Vaillant Live, Chatsworth, De Montfort Hall, Curve Leicester, National Space Centre, Royal & Derngate, Symphony Hall Birmingham, Birmingham Rep, Warwick Arts Centre, Royal Shakespeare Company, and Town Hall & Symphony Hall Birmingham.

Registry state after this tranche: 125 ready / 131 probe / 118 hold (374 total).

## Wave 12 - remaining P1 validation tranche

Wave 12 validates a further 12 P1 sources against current 2026 public event listings and promotes them from `probe` to `ready`. Where a theatre is known to use Spektrix but the public website already exposes reliable server-rendered listings, the registry now uses the generic `structured_html` connector rather than blocking rollout on a guessed or unvalidated Spektrix client identifier.

Promoted sources: Derby Theatre, Buxton Opera House, Birmingham Hippodrome, Utilita Arena Birmingham, Wolverhampton Grand Theatre, Coventry Building Society Arena, Belgrade Theatre, Warwick Castle, New Vic Theatre, Trentham Estate, Ironbridge Valley of Invention (now routed through National Trust), and Midlands Arts Centre (MAC).

Registry position after Wave 12: **374 total / 137 ready / 119 probe / 118 hold**, with only **12 P1 probe sources** remaining.


## Wave 13 – final P1 validation pass

Wave 13 promotes seven additional P1 sources and adds a reusable `LegacySpektrixEventListConnector` for older Spektrix `website/EventList.aspx` catalogues. The structured HTML date parser now accepts compact dates such as `27Aug 2026` and comma-formatted ranges such as `25 - 27 September, 2026`.

Registry state after Wave 13: **144 ready / 112 probe / 118 hold**. Only five P1 probes remain: New Theatre Royal Lincoln, Engine Shed Lincoln, Black Country Living Museum, Worcester Theatres, and Castle Theatre Wellingborough.

The legacy Spektrix connector follows a bounded number of month catalogue links, reconstructs month/year context, creates one occurrence per listed performance day, and filters non-event add-ons such as Ticket Protection and WatchWord Glasses.

## Wave 14 - Final P1 endpoint/platform pass

Wave 14 resolves two of the five remaining P1 probes without browser automation:

- **Black Country Living Museum** now uses a dedicated server-rendered calendar connector against `https://bclm.com/tickets-and-events/whats-on/`. It follows pagination and preserves explicit repeated dates as individual occurrences while leaving genuine multi-day ranges intact.
- **Castle Theatre Wellingborough** is updated to its current Parkwood Theatres URL and uses the reusable structured HTML connector.

The registry is now **146 ready / 110 probe / 118 hold**. Three P1 probes remain deliberately unpromoted: **New Theatre Royal Lincoln, The Engine Shed Lincoln, and Worcester Theatres**. Their public master catalogues are client-rendered or expose placeholder templates in crawlable HTML. Their event/detail pages are readable, but a stable first-party programme-discovery endpoint has not yet been validated, so Wave 14 does not introduce fragile browser automation or guessed selectors.

## Wave 15
- Added `SecondaryVenueIndexConnector` for venue catalogues that are client-only on the first-party site but have stable third-party venue indexes.
- New Theatre Royal Lincoln uses Artspod as a discovery fallback; direct venue records remain authoritative.
- The Engine Shed Lincoln uses Gigantic as a discovery fallback; direct venue records remain authoritative.
- Added `PazazProjectsConnector`, which probes first-party PAZAZ project/event JSON endpoints and parses common `project_*` fields.
- Worcester Theatres remains in `probe` until one of its first-party PAZAZ endpoints validates live.
- Registry: 148 ready / 108 probe / 118 hold. Only one P1 probe remains: Worcester Theatres.

## Wave 16 - Worcester Theatres / Auto-Spektrix

- Worcester Theatres is now routed through `AutoSpektrixConnector` after first-party confirmation that Swan Theatre and Huntingdon Hall migrated to Spektrix.
- `AutoSpektrixConnector` discovers/validates the Spektrix client name at runtime and never accepts an unvalidated candidate.
- Spektrix event harvesting now fetches event instances explicitly when the event feed does not embed them.
- Worcester Theatres, Swan Theatre Worcester and Huntingdon Hall are promoted to `ready` configuration.
- The P1 `probe` queue is now empty. Fourteen P1 sources remain in `hold` and still need dedicated production connector work; these are not being misreported as complete.

## Wave 18 — final P1 aggregator/ticketing review

- Added `SeeTicketsMidlandsConnector`, using See Tickets' public server-rendered Event Finder pages with bounded pagination and Midlands venue/location filtering.
- Added `AllEventsApiConnector` for the official AllEvents commercial API. It remains `probe` until a commercial API key/product endpoint is issued and validated.
- Eventbrite remains `hold` because its general public event discovery API is not available.
- Facebook Events remains `hold` because general public event discovery is platform/login restricted.
- TicketSource remains `hold` as its official API is account/organiser scoped rather than a UK-wide discovery feed.
- The Ticket Factory remains `hold/redundant` because it is now powered by AXS and direct NEC/bp pulse LIVE/Utilita Arena sources are already in the registry.


## Wave 24
Promoted eight P2 sources: Nottingham Arts Theatre, Peggy's Skylight, Trent Bridge, Mansfield Palace Theatre, Newark Showground, and the shared ARC racecourse pattern for Southwell, Uttoxeter and Worcester.


## Wave 35 - live harvesting phase
Source expansion is frozen at 313 runnable sources. The packaged JSON registry is now synchronised to the Wave 34 registry. `python -m eventsdesk.harvest --list --limit 20` previews the rollout; `python -m eventsdesk.harvest --limit 20` performs a controlled first live harvest into SQLite plus JSON. Remove `--limit` only after reviewing connector health and duplicate yield.

## Wave 36 - environment-aware live validation
The first controlled 10-source harvest was attempted in the build environment. All 10 requests failed before HTTP because the container could not resolve public DNS. Wave 36 adds a three-host network preflight so a global environment outage is reported once as `environment_network_unavailable` and does not get misclassified as ten connector failures. Use `python -m eventsdesk.harvest --network-check` to verify the runtime before a live harvest.

## Wave 37 - Windows live validation launcher
For the first real live validation on Windows, extract the package and double-click `run_live10_windows.bat`. It creates a local `.venv`, installs requirements, verifies external network/DNS access, runs the first 10 high-authority sources, and writes `EventsDesk_Live10_Result.json`, `EventsDesk_Live10_Summary.txt`, and `EventsDesk_Live10.sqlite`. Global network failure is stopped before connectors run, so it cannot be mistaken for scraper failure.

## Wave 38 - live data quality
The first live 10-source run proved the harvesting pipeline (242 raw / 215 deduplicated, 10/10 successful). Wave 38 improves reusable structured HTML extraction before scaling: response encoding repair, normalized mojibake repair, and conservative optional extraction of image, description, category, price, age restriction and explicit listing time. Existing fallbacks remain intact.

## Wave 40 - live 25-source cleanup
The 25-source benchmark exposed 787 false Theatre Severn records titled `Booking and More Information`. Wave 40 adds generic CTA-title filtering, source-level repeated-title anomaly reporting, a legacy Spektrix CTA guard, the corrected current Regent Theatre ATG URL, the current Mansfield Palace Theatre council URL, and a first-party Warwick Arts Centre card connector. Re-run the same 25-source benchmark before expanding to 50.


## Wave 41 - 100-source recovery pass
Browser-compatible request headers and explicit access-blocked classification; deeper and numeric date extraction; council child-calendar discovery; National Trust property /events fallback; current-route corrections for Nottingham Arts Theatre, Chapel Street Arts Centre (former Déda), Pavilion Arts Centre, Nottingham City Council and Rugeley Rose; and current Warwick Arts Centre parsing. Re-run the same 100-source benchmark before scaling further.


## Wave 42 - National Trust recovery
Fixed the shared National Trust JSON-LD path by importing `parse_jsonld_events` explicitly. This removes the live `NameError` seen for Clumber Park and the National Trust network source. Access-blocked and zero-yield sources remain non-fatal and visible in harvest health output.


## Wave 43 - scalable output
Large harvests no longer embed every event inside the summary JSON. SQLite remains the authoritative database; a compact JSON summary is written to `--output`, while deduplicated events are streamed one-per-line to a JSONL file (default: `<output_stem>_events.jsonl`). Use `--events-output PATH` to choose another export path. This prevents large 200/313-source runs from failing while serializing one giant in-memory JSON document.


## Wave 44 - second-hundred recovery
Updated the ten live failures from the 200-source benchmark using current first-party or stable local fallback routes. Persistent HTTP 406 is now classified as access-blocked rather than a connector-code failure.


## Wave 45 - final connector recovery
Nine stale/SSL-prone source routes were refreshed. Missing Skiddle/Ticketmaster credentials are now reported as `credential_missing`, separate from true connector failures.


## Wave 46 - Data Intelligence
Adds deterministic source/geography enrichment, controlled category classification, category contamination cleanup, per-event quality score/status, and persists those quality fields in SQLite. Existing lifecycle_state continues to identify expired/cancelled/postponed records.

## Wave 47 - Data Quality & Lifecycle
Wave 47 expands geography inference from the source registry, repairs additional city/district values accidentally stored as counties, refines classification so source names do not bias every record toward a venue type, and adds source-type category fallbacks only when event text is otherwise unclassified. SQLite retains full active/history records, while `current_events()` and the streamed JSONL export contain only scheduled/postponed publication-facing events. Harvest summaries now report `current_events` and `expired_or_past_events` separately.
