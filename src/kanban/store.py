"""Markdown-file storage: the files are the source of truth.

Layout under the data directory (open it as an Obsidian vault if you like):

    <board-slug>/board.md          frontmatter: title, columns
    <board-slug>/cards/<id>.md     frontmatter: id, title, column, position, due; body = notes
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_COLUMNS = ["Todo", "Doing", "Done"]


@dataclass
class Card:
    id: str
    title: str
    column: str
    position: int = 0
    due: str | None = None
    body: str = ""


@dataclass
class Board:
    slug: str
    title: str
    columns: list[str] = field(default_factory=lambda: list(DEFAULT_COLUMNS))


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "board"


def _read(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    if text.startswith("---\n"):
        _, front, body = text.split("---\n", 2)
        return yaml.safe_load(front) or {}, body.lstrip("\n")
    return {}, text


def _due(meta: dict) -> str | None:
    # hand-edited unquoted dates load as datetime.date; keep everything ISO strings
    return str(meta["due"]) if meta.get("due") else None


def _write(path: Path, meta: dict, body: str = "") -> None:
    front = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True)
    path.write_text(f"---\n{front}---\n\n{body}", encoding="utf-8")


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
        return Board(slug, meta.get("title", slug), meta.get("columns", list(DEFAULT_COLUMNS)))

    def create_board(self, title: str, columns: list[str] | None = None) -> Board:
        slug, n = slugify(title), 2
        while (self.root / slug).exists():
            slug, n = f"{slugify(title)}-{n}", n + 1
        board = Board(slug, title, columns or list(DEFAULT_COLUMNS))
        (self.root / slug / "cards").mkdir(parents=True)
        _write(self.root / slug / "board.md", {"title": board.title, "columns": board.columns})
        return board

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
        _write(self._card_path(slug, card.id), meta, card.body)

    def list_cards(self, slug: str) -> list[Card]:
        self.get_board(slug)
        cards = []
        for path in (self._board_dir(slug) / "cards").glob("*.md"):
            meta, body = _read(path)
            cards.append(Card(
                id=meta["id"], title=meta["title"], column=meta["column"],
                position=meta.get("position", 0), due=_due(meta), body=body,
            ))
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
        meta, body = _read(path)
        return Card(meta["id"], meta["title"], meta["column"], meta.get("position", 0),
                    _due(meta), body)

    def update_card(self, slug: str, card_id: str, title: str, body: str, due: str | None) -> Card:
        card = self.get_card(slug, card_id)
        card.title, card.body, card.due = title, body, due or None
        self._save(slug, card)
        return card

    def dated_cards(self) -> list[tuple[Board, Card]]:
        """Every card with a due date, across all boards, soonest first."""
        found = [(b, c) for b in self.list_boards() for c in self.list_cards(b.slug) if c.due]
        return sorted(found, key=lambda bc: (str(bc[1].due), bc[0].slug, bc[1].position))

    def add_card(self, slug: str, title: str, column: str, due: str | None = None) -> Card:
        board = self.get_board(slug)
        if column not in board.columns:
            raise ValueError(f"unknown column: {column}")
        siblings = self.cards_by_column(slug)[column]
        card = Card(uuid.uuid4().hex[:8], title, column, position=len(siblings), due=due)
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
