"""The Logbook: a record of everything you have completed, with where it came from.

Kept as one append-only JSON-lines file so repeating cards build a real history (the card file
only remembers its latest completion). Board and list names are saved as they were at the time,
so an entry still makes sense after a rename or delete.
"""

from __future__ import annotations

import json

LOG_FILE = ".trellis-log.jsonl"


class LogbookMixin:
    def _log_path(self):
        return self.root / LOG_FILE

    def _read_log(self) -> list[dict]:
        path = self._log_path()
        if not path.exists():
            return []
        events = []
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue  # a torn or hand-edited line must not take the page down
            if isinstance(event, dict) and event.get("card") and event.get("at"):
                events.append(event)
        return events

    @staticmethod
    def _event(board, card, at: str) -> dict:
        event = {"at": at, "card": card.id, "title": card.title, "board": board.slug,
                 "board_title": board.title, "list": card.column}
        if card.repeat:
            event["repeat"] = True
        if card.tags:
            event["tags"] = list(card.tags)
        if card.priority:
            event["priority"] = card.priority
        return event

    def log_completion(self, board, card, at: str) -> None:
        with self._log_path().open("a", encoding="utf-8") as f:
            f.write(json.dumps(self._event(board, card, at), ensure_ascii=False) + "\n")

    def remove_completion(self, card_id: str, at: str) -> None:
        events = self._read_log()
        for i in range(len(events) - 1, -1, -1):
            if events[i]["card"] == card_id and events[i]["at"] == at:
                del events[i]
                break
        else:
            return
        self._log_path().write_text(
            "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in events), encoding="utf-8")

    def edit_completion_at(self, card_id: str, old_at: str, new_at: str) -> None:
        """Move a logged completion to a different timestamp (see Store.edit_completion)."""
        events = self._read_log()
        for i in range(len(events) - 1, -1, -1):
            if events[i]["card"] == card_id and events[i]["at"] == old_at:
                events[i]["at"] = new_at
                break
        else:
            return
        self._log_path().write_text(
            "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in events), encoding="utf-8")

    def logbook(self, limit: int | None = 500, date_from: str | None = None,
               date_to: str | None = None) -> list[dict]:
        """Newest first. Cards completed before the log existed are folded in from their files.
        `date_from`/`date_to` (inclusive ISO dates) filter by completion day, applied before the
        limit so a date-range query is never truncated by an unrelated recency cap. `limit=None`
        returns everything in range, unbounded -- Metrics and the CSV export need real totals, not
        just the newest 500 the Logbook page itself is happy to show."""
        events = self._read_log()
        seen = {(e["card"], e["at"]) for e in events}
        for board, card in self.all_cards():
            if card.done and card.completed and (card.id, card.completed) not in seen:
                events.append(self._event(board, card, card.completed))
        if date_from:
            events = [e for e in events if e["at"][:10] >= date_from]
        if date_to:
            events = [e for e in events if e["at"][:10] <= date_to]
        events.sort(key=lambda e: e["at"], reverse=True)
        return events[:limit] if limit else events
