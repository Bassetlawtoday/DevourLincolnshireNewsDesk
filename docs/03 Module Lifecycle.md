# Module Lifecycle

## Dashboard-managed modules

1. Home checks its owned window reference.
2. A live window is deiconified, raised and focused.
3. Otherwise Home constructs one window and tracks its destruction.
4. An existing repository payload is injected through the module's established `load_stories(...)` or `load_results(...)` method.
5. Opening a populated module never starts a second collection.

Police, Fire and Sport use `IntelligenceWindowSupport` for title-bar/CLOSE handling, tracked callbacks and Home focus restoration. `DebouncedAction` owns the single pending search callback.

Council uses the same lifecycle. Its worker communicates through an in-memory
queue polled by a tracked Tk callback, so the worker never calls Tk directly.
Repository payload loading uses `load_stories(...)` and never recollects.

On close, tracked callbacks are cancelled before widget destruction. The owning Dashboard reference is removed by the window destroy binding. Child widgets own their `CTkImage` references and release them with widget destruction.

## Manual refresh

A module performs its existing collection and processing. On success it sends its unchanged payload through the optional `dashboard_result_callback`. Home stores the payload, updates the count and timestamp, records refresh state and recalculates the schedule. A failure does not send a replacement payload, so the previous successful repository entry remains available.

## Planning

Planning has two distinct owners: the downloader and the report window. A valid cached report opens directly. The downloader is opened only when a report payload is unavailable or the user chooses to refresh/troubleshoot.

Facebook Phase 1 has no window lifecycle. Its service is callable explicitly,
is absent from startup and Refresh All, and exposes routed views for future adapters.
# Facebook Operations lifecycle

Facebook Operations is a single-instance auxiliary window, not an intelligence module. Reopening focuses the existing window. Shared lifecycle support owns close behaviour, callback cancellation, and Home focus restoration. Diagnostics execute in one background worker and marshal completion back to Tk; opening, closing, and local status refresh make no network request.

# System Health lifecycle

System Health is a single-instance, non-modal tools window using shared foreground presentation, callback cancellation, and Home focus restoration. Local snapshots use cheap state probes; explicit diagnostic bundles run in one worker and marshal results to Tk. Closing never affects collectors or NewsDesk Pro itself.
# Facebook lifecycle

Facebook remains manual and dormant at startup: configure app, authorise, select and confirm Page, validate, explicitly enable, then explicitly collect. Disconnect removes tokens and disables collection without deleting Page metadata or posts.

# Authentication-service lifecycle

Stage 1 authentication sessions are created only by `POST /facebook/start`,
expire automatically, consume callback state once and disappear on process
restart. The service is single-instance and independent of the Tk lifecycle.
NewsDesk does not call it yet; Stage 2 will add desktop start/poll integration.
