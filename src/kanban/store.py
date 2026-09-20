"""Markdown-file storage: the files are the source of truth.

Layout under the data directory (open it as an Obsidian vault if you like):

    <board-slug>/board.md          frontmatter: title, columns, hidden (list names)
    <board-slug>/cards/<id>.md     frontmatter: id, title, column, position, due, repeat, done,
                                   completed, last_completed; body = notes
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import yaml

from .dates import next_occurrence

DEFAULT_COLUMNS = ["Todo", "Doing", "Done"]


@dataclass
class Card:
    id: str
    title: str
    column: str
    position: int = 0
    due: str | None = None
    body: str = ""
    repeat: str | None = None
    done: bool = False
    completed: str | None = None  # ISO timestamp of when it was checked off
    last_completed: str | None = None  # repeating cards: when it last rolled forward


@dataclass
class Board:
    slug: str
    title: str
    columns: list[str] = field(default_factory=lambda: list(DEFAULT_COLUMNS))
    hidden: list[str] = field(default_factory=list)  # lists that exist but are tucked away


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "board"


def _read(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    if text.startswith("---\n"):
        _, front, body = text.split("---\n", 2)
        return yaml.safe_load(front) or {}, body.lstrip("\n")
    return {}, text


def _iso(meta: dict, key: str) -> str | None:
    # hand-edited unquoted dates/times load as date/datetime; keep everything ISO strings
    value = meta.get(key)
    if not value:
        return None
    if isinstance(value, datetime):
        return value.isoformat(timespec="minutes")
    return str(value)


def _write(path: Path, meta: dict, body: str = "") -> None:
    front = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True)
    path.write_text(f"---\n{front}---\n\n{body}", encoding="utf-8")


def _card_from(meta: dict, body: str) -> Card:
    return Card(
        id=meta["id"], title=meta["title"], column=meta["column"],
        position=meta.get("position", 0), due=_iso(meta, "due"), body=body,
        repeat=meta.get("repeat") or None, done=bool(meta.get("done")),
        completed=_iso(meta, "completed"), last_completed=_iso(meta, "last_completed"),
    )


class Store:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    # -- boards ---------------------------------------------------------

    def _board_dir(self, slug: str) -> Path:
        # slugs come from URLs; refuse anything that could escape the data dir
        if slug != slugify(slug):
            raise KeyError(slug)
        return self.root / slug

    def list_boards(self) -> list[Board]:
        return [
            self.get_board(p.parent.name) for p in sorted(self.root.glob("*/board.md"))
        ]

    def get_board(self, slug: str) -> Board:
        path = self._board_dir(slug) / "board.md"
        if not path.exists():
            raise KeyError(slug)
        meta, _ = _read(path)
        columns = meta.get("columns", list(DEFAULT_COLUMNS))
        hidden = [c for c in meta.get("hidden", []) if c in columns]
        return Board(slug, meta.get("title", slug), columns, hidden)

    def _save_board(self, board: Board) -> None:
        meta = {"title": board.title, "columns": board.columns}
        if board.hidden:
            meta["hidden"] = board.hidden
        _write(self._board_dir(board.slug) / "board.md", meta)

    def create_board(self, title: str, columns: list[str] | None = None) -> Board:
        slug, n = slugify(title), 2
        while (self.root / slug).exists():
            slug, n = f"{slugify(title)}-{n}", n + 1
        board = Board(slug, title, columns or list(DEFAULT_COLUMNS))
        (self.root / slug / "cards").mkdir(parents=True)
        self._save_board(board)
        return board

    # -- lists (columns) ------------------------------------------------

    @staticmethod
    def _clean_name(name: str, others: list[str]) -> str:
        name = " ".join(name.split())
        if not name:
            raise ValueError("list name is empty")
        if name.lower() in (o.lower() for o in others):
            raise ValueError(f"a list named {name!r} already exists")
        return name

    def add_column(self, slug: str, name: str) -> None:
        board = self.get_board(slug)
        board.columns.append(self._clean_name(name, board.columns))
        self._save_board(board)

    def rename_column(self, slug: str, old: str, new: str) -> None:
        board = self.get_board(slug)
        if old not in board.columns:
            raise ValueError(f"unknown list: {old}")
        new = self._clean_name(new, [c for c in board.columns if c != old])
        if new == old:
            return
        board.columns = [new if c == old else c for c in board.columns]
        board.hidden = [new if c == old else c for c in board.hidden]
        self._save_board(board)
        for card in self.list_cards(slug):
            if card.column == old:
                card.column = new
                self._save(slug, card)

    def set_column_hidden(self, slug: str, name: str, hidden: bool) -> None:
        board = self.get_board(slug)
        if name not in board.columns:
            raise ValueError(f"unknown list: {name}")
        board.hidden = [c for c in board.hidden if c != name] + ([name] if hidden else [])
        self._save_board(board)

    def delete_column(self, slug: str, name: str) -> None:
        board = self.get_board(slug)
        if name not in board.columns:
            raise ValueError(f"unknown list: {name}")
        if any(c.column == name for c in self.list_cards(slug)):
            raise ValueError("list is not empty")
        board.columns.remove(name)
        board.hidden = [c for c in board.hidden if c != name]
        self._save_board(board)

    # -- cards ----------------------------------------------------------

    def _card_path(self, slug: str, card_id: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{8}", card_id):
            raise KeyError(card_id)
        return self._board_dir(slug) / "cards" / f"{card_id}.md"

    def _save(self, slug: str, card: Card) -> None:
        meta = {"id": card.id, "title": card.title, "column": card.column,
                "position": card.position}
        if card.due:
            meta["due"] = card.due
        if card.repeat:
            meta["repeat"] = card.repeat
        if card.done:
            meta["done"] = True
            if card.completed:
                meta["completed"] = card.completed
        if card.last_completed:
            meta["last_completed"] = card.last_completed
        _write(self._card_path(slug, card.id), meta, card.body)

    def list_cards(self, slug: str) -> list[Card]:
        self.get_board(slug)
        cards = [_card_from(*_read(p)) for p in (self._board_dir(slug) / "cards").glob("*.md")]
        return sorted(cards, key=lambda c: c.position)

    def cards_by_column(self, slug: str) -> dict[str, list[Card]]:
        board = self.get_board(slug)
        grouped: dict[str, list[Card]] = {col: [] for col in board.columns}
        for card in self.list_cards(slug):
            grouped.setdefault(card.column, []).append(card)
        return grouped

    def get_card(self, slug: str, card_id: str) -> Card:
        path = self._card_path(slug, card_id)
        if not path.exists():
            raise KeyError(card_id)
        return _card_from(*_read(path))

    def update_card(self, slug: str, card_id: str, title: str, body: str, due: str | None,
                    repeat: str | None = None) -> Card:
        card = self.get_card(slug, card_id)
        card.title, card.body, card.due, card.repeat = title, body, due or None, repeat or None
        self._save(slug, card)
        return card

    def complete_card(self, slug: str, card_id: str, now: datetime | None = None) -> Card:
        """Stamp the completion time. Repeating cards then advance to their next due date;
        others toggle done/not done."""
        now = now or datetime.now()  # local time: the app is meant to run in the owner's zone
        stamp = now.isoformat(timespec="minutes")
        card = self.get_card(slug, card_id)
        if card.repeat:
            due = date.fromisoformat(card.due) if card.due else None
            card.due = next_occurrence(card.repeat, due, now.date()).isoformat()
            card.last_completed = stamp
        elif card.done:
            card.done, card.completed = False, None
        else:
            card.done, card.completed = True, stamp
        self._save(slug, card)
        return card

    def dated_cards(self) -> list[tuple[Board, Card]]:
        """Every open card with a due date, across all boards, soonest first.

        Cards in hidden lists are left out: hiding a list means "not now".
        """
        found = [(b, c) for b in self.list_boards() for c in self.list_cards(b.slug)
                 if c.due and not c.done and c.column not in b.hidden]
        return sorted(found, key=lambda bc: (str(bc[1].due), bc[0].slug, bc[1].position))

    def search(self, query: str) -> list[tuple[Board, Card]]:
        """Cards whose title, notes or board name contain every word of the query."""
        terms = query.lower().split()
        if not terms:
            return []
        hits = []
        for b in self.list_boards():
            for c in self.list_cards(b.slug):
                hay = f"{c.title}\n{c.body}\n{b.title}".lower()
                if all(t in hay for t in terms):
                    hits.append((b, c))
        return hits

    def add_card(self, slug: str, title: str, column: str, due: str | None = None,
                 repeat: str | None = None) -> Card:
        board = self.get_board(slug)
        if column not in board.columns:
            raise ValueError(f"unknown column: {column}")
        siblings = self.cards_by_column(slug)[column]
        card = Card(uuid.uuid4().hex[:8], title, column, position=len(siblings), due=due,
                    repeat=repeat)
        self._save(slug, card)
        return card

    def move_card(self, slug: str, card_id: str, column: str, index: int) -> None:
        board = self.get_board(slug)
        if column not in board.columns:
            raise ValueError(f"unknown column: {column}")
        grouped = self.cards_by_column(slug)
        card = next((c for cards in grouped.values() for c in cards if c.id == card_id), None)
        if card is None:
            raise KeyError(card_id)
        for cards in grouped.values():
            if card in cards:
                cards.remove(card)
        card.column = column
        target = grouped[column]
        target.insert(max(0, min(index, len(target))), card)
        for cards in grouped.values():
            for pos, c in enumerate(cards):
                if c is card or c.position != pos:
                    c.position = pos
                    self._save(slug, c)

    def delete_card(self, slug: str, card_id: str) -> None:
        self._card_path(slug, card_id).unlink(missing_ok=True)
