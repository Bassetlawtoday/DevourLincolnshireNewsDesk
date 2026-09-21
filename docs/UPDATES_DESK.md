# Updates Desk

## Full-content requirement

Updates Desk lists newly discovered material but releases an item to Social
Desk only after substantive full article text has been verified. Selecting an
incomplete item starts the appropriate detail loader automatically. A source
image, metadata or a feed teaser does not satisfy this requirement. If the
source does not expose a fuller written article, the item remains visible and
locked with the extraction failure displayed for editorial review.

Updates Desk is the eighth NewsDesk Pro module. It collates newly discovered content after successful refreshes of Police, Fire, Sport, Council, Events and Local Democracy. Planning is deliberately excluded.

## Workflow

1. An eligible module refreshes manually, from the dashboard, or on a schedule.
2. Previously unseen stories enter Updates Desk as **New**.
3. An editor reviews an item and selects **Send to Social Desk**.
4. The item becomes red, is marked **Sent to Social Desk**, and cannot be transferred again.
5. When Social Desk successfully creates the Metricool draft, the item becomes **Sent to Metricool** with its reference and time.

Metricool failures do not advance the item to the final state.

## Deletion and duplicate protection

Deleting an Updates Desk entry affects only this queue. It does not alter the originating module or a Social Desk draft. A small permanent identity ledger remains after deletion, preventing the same source item from returning after a later refresh.

**Clear completed** hides all Metricool-confirmed entries while retaining their identities.

**Set current as baseline** hides the first-refresh backlog while retaining its identities. Later refreshes then show only genuinely unseen content.

The review panel displays complete stored copy, available source images, captions and credits. Local Democracy listing previews are automatically upgraded through the existing authenticated LDRS detail collector when selected. **Load full content** can refresh a public source article on demand.

## Data

Queue and identity data are stored in `data/updates_desk.sqlite`. Existing source-module stores are not changed.
