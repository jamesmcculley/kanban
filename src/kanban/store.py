"""Markdown-file storage: the files are the source of truth.

Layout under the data directory (open it as an Obsidian vault if you like):

    <board-slug>/board.md          frontmatter: title, columns, hidden (list names)
    <board-slug>/cards/<id>.md     frontmatter: id, title, column, position, due, repeat, done,
                                   completed, last_completed; body = notes
"""

from __future__ import annotations

import re
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import yaml

from .canvas import BOARD_KINDS, CanvasMixin
from .dates import next_occurrence
from .mdfile import read_md as _read
from .mdfile import slugify
from .mdfile import write_md as _write

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
    tags: list[str] = field(default_factory=list)


@dataclass
class Board:
    slug: str
    title: str
    columns: list[str] = field(default_factory=lambda: list(DEFAULT_COLUMNS))
    hidden: list[str] = field(default_factory=list)  # lists that exist but are tucked away
    area: str | None = None  # sidebar group ("Home", "Work"...)
    position: int = 0  # sidebar order
    kind: str = "kanban"  # or "canvas"
    parent: str | None = None  # set on boards nested inside a canvas


_TAG = re.compile(r"[a-z][a-z0-9_-]*")
_TITLE_TAG = re.compile(r"(?:^|(?<=\s))#([A-Za-z][A-Za-z0-9_-]*)(?![\w-])")


def parse_tags(value) -> list[str]:
    """'#Home, errand  home' -> ['home', 'errand']: lowercase, deduped, order kept."""
    parts = re.split(r"[,\s]+", value) if isinstance(value, str) else [str(v) for v in value or []]
    tags: list[str] = []
    for part in parts:
        tag = part.strip().lstrip("#").lower()
        if _TAG.fullmatch(tag) and tag not in tags:
            tags.append(tag)
    return tags


def split_tags(title: str) -> tuple[str, list[str]]:
    """'Buy paint #home #errand' -> ('Buy paint', ['home', 'errand'])."""
    tags = parse_tags(_TITLE_TAG.findall(title))
    return " ".join(_TITLE_TAG.sub("", title).split()), tags


def _iso(meta: dict, key: str) -> str | None:
    # hand-edited unquoted dates/times load as date/datetime; keep everything ISO strings
    value = meta.get(key)
    if not value:
        return None
    if isinstance(value, datetime):
        return value.isoformat(timespec="minutes")
    return str(value)


def _card_from(meta: dict, body: str) -> Card:
    return Card(
        id=meta["id"], title=meta["title"], column=meta["column"],
        position=meta.get("position", 0), due=_iso(meta, "due"), body=body,
        repeat=meta.get("repeat") or None, done=bool(meta.get("done")),
        completed=_iso(meta, "completed"), last_completed=_iso(meta, "last_completed"),
        tags=parse_tags(meta.get("tags")),
    )


