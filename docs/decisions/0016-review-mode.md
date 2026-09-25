# 0016. Review mode: a rolling look-back/look-forward report, starring, and per-card exclusion

- Status: accepted (amended 2026-09-25 -- see below)
- Date: 2026-09-25
- Departs from standard: none

> **Amendment, same day:** the per-card exclusion mechanism this ADR describes below ("today" vs.
> "always," managed from Settings) was replaced by a general `Card.hidden` flag usable from any
> page, revived from the card's own board -- see ADR 0018. `excluded_ids()`, the
> `review_exclusions` storage key, and the `/review/exclude`/`/review/include` routes no longer
> exist. Everything else in this ADR (starring, the free-text day counts, starred-only ignoring
> the date range) is unchanged.

## Context

The owner wanted a quick answer to "what did I do last week / what am I doing this week" for a
review, plus a way to keep the report from being cluttered by things not worth mentioning, and a
way to make sure a few things are never missed. The same mechanism needed to double as an annual
review: show only starred items, ever, ignoring any date window.

## Decision

- **Look-back/look-forward are GET query params (`back`/`forward`), not persisted.** Consistent
  with Scheduled's existing date-range filter: bookmarkable via URL, not a standing device
  preference. Default to 7 when absent.
- **Both are free-text inputs, not a dropdown or `<input type=number>`**, clamped server-side by
  the pure `review.clamp_days()`. 0 is a real, meaningful value ("show nothing that direction"),
  so only a missing or unparseable value falls back to the 7-day default — a dropdown can't offer
  0 alongside "whatever number I want" (999, for a specific request in this round) without either
  an awkward "custom" option or silently rejecting free values. A ceiling of `MAX_DAYS` (3650, ~10
  years) guards against a typo like an extra zero, not a real limit.
- **"Only show starred items" is a checkbox (`starred=1`) that ignores both day counts entirely**,
  showing every starred card ever, split into completed/open. Built specifically for the annual-
  review use case named in the request — a "last 365 days" window would eventually need
  adjusting again next year; "every starred item, always" doesn't.
- **Exclusion is per-card with two scopes, stored server-side** (`.trellis.yml`'s
  `review_exclusions`, shared across the LAN instance like saved searches): "today"
  (`until=<today's ISO date>`, expires automatically — `review.excluded_ids()` only honors it on
  that exact calendar day) and "always" (`until=None`, permanent). Server-side and shared, not
  per-device `localStorage`, because "don't mention the recurring vacuum-the-house chore" is a
  fact about the report, not about one browser.
- **Starring is a persistent per-card boolean (`Card.starred`), not review-scoped.** It's exposed
  everywhere the card-edit dialog opens (`_edit.html`'s `.star-btn`, shared via one `ui.js` click
  handler keyed off the class, not the template) as well as from a Review row directly — matching
  the "duplicate from anywhere" precedent (ADR 0014). A review-only flag would have meant
  re-deciding what's worth highlighting every single week; a persistent one lets the owner mark
  something important once and have it surface in every future report until unstarred.
- **Two independent show/hide mechanisms, matching two different existing patterns, not one:**
  - The on-page filter popover (back/forward/starred-only, `.review-filter-wrap` — its own class
    trio per AGENTS.md trap 9) also carries "Completed"/"Upcoming" section-visibility checkboxes,
    stored in `localStorage` (`review-hide`) via a `ReviewSections` module mirroring `TodaySections`.
    In-page and per-device, like Today's equivalent three-section toggle, because it's "what do I
    want to see in this report right now," not a standing preference set once in Settings.
  - Settings gained a "Review" checkbox in the existing "Show in the sidebar" and "Page titles"
    fieldsets (same as every other page), plus a new "Excluded from Review" section listing every
    resolved exclusion (title, board, "today only" vs "always") with an "Include again" button —
    the one piece of review state that's a genuine standing, shared setting (unlike section
    visibility), since forgetting *why* something was permanently excluded is exactly the failure
    mode a management list exists to prevent.
- **A dedicated `_review_row.html` macro, not an extension of `_card_row.html`/`_logbook_row.html`.**
  Review's row needs star + exclude-menu + either a completed-stamp or a due date depending on
  section — concerns specific to this feature. Bolting them onto the shared row macros risked
  destabilizing already-tested components used everywhere else for one feature's needs; a
  review-only macro keeps the blast radius contained.
- **`_resolve_logged_cards()` (built for Today's CSV export) is reused** to turn Logbook events
  into live `(board, card)` pairs for the Completed section, giving Completed and Upcoming the same
  `(board, card)` tuple shape and letting both flow through one row macro.
- **The `.eye-menu-wrap`/`data-eye-toggle` widget is reused as-is for the per-row exclude menu**,
  since it's already a generic "reveal a small action menu" mechanism (unlike the filter popovers,
  which are deliberately *not* shared per trap 9) — its open/close JS has no coupling to what's
  inside it.

## Consequences

- Unit tests cover `review.py`'s pure functions (`excluded_ids`, `clamp_days` — zero, negative,
  decimal, huge, and whitespace-padded input) and the new `Store` methods (`set_starred`,
  `exclude_from_review`/`include_in_review` round-trips, the missing-card `KeyError` path).
  Route tests cover `/review`'s default window, `back=0`/`forward=0`, `starred=1`, and both
  exclusion scopes including "today"'s same-day expiry. Two e2e tests cover starring from the edit
  dialog and seeing it reflected on a Review row, the starred-only filter actually narrowing
  results, excluding a card and watching the row disappear live plus survive a reload, the
  Settings "Include again" round-trip, and the section-visibility toggle persisting.
- "Upcoming" only ever shows cards with a start or due date (`Store.scheduled_cards`) — a card with
  neither never appears there regardless of the look-forward window, same as Scheduled itself.
  Not a new limitation, just inherited from the existing agenda query it reuses.
