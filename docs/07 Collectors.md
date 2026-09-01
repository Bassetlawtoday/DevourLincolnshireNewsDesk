# Collectors

Collectors remain module-specific. This consolidation does not introduce a universal scraper or scoring engine.

- Police collection is owned by `PoliceCollectionService` and Police source classes.
- Fire collection is owned by `FireCollectionService` and Fire source classes.
- Sport collection is owned by `SportCollectionService`, `SportScraper` and configured Sport sources.
- Planning navigation is owned by the Planning engine and its Selenium workflow.
- Government announcements are owned by `GovernmentFeedService`.
- Council collection is owned by `CouncilCollectionService` and three
  source-specific parsers in `council_scraper.py`.

`DashboardRefreshCoordinator` is an orchestration adapter. It invokes the appropriate collector, produces `DashboardRefreshResult`, stores successful payloads and records operational metadata. It does not reinterpret story content.

Existing collector result objects and module payload dictionaries remain authoritative. The older shared collection models under `newsdesk/core/` were not imposed on active collectors because doing so would create a broad compatibility migration without an observed defect.

Collectors owning browsers, sessions or executors retain their existing cleanup methods. No cleanup method was renamed in this pass.

Council uses ordinary `requests.Session` HTTP with a user agent, timeouts,
same-host enforcement and at most three listing pages. Listing dates are used
to stop pagination at the 14-day boundary. Article and source failures are
isolated and recorded in per-source health data.

Facebook collection uses only the approved-provider contract. The live adapter
targets the official Meta Graph API with verified HTTPS, bounded pagination,
minimum fields and structured errors. No Facebook sources are enabled in Phase 1.
# Controlled Facebook collection

Devour Lincolnshire collection uses the existing provider → normaliser → deduplicator → router → central store chain. The first selected run uses a 30-day window and requests at most two API pages of 25 posts. Subsequent runs begin five minutes before the newest stored post and rely on the existing identity/content deduplication. Comments and reactions are not requested.