class Store(CanvasMixin):
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
        boards = [self.get_board(p.parent.name) for p in sorted(self.root.glob("*/board.md"))]
        return sorted(boards, key=lambda b: (b.position, b.slug))

    def get_board(self, slug: str) -> Board:
        path = self._board_dir(slug) / "board.md"
        if not path.exists():
            raise KeyError(slug)
        meta, _ = _read(path)
        kind = meta.get("kind", "kanban")
        columns = meta.get("columns", list(DEFAULT_COLUMNS) if kind == "kanban" else [])
        hidden = [c for c in meta.get("hidden", []) if c in columns]
        return Board(slug, meta.get("title", slug), columns, hidden,
                     area=meta.get("area") or None, position=int(meta.get("position") or 0),
                     kind=kind, parent=meta.get("parent") or None)

    def _save_board(self, board: Board) -> None:
        meta = {"title": board.title}
        if board.kind != "kanban":
            meta["kind"] = board.kind
        else:
            meta["columns"] = board.columns
        if board.parent:
            meta["parent"] = board.parent
        if board.hidden:
            meta["hidden"] = board.hidden
        if board.area:
            meta["area"] = board.area
        if board.position:
            meta["position"] = board.position
        _write(self._board_dir(board.slug) / "board.md", meta)

    def create_board(self, title: str, columns: list[str] | None = None, kind: str = "kanban",
                     parent: str | None = None) -> Board:
        if kind not in BOARD_KINDS:
            raise ValueError(f"unknown board kind: {kind}")
        slug, n = slugify(title), 2
        while (self.root / slug).exists():
            slug, n = f"{slugify(title)}-{n}", n + 1
        last = max((b.position for b in self.list_boards()), default=0)
        board = Board(slug, title, (columns or list(DEFAULT_COLUMNS)) if kind == "kanban" else [],
                      position=last + 1, kind=kind, parent=parent)
        (self.root / slug / ("cards" if kind == "kanban" else "items")).mkdir(parents=True)
        self._save_board(board)
        return board

    # -- areas: named groups of boards in the sidebar ---------------------

    def _meta_path(self) -> Path:
        return self.root / ".trellis.yml"

    def _meta(self) -> dict:
        path = self._meta_path()
        return (yaml.safe_load(path.read_text(encoding="utf-8")) or {}) if path.exists() else {}

    def _save_areas(self, names: list[str]) -> None:
        meta = self._meta()
        meta["areas"] = names
        self._meta_path().write_text(yaml.safe_dump(meta, sort_keys=False, allow_unicode=True),
                                     encoding="utf-8")

    def areas(self) -> list[str]:
        """Ordered area names, including any a board mentions that the meta file lacks."""
        names = list(self._meta().get("areas") or [])
        for board in self.list_boards():
            if board.area and board.area not in names:
                names.append(board.area)
        return names

    def sidebar(self) -> dict:
        """Boards grouped for the sidebar: {'unassigned': [...], 'areas': [(name, [...])]}."""
        boards = [b for b in self.list_boards() if b.parent is None]  # nested boards live in a canvas
        names = self.areas()
        return {
            "unassigned": [b for b in boards if b.area not in names],
            "areas": [(n, [b for b in boards if b.area == n]) for n in names],
        }

    def add_area(self, name: str) -> None:
        names = self.areas()
        self._save_areas(names + [self._clean_name(name, names)])

    def rename_area(self, old: str, new: str) -> None:
        names = self.areas()
        if old not in names:
            raise ValueError(f"unknown area: {old}")
        new = self._clean_name(new, [n for n in names if n != old])
        self._save_areas([new if n == old else n for n in names])
        for board in self.list_boards():
            if board.area == old:
                board.area = new
                self._save_board(board)

    def delete_area(self, name: str) -> None:
        names = self.areas()
        if name not in names:
            raise ValueError(f"unknown area: {name}")
        if any(b.area == name for b in self.list_boards()):
            raise ValueError("area is not empty")
        self._save_areas([n for n in names if n != name])

    def apply_layout(self, areas: list[str], boards_by_area: dict[str, list[str]]) -> None:
        """Save a drag-and-drop result: area order, and which boards sit where.

        `boards_by_area` maps an area name (or "" for no area) to slugs in display order.
        """
        if sorted(areas) != sorted(self.areas()):
            raise ValueError("areas changed underneath you; reload")
        known = {b.slug: b for b in self.list_boards()}
        position = 0
        for area in ["", *areas]:
            for slug in boards_by_area.get(area, []):
                board = known[slug]  # KeyError for a stale/forged slug
                position += 1
                board.area, board.position = (area or None), position
                self._save_board(board)
        self._save_areas(areas)

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

    def reorder_columns(self, slug: str, names: list[str]) -> None:
        """Reorder the visible lists; hidden lists keep their slots."""
        board = self.get_board(slug)
        slots = [i for i, c in enumerate(board.columns) if c not in board.hidden]
        if sorted(names) != sorted(board.columns[i] for i in slots):
            raise ValueError("lists changed underneath you; reload")
        for slot, name in zip(slots, names, strict=True):
            board.columns[slot] = name
        self._save_board(board)

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
        if card.tags:
            meta["tags"] = card.tags
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
                    repeat: str | None = None, tags: list[str] | None = None) -> Card:
        card = self.get_card(slug, card_id)
        card.title, card.body, card.due, card.repeat = title, body, due or None, repeat or None
        card.tags = parse_tags(tags)
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

    def all_cards(self) -> list[tuple[Board, Card]]:
        return [(b, c) for b in self.list_boards() if b.kind == "kanban"
                for c in self.list_cards(b.slug)]

    def cards_with_tag(self, tag: str) -> list[tuple[Board, Card]]:
        """Open cards first, then completed ones."""
        hits = [(b, c) for b, c in self.all_cards() if tag in c.tags]
        return sorted(hits, key=lambda bc: bc[1].done)

    def tag_counts(self) -> list[tuple[str, int]]:
        """Tags on open cards outside hidden lists, alphabetical."""
        counts = Counter(t for b, c in self.all_cards()
                         if not c.done and c.column not in b.hidden for t in c.tags)
        return sorted(counts.items())

    def dated_cards(self) -> list[tuple[Board, Card]]:
        """Every open card with a due date, across all boards, soonest first.

        Cards in hidden lists are left out: hiding a list means "not now".
        """
        found = [(b, c) for b, c in self.all_cards()
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
                hay = f"{c.title}\n{c.body}\n{b.title}\n{' '.join('#' + t for t in c.tags)}".lower()
                if all(t in hay for t in terms):
                    hits.append((b, c))
        return hits

    def add_card(self, slug: str, title: str, column: str, due: str | None = None,
                 repeat: str | None = None, tags: list[str] | None = None,
                 top: bool = False) -> Card:
        board = self.get_board(slug)
        if column not in board.columns:
            raise ValueError(f"unknown column: {column}")
        siblings = self.cards_by_column(slug)[column]
        card = Card(uuid.uuid4().hex[:8], title, column, position=len(siblings), due=due,
                    repeat=repeat, tags=parse_tags(tags))
        self._save(slug, card)
        if top and siblings:
            self.move_card(slug, card.id, column, 0)
            card.position = 0
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
