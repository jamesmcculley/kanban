# 0017. Collapsible sections on Today, Scheduled, Logbook and Review

- Status: accepted
- Date: 2026-09-25
- Departs from standard: none

## Context

Today and Review already had a per-page toggle to hide a whole section entirely (a standing
preference, set once from that page's own filter popover). The owner asked for something
different and complementary: a fold/unfold control on every section heading across all four
list-style pages (Today, Scheduled, Logbook, Review), so a section can be collapsed out of the way
for now without turning it off as a standing preference.

## Decision

- **Persisted, not session-only.** Unlike bulk-select's deliberately non-persisted selection (ADR
  0015), a section's collapsed state is remembered per device (`localStorage`) across reloads --
  folding "Created today" away once is a real, lasting preference for most people, same as every
  other view toggle already in this app (sidebar sections, sort order, Today/Review's own
  section-visibility). Confirmed with the owner rather than assumed, since the two behaviors
  (reset vs. remember) are both plausible and genuinely different in effect.
- **One shared mechanism for both fixed and dynamic section keys.** Today (`due`/`completed`/
  `created`) and Review (`completed`/`upcoming`) have a small fixed set of section ids, which could
  have used the `data-X-hide` attribute + static CSS pattern already established for sidebar/
  Today/Review section *visibility*. But Scheduled and Logbook group by date -- an unbounded key
  space -- which can't be pre-written as CSS rules. Rather than build two different mechanisms,
  every page uses one: `data-collapse-id="<page>:<section>"` on the section wrapper (a fixed word
  or an ISO date), one `localStorage` array (`collapsed-sections`) of currently-collapsed ids, and
  a single generated `<style>` tag rewritten on every change -- the same shape `HiddenBoards`
  already uses for arbitrary board slugs, just applied to section ids instead.
- **The generated stylesheet is built both pre-paint (`_theme_boot.html`) and by
  `CollapsedSections.render()` (`sidebar.js`)**, so a collapsed section never flashes open on load
  and stays in sync the moment it's toggled -- the pre-paint copy can't set `aria-expanded` (the
  elements don't exist yet in `<head>`), so a `DOMContentLoaded` pass catches up the a11y state
  separately once they do.
- **The chevron button leads the heading text** (not trailing, not `margin-left: auto`), the
  common disclosure-control convention, and needs no page-specific CSS: `.agenda h2` already
  applies to all four pages (Today, Scheduled, Logbook and Review's `<main>` all carry the
  `.agenda` class), so one rule covers every page at once.
- **A row's or card's actual DOM stays put** -- collapsing only toggles a `.collapsible-body`
  wrapper's `display`, not a client-side re-render -- so nothing about card counts, htmx targets or
  Sortable's drag setup needed to change.

## Consequences

- No new server routes or Python code: this is entirely a template/CSS/JS feature layered onto
  existing section markup (`<section data-X-section>` on Today/Review; a new `<section>` wrapper
  added around Scheduled's and Logbook's previously-flat per-date/per-day groups).
- Two new e2e tests: one exercising a fixed-key section (Today's "Due & overdue", including reload
  persistence and re-expanding), one exercising a dynamic per-day group (Logbook), since the two
  code paths through the id-matching regex are worth covering independently even though they share
  one implementation.
