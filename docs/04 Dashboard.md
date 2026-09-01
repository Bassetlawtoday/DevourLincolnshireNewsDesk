# Dashboard

`modules/dashboard.py` owns NewsDesk Pro Home presentation and orchestration. It does not implement source extraction or editorial scoring.

Dedicated services are responsible for:

- Scheduling: `newsdesk.dashboard.scheduler`
- Collection execution and outcomes: `refresh_coordinator`
- Complete in-memory payloads: `result_repository`
- Operational state: `state_store`
- Planning persistence: `planning_cache`
- Static module metadata: `registry`

The registry defines module key, display name, workload class, card visibility, repository support and the Planning-special marker. It is static Python metadata, not dynamic plugin loading.

Home permits at most two heavy collectors. Planning, Police and Sport are heavy; Fire and Government are light. Worker threads never create or modify Tk widgets. Home polls futures and performs completion UI work on the Tk thread.

Council is registered as a light module with a Home card and an interval-based
60-minute default. It participates in startup freshness and Refresh All. A
partial Council source failure retains usable results; failure of all three
sources preserves the previous repository payload.

Manual refresh callbacks use the same `_module_payload_updated` pathway as before. Successful payloads replace repository entries; failed runs preserve the last successful payload.

Government announcement timestamps use the shared readable UK date-and-time
presentation. Home otherwise retains its specialised cover-dashboard layout.
# Facebook Operations access

Home exposes a restrained **FACEBOOK OPERATIONS** tools control. It does not add an intelligence card, story count, schedule, startup task, or REFRESH ALL collector. Its default state is configured and inactive.

The Operations Centre is presented above Home after its initial layout completes. Selecting the control again restores and focuses the same window, including after minimisation. Closing it clears Home's tracked reference and restores Home focus; it is never permanently topmost or modal.

Home also exposes **SYSTEM HEALTH** beside Settings and Facebook Operations. It is a platform tool, not an intelligence card, scheduled module, startup collector, or REFRESH ALL target.

System Health delegates its Facebook Operations action back to Home. Home therefore remains the owner of the single Operations window and restores/focuses an existing instance rather than allowing Health to create an independent copy.
