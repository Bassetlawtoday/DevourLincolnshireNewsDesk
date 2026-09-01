# Intelligence Modules

Police, Fire and Sport share infrastructure while retaining their editorial identities.

Shared:

- `IntelligenceWindowSupport` for close/focus and callback cleanup
- `DebouncedAction` for search input
- `NewsDeskStoryQueue` for queue rendering
- `ImagePreviewCache` for selected-story previews
- `newsdesk.theme` for established dark-theme constants
- Optional dashboard payload notification

Module-owned:

- Collector and source definitions
- Recency and normalisation rules
- Scoring, ranking and priority labels
- Searchable fields and filter semantics
- Statistics and source-health presentation
- Selected-story workspace
- Publication and export actions

The established public methods `load_stories(...)` remain unchanged. Sport retains its defensive recency boundary and ranking pipeline. Police and Fire retain their existing processing and filters.

Planning is not forced through the intelligence-window support because its report wrapper, downloader, retained application register and daily cache have a materially different lifecycle.

## Council Intelligence

Council collects Bassetlaw District Council, Nottinghamshire County Council and
East Midlands Combined County Authority (EMCCA) news. Every Bassetlaw District
Council release is `TOP PRIORITY`. Other releases use direct Bassetlaw location
evidence, selective district-wide impact rules, and the transparent categories
`HIGH LOCAL IMPORTANCE`, `LOCAL` and `REVIEW`. No numerical scoring engine is
used. All in-range stories remain accessible through source, priority, category
and text filters.

Council Intelligence v1.1 completes the editorial workspace with readable UK
dates, headline-first metadata, bounded image previews, standard image actions,
shared publishing outputs, Story Pack export and honest missing-image states.

Police, Fire, Sport and Council share the same broad editorial flow: headline,
readable metadata, image actions, summary, article, and the standard output bar.
Their priorities, filters, statistics and evidence remain module-specific.

The Facebook core is implemented but not populated or activated. Phase 2 may
adapt routed posts; receiving modules retain editorial scoring and presentation.

Fourteen initial official-source definitions are assigned to `devour_lincolnshire`,
but none is enabled or described as monitored. Future route keys remain evidence only.
# Facebook status

Facebook Operations is not an intelligence module. Stored Facebook posts are not injected into Police, Fire, Council, Sport, Government, or future module windows in this version.

Its independent window follows the same single-instance, focus-restoration, title-bar X, and callback-cleanup conventions as intelligence windows without changing their lifecycle.

System Health observes Police, Fire, Sport, Planning, Government, and Council through dashboard state and runtime repositories. It never invokes their collectors, scoring, queues, or publishing actions. Unknown runtime evidence and inactive services are not reported as module failures.
# Facebook Review routing

Controlled Devour Lincolnshire posts are stored and routed to Review only. They are not injected into Police, Fire, Sport, Planning, Government or Council queues in this pass.
