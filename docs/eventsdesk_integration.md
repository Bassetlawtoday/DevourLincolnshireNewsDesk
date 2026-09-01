# EventsDesk integration

EventsDesk is an optional, isolated NewsDesk Pro module. The proven event collection engine lives in the top-level `eventsdesk` package and owns event-specific harvesting, source registry, deduplication, enrichment, lifecycle and SQLite persistence.

The UI adapter is `modules/events.py`. It consumes central NewsDesk Pro theme/header/window support and the central newsletter selection workflow. It does **not** import or modify Police, Fire, Planning, Sport, Council or Facebook collectors. The dashboard card is deliberately excluded from `MODULE_KEYS`, so `Refresh All` and the existing scheduler continue to orchestrate only the established five intelligence modules.

Newsletter/Ghost integration reuses `newsdesk.newsletter` and `modules.newsletter_desk`; EventsDesk does not store Ghost credentials or implement a second Ghost client. Event provenance is converted to the central `Story` model before the shared Add to Newsletter workflow is invoked.

Event data is stored under `data/eventsdesk/eventsdesk.sqlite`.
