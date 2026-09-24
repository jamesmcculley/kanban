"""Pure narrowing for Advanced Search -- given (board, card) pairs (from Store.search or
Store.all_cards), filter by tags, priority, board and done/open status. No I/O, no Flask; see
AGENTS.md's boundary list. Combines with the base text search the same way every other filter in
this app does: nothing set = no narrowing, and multiple fields set narrow with AND between fields,
OR within a field's own choices (e.g. two tags checked means "either tag", not "both").
"""

from __future__ import annotations


def refine(results: list, tags: list[str] | None = None, priorities: list[str] | None = None,
          boards: list[str] | None = None, statuses: list[str] | None = None) -> list:
    tag_set, priority_set, board_set = set(tags or []), set(priorities or []), set(boards or [])
    statuses = set(statuses or [])
    want_open, want_done = "open" in statuses, "done" in statuses
    status_filters = want_open != want_done  # both or neither checked -> no status narrowing

    def matches(board, card) -> bool:
        if tag_set and not tag_set & set(card.tags):
            return False
        if priority_set and (card.priority or "none") not in priority_set:
            return False
        if board_set and board.slug not in board_set:
            return False
        return not (status_filters and card.done != want_done)

    return [(b, c) for b, c in results if matches(b, c)]
