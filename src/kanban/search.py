"""Pure narrowing for Advanced Search and the cards CSV export -- given (board, card) pairs (from
Store.search, Store.all_cards, Store.scheduled_cards...), filter by title text, tags, priority,
board, list and done/open status. No I/O, no Flask; see AGENTS.md's boundary list. Nothing set = no
narrowing, and multiple fields set narrow with AND between fields, OR within a field's own choices
(e.g. two tags checked means "either tag", not "both").
"""

from __future__ import annotations


def refine(results: list, q: str = "", tags: list[str] | None = None, priorities: list[str] | None = None,
          boards: list[str] | None = None, lists: list[str] | None = None,
          statuses: list[str] | None = None) -> list:
    q = (q or "").strip().lower()
    tag_set, priority_set = set(tags or []), set(priorities or [])
    board_set, list_set = set(boards or []), set(lists or [])
    statuses = set(statuses or [])
    want_open, want_done = "open" in statuses, "done" in statuses
    status_filters = want_open != want_done  # both or neither checked -> no status narrowing

    def matches(board, card) -> bool:
        if q and q not in card.title.lower():
            return False
        if tag_set and not tag_set & set(card.tags):
            return False
        if priority_set and (card.priority or "none") not in priority_set:
            return False
        if board_set and board.slug not in board_set:
            return False
        if list_set and card.column not in list_set:
            return False
        return not (status_filters and card.done != want_done)

    return [(b, c) for b, c in results if matches(b, c)]
