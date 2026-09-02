# Devour Lincolnshire NewsDesk — V40.1 handover

## Starting point for the next conversation

Continue **Devour Lincolnshire NewsDesk** from version **V40.1**. The next major module is **Planning Intelligence**. Before changing code, inspect the latest complete project ZIP and agree the proposed scope with the user. Do not guess, create speculative patches or solve source-access problems one at a time.

Repository: `https://github.com/Bassetlawtoday/DevourLincolnshireNewsDesk`

Windows project folder: `C:\Users\Windows\Documents\DevourLincolnshireNewsDesk`

Local image library: `C:\Users\Windows\Desktop\Devour News Lincs Images`

## Product direction

Devour is being simplified into a Lincolnshire information-collection platform. Its primary decision is geographical: if a relevant item concerns Lincolnshire, it should be included and shown in date order.

Police, Fire, Council and Sport no longer need editorial-priority scoring as their principal workflow. The emphasis is:

1. Collect from the complete managed source set.
2. Confirm Lincolnshire relevance.
3. Extract usable title, date, content, links and an appropriate image.
4. Retain the last successful collection between sessions.
5. Allow the user to inspect the source and create a Social Desk draft.

## Modules completed so far

### Police Intelligence

- Lincolnshire-focused collection with managed official and relevant regional sources.
- Date-ordered presentation rather than editorial prioritisation.
- Social Desk hand-off is present.
- Persistent last-refresh information is retained.
- Refresh progress/timing work has been added, but performance and source behaviour still require full end-to-end testing.

### Fire Intelligence

- Lincolnshire Fire and Rescue news plus relevant incident/news sources, including Humberside coverage where geographically relevant.
- Incident pages without photographs use a branded **Devour Lincolnshire — Fire Intelligence** fallback rather than an unrelated image.
- Video is not treated as a still image.
- Social Desk hand-off is present.
- Fire refresh results persist between sessions through the shared snapshot store.
- Low story volume can be legitimate; source warnings should remain visible.

### Council Intelligence

- Coverage is intended to include Lincolnshire County Council, City of Lincoln Council and all Lincolnshire district/borough councils.
- Direct news, RSS, site-search and summary-only fallbacks are used according to what each official site permits.
- Blocked official pages remain labelled **SUMMARY ONLY** and retain an **OPEN SOURCE** route.
- URLs that genuinely occur within article content should remain usable; the article's own source URL is held separately and appended at social-send time.
- Social Desk hand-off is present.
- Council results persist between sessions through the shared snapshot store.

### Local Democracy / LDRS

- Uses the user's authorised LDRS API access.
- Collects Lincolnshire-relevant Local Democracy stories, article text and available LDRS media.
- Transfers drafts to Social Desk with source URL, image URL, caption and required credit.
- LDRS media can include images, audio and other attachments; only a suitable still image should be selected for image use.
- LDRS results already retained their information between sessions.

### Events Intelligence

- Broad Lincolnshire events coverage from venues, theatres, visitor organisations, councils and event listings.
- Cinemas are intentionally excluded.
- The collector tries to retain event date/time, venue, town, description, source link and a relevant source image.
- URLs appearing inside descriptions are presented as usable links.
- Social Desk hand-off is present.
- Events results retain their information between sessions.
- Full testing is still needed for incorrect hero-image selection, thin descriptions and source buttons on difficult sites.

### Sport Intelligence

- Lincolnshire sports and clubs are collected from the managed source set.
- The intended active window is the most recent seven days; old sports articles are not useful for this workflow.
- Videos must not be brought across as images.
- Date order replaces editorial prioritisation.
- Social Desk hand-off is present.
- Sport results persist between sessions through the shared snapshot store.
- Content depth and yield across the full source list still need wider testing. Do not assume a zero-yield source is broken until its current official output and access method have been checked.

### Social Desk and Metricool

