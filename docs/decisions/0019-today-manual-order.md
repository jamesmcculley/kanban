# 0019. Manual drag order for Today's "Due & overdue" list

- Status: accepted
- Date: 2026-09-25
- Departs from standard: none

## Context

Today's "Due & overdue" section sorts by due date (see `scheduled_cards`): oldest overdue first.
That's a reasonable default, but it isn't always the order you actually want to work through your
day in -- an old overdue task might matter less right now than something due today. The owner
asked to be able to rearrange it.

## Decision

- **Manual order overrides date order entirely, not just within a day** -- confirmed with the
  owner rather than assumed, since the alternative (dragging only breaks ties within the same due
  date, dates otherwise still sort first) is a materially smaller, safer-looking change that would
  not actually let you put an old overdue task below something due today, which is the whole point
  of the request.
- **A new field, `Card.today_order`, not a reuse of the existing `position`.** `position` is
  already meaningful (order within a card's own column on its own board); reusing it for Today
  would mean dragging on Today silently reorders that board's list too, which nothing asked for and
  would surprise anyone looking at the board itself later. `today_order` is a second, independent
  number that only `today_view`'s sort of the `due` list ever reads -- Scheduled and Review's own
  "upcoming" keep sorting by date alone, untouched.
- **A card with no `today_order` yet sorts after every card that has one, in the original date
  order** -- not interleaved by date. This is what "new cards land at the end until you drag them"
  (the same framing used when this got greenlit) means concretely: touch the list once and it
  becomes fully manual from that point forward; anything that shows up later (newly due, or simply
  never dragged) queues up after the manually-ordered block rather than trying to guess where it
  "should" go relative to dates that no longer drive the sort.
- **One drag reindexes the *whole visible list*, not just the two rows involved** -- the same
  "send the full order, not a delta" shape `reorder_columns`/`move_card`'s column reorder already
  use. `Store.reorder_today(ids)` looks each id up by scanning `all_cards()` once (cards can span
  several boards, unlike a column reorder, so there's no single slug to scope the lookup to) and
  assigns `today_order = 0..N-1` in the given order.
- **Only "Due & overdue" is reorderable.** "Completed today" is history, not a queue -- reordering
  it has no obvious meaning. "Created today" is informational (what got made today), not a
  priority list either. Scoping this to the one section that actually reads as "what should I do,
  in what order" keeps `today_order` meaning one specific thing.
- **The whole row is the drag handle, no separate grip element** -- same as a card within a board
  column (`.card` already sets `cursor: grab`; nothing else in that list gets its own grip icon
  either). A short "drag to reorder" hint next to the section heading exists only because this is
  a brand-new capability nobody would otherwise discover; the interactive elements inside a row
  (checkbox, hide button, edit pencil) are in Sortable's `filter` so a click on them isn't mistaken
  for a drag start.

## Consequences

- Unit tests cover `reorder_today` (order is applied in the given sequence, spans multiple boards
  in one call, and silently skips an id that doesn't resolve to a card). A route test confirms the
  default date order, then confirms a reorder call flips it and that the new order survives a
  fresh request (it's a real card field, not client-side state). One e2e test drags a freshly-due
  card above a years-overdue one and confirms the new order holds after a reload.
- `today_order` is one more piece of frontmatter on any card that's ever been part of a manual
  Today reorder. It's harmless if the card later leaves the due list (done, no due date, hidden) --
  the value just sits unused until the card becomes due again, at which point it resumes meaning
  exactly what it always meant.
