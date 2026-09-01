# NewsDesk Pro Data Retention Policy

**Owner:** Devour Lincolnshire  
**System:** NewsDesk Pro  
**Version:** 1.2 — 31 August 2026  
**Review:** Annually, and whenever a source, licence, purpose or storage design changes

## Purpose and scope

This policy explains what NewsDesk Pro stores, where it is stored, why it is used, how long it is kept, and how it is disposed of. It covers Planning, Police, Fire, Sport, Council, Events and Local Democracy Intelligence; Social Desk; downloaded media; operational logs; configuration and audit records.

NewsDesk Pro is an internal editorial research and production system. Information is collected only for legitimate newsroom discovery, verification, analysis, selection, production, provenance and publication. Retention is limited to what remains necessary for those purposes, subject to applicable source licences, copyright, data-protection law, journalism protections and the public interest.

## Storage locations

The live installation is held locally under `C:\Users\<user>\Documents\DevourLincolnshireNewsDesk`. The principal locations are:

| Information | Local location | Purpose | Retention and disposal |
|---|---|---|---|
| Local Democracy article metadata, authors, councils, categories and dates | `data\contentdesk\contentdesk.sqlite` | Search, discovery and aggregate analysis | 12 months; deleted automatically unless newsletter-selected |
| Local Democracy full article text, source-image URL, caption and credit | Same database; downloaded working media in the local cache | Editorial review, copying and newsletter selection | 90 days; full copy is minimised automatically unless newsletter-selected |
| LDRS author/reviewer email addresses | Never intentionally retained after collection | Not required for the newsroom functions | Removed on every retention run |
| Events and source provenance | `data\eventsdesk\eventsdesk.sqlite` | Event discovery, verification, history and newsletter selection | Expired events: 90 days, then deleted unless newsletter-selected |
| Planning records | `data\newsdesk.db` | Planning monitoring and editorial research | Active records while required; concluded records reviewed/removed after 12 months |
| Police, Fire, Sport and Council live results | Application memory during the current session | Current newsroom monitoring | End of session, except an item selected into a newsletter |
| Social Desk local drafts | `data\social\drafts.json` | Prepare and review posts before transfer to Metricool | Unsubmitted drafts: 90 days; Metricool delivery references: 12 months |
| Metricool connection settings | `data\social\metricool.json` | Identify the selected Metricool user and brand | While the integration is active; API token is encrypted for the signed-in Windows user |
| Newsletter editions and selected copy | `data\newsletter\editions.json` | Editorial production, provenance, corrections and publication record | Permanent editorial archive unless an authorised editor decides otherwise |
| Rights-approved newsletter images and rights records | `data\newsletter\images` and edition records | Evidence of rights review and faithful publication archive | Permanent with the associated editorial record |
| Temporary source images | `cache\images` | Short-lived display and processing | 14 days, automatically deleted |
| Application logs | `logs` | Fault diagnosis, security and operational accountability | 30 days, automatically deleted |
| Retention audit | `data\retention\cleanup_audit.jsonl` | Demonstrate that this schedule was applied | Permanent non-content compliance record; reviewed annually |
| API keys and settings | Local configuration files excluded from Git | Authorised source access and scheduling | While the integration is authorised; remove immediately when access ends |
| Backups | `archive\backups` | Recovery from failed installations or data loss | Review quarterly; securely delete obsolete copies, applying the same substantive limits where practicable |

The program source may be checkpointed to GitHub. Databases, API keys, downloaded images, backups and generated source data must remain excluded from source-control commits.

## Rules and safeguards

1. Data minimisation: retain only fields needed for an identified editorial or operational purpose. LDRS contact emails are removed because they are not needed by the product.
2. Newsletter protection: any source item selected into a newsletter is protected from automatic source-record deletion so the editorial decision, provenance, rights evidence and published output remain auditable.
3. Draft protection: the system flags abandoned drafts for review after 90 days but does not silently delete editorial work.
4. Aggregate analysis: non-identifying totals may be retained after source detail expires where the total cannot be used to reconstruct an article or identify an individual.
5. Source rights: retention does not create a right to republish. Reuse remains subject to the supplier's terms, copyright, embargo, credit, caption and permission information recorded for the item.
6. Security: local access is limited to authorised users; credentials are not displayed in the dashboard or committed to Git; backups and exports require equivalent protection.
7. Accuracy and correction: source corrections, embargoes, takedowns and rights changes must be reflected promptly in working and newsletter records where relevant.
8. Disposal: database records are deleted or minimised by the retention process. Files are deleted from local storage. Sensitive exports and obsolete backups must be securely deleted by an authorised user.

## Operation and accountability

The **Data Retention Centre** on the main dashboard shows this schedule, the installed policy and the latest cleanup result. Retention runs at application startup and can also be run manually. Each run appends a timestamped record containing policy version, outcome and counts; it does not duplicate article content in the audit.

The editor/data controller is responsible for reviewing exceptions, legal holds, complaints, subject requests, licence changes and obsolete backups. A documented legal hold may suspend deletion for a specific record; the reason, scope, approver and review date should be recorded. Requests for access, correction, restriction or erasure are assessed under applicable law and the journalistic purpose of the record—not granted or refused automatically.

## Availability

The authoritative installed copies are:

- `docs\NEWSDESK_DATA_RETENTION_POLICY.html` — readable, printable and shareable copy
- `docs\NEWSDESK_DATA_RETENTION_POLICY.md` — source-controlled policy text

The HTML copy can be opened at any time from **NewsDesk Pro → Data Retention** and supplied to an auditor, source partner, regulator or other appropriate requester. This document is an operational policy and should be reviewed by the organisation's data-protection/legal adviser where legal assurance is required.