- Intelligence modules add content to a shared local Social Desk draft store.
- Drafts remain local until the user explicitly sends them.
- Metricool is configured with the user's REST API token, user ID and verified brand.
- The connected Facebook page for **Devour News — Lincs** has been verified.
- Social Desk sends **Metricool drafts only**: `draft=true` and `autoPublish=false`. It never publishes automatically.
- A successful Facebook test draft has been confirmed in Metricool Planning.
- A normal content draft without an image has also been confirmed.
- The article/event source URL is stored in its dedicated field and automatically included in the outgoing social copy.
- Bare URLs contained within useful content are preserved so social platforms can make them clickable.
- Images require a credit and explicit confirmation that rights are approved for social use.
- Public source-image URLs are first imported by Metricool. If that import fails, the entire draft is stopped and retained locally. It must not silently send without the selected image.
- The visible error is: **Draft not sent — image could not be imported.**
- The user may then retry, remove the image or select another image.
- V40.1 adds an **IMAGE LIBRARY** button rooted at `C:\Users\Windows\Desktop\Devour News Lincs Images`.
- Local JPEG/PNG selection uses Metricool's official planner-media upload route. A local-image draft has been successfully confirmed in Metricool.

## Shared persistence architecture

Police, Fire, Sport and Council use the shared `newsdesk/dashboard/feed_snapshot_store.py` implementation. The store writes atomic JSON snapshots beneath `data/feed_snapshots/`, maintains a backup and restores the last successful collection on module or dashboard launch.

A failed refresh must not overwrite a previously successful snapshot. Runtime snapshots are deliberately excluded from Git.

Events and LDRS retain their existing persistence mechanisms.

## Known limitations and testing points

- Collection quality is source-dependent. Some official sites block automated article access, expose only summaries or change markup without notice.
- A source being enabled does not guarantee it published a new Lincolnshire item within the active date window.
- Source health, yield and failure information should be presented clearly rather than hidden.
- Some collected OpenGraph images are logos or generic placeholders. These should not be mistaken for story photographs.
- Metricool may reject or time out while importing a particular public image even when text-only delivery works.
- Local image upload is confirmed for JPEG/PNG, but broader network-specific size and aspect-ratio combinations still require testing.
- Events image relevance and Sport content depth require particular attention during full testing.
- Planning is the remaining major intelligence module and should be designed from the audited current codebase, not from assumptions based on earlier versions.

## Required working method for future changes

The user has explicitly requested the following process:

1. Start from the newest complete ZIP or confirmed GitHub checkpoint.
2. Audit the existing implementation and every relevant source before writing code.
3. Explain the evidence, root cause and exact proposed change.
4. Obtain agreement before coding when the scope has not already been explicitly authorised.
5. Centralise shared behaviour and reuse existing services instead of producing successive one-source patches.
6. Make a coherent batch, run relevant tests and validate the installer before delivery.
7. Preserve working architecture and unrelated user changes.
8. Do not claim a live external integration is working until the user confirms it from their account.

## How installation instructions are delivered

Changes are normally supplied as a versioned ZIP containing:

- A `package` folder.
- A clearly named PowerShell installer.
- A small payload containing only the intended replacement/new files.
- A README explaining scope.

The PowerShell command should search recursively beneath Downloads so the user does not need to type the extracted folder name. The standard form is:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned -Force

$installer = Get-ChildItem "$env:USERPROFILE\Downloads" `
    -Filter "INSTALL-EXACT-VERSION-NAME.ps1" -Recurse |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

if (-not $installer) {
    throw "The installer was not found. Extract the ZIP first."
}

Set-Location $installer.DirectoryName
Unblock-File $installer.FullName
& $installer.FullName
```

Every installer should:

- Verify the project folder.
- Back up every replaced file.
- Install only the declared payload.
- Compile/test the installed result.
- Restore the previous files automatically if validation fails.
- Never expose, copy or commit API tokens, databases, local drafts, downloaded images or runtime snapshots.

## Immediate next task: Planning Intelligence

Begin with an audit and an agreed design. Check the existing planning module, its current sources, geographic filtering, persistence, collection speed, application detail extraction, document links and Social Desk transfer. Reuse the shared date-order, link, image, persistence and Social Desk conventions where they fit Planning, but do not force an inappropriate news-article model onto planning applications.
