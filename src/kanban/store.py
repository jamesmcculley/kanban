"""Markdown-file storage: the files are the source of truth.

Layout under the data directory (open it as an Obsidian vault if you like):

    <board-slug>/board.md          frontmatter: title, columns, hidden (list names)
    <board-slug>/cards/<id>.md     frontmatter: id, title, column, position, start, due, repeat,
                                   done, completed, last_completed; body = notes
"""

from __future__ import annotations

import re
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import yaml

from . import labels as L
from .dates import next_occurrence
from .logbook import LogbookMixin
from .mdfile import extra_fields, slugify
from .mdfile import read_md as _read
from .mdfile import write_md as _write
from .preferences import PreferencesMixin
from .settings import DEFAULT_COLUMNS
from .tags import parse_tags
from .trash import TrashMixin

BOARD_KINDS = ("kanban", "tasks")
PRIORITIES = ("low", "medium", "high")
TASKS_COLUMN = "Tasks"  # the one hidden column every tasks-kind board uses internally


@dataclass
class Card:
    id: str
    title: str
    column: str
    position: int = 0
    start: str | None = None  # when you plan to start it
    due: str | None = None
    body: str = ""
    repeat: str | None = None
    done: bool = False
    completed: str | None = None  # ISO timestamp of when it was checked off
    last_completed: str | None = None  # repeating cards: when it last rolled forward
    tags: list[str] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)  # board-scoped label ids (Board.labels)
    priority: str | None = None  # one of PRIORITIES, or None for no priority
    archived: bool = False  # cleared from its list; still in the Logbook and search
    effects: list[str] = field(default_factory=list, compare=False, repr=False)  # what rules just did (not stored)
    extra: dict = field(default_factory=dict, compare=False, repr=False)  # unknown frontmatter, kept as-is


@dataclass
class Board:
    slug: str
    title: str
    columns: list[str] = field(default_factory=lambda: list(DEFAULT_COLUMNS))
    hidden: list[str] = field(default_factory=list)  # lists that exist but are tucked away
    area: str | None = None  # sidebar group ("Home", "Work"...)
    position: int = 0  # sidebar order
    kind: str = "kanban"
    parent: str | None = None  # unused; kept so a file from when boards could nest still reads back
    settings: dict = field(default_factory=dict)  # this board's overrides of the global settings
    rules: list = field(default_factory=list)  # this board's automation rules
    labels: list = field(default_factory=list)  # this board's label definitions: [{id, name, color}]
    archived: bool = False  # tucked away: out of the sidebar, search, Scheduled; still fully intact
    extra: dict = field(default_factory=dict, compare=False, repr=False)  # unknown frontmatter, kept as-is


def _iso(meta: dict, key: str) -> str | None:
    # hand-edited unquoted dates/times load as date/datetime; keep everything ISO strings
    value = meta.get(key)
    if not value:
        return None
    if isinstance(value, datetime):
        return value.isoformat(timespec="minutes")
    return str(value)


_CARD_KEYS = {"id", "title", "column", "position", "start", "due", "repeat", "tags", "labels",
              "priority", "done", "completed", "last_completed", "archived"}
_BOARD_KEYS = {"title", "kind", "columns", "parent", "hidden", "area", "position", "settings", "rules",
               "labels", "archived"}


def _card_from(meta: dict, body: str) -> Card:
    return Card(extra=extra_fields(meta, _CARD_KEYS),
        id=meta["id"], title=meta["title"], column=meta["column"],
        position=meta.get("position", 0), start=_iso(meta, "start"), due=_iso(meta, "due"), body=body,
        repeat=meta.get("repeat") or None, done=bool(meta.get("done")),
        completed=_iso(meta, "completed"), last_completed=_iso(meta, "last_completed"),
        tags=parse_tags(meta.get("tags")), labels=list(meta.get("labels") or []),
        priority=meta.get("priority") if meta.get("priority") in PRIORITIES else None,
        archived=bool(meta.get("archived")),
    )


def effective_date(card: Card) -> str | None:
    """The date that decides where a card sits in Scheduled: due if it has one, else start."""
    return card.due or card.start


class Store(TrashMixin, LogbookMixin, PreferencesMixin):
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

    def list_archived_boards(self) -> list[Board]:
        return [b for b in self.list_boards() if b.archived]

    def archive_board(self, slug: str) -> None:
        """Tuck a board away: out of the sidebar, search, Scheduled and move-to/capture pickers,
        but still fully there -- its area, position, rules and cards are all untouched, and
        unarchive_board puts it right back where it was."""
        board = self.get_board(slug)
        board.archived = True
        self._save_board(board)

    def unarchive_board(self, slug: str) -> None:
        board = self.get_board(slug)
        board.archived = False
        self._save_board(board)

    def get_board(self, slug: str) -> Board:
        path = self._board_dir(slug) / "board.md"
        if not path.exists():
            raise KeyError(slug)
        meta, _ = _read(path)
        kind = meta.get("kind", "kanban")
        default_cols = list(DEFAULT_COLUMNS) if kind == "kanban" else [TASKS_COLUMN] if kind == "tasks" else []
        columns = meta.get("columns", default_cols)
        hidden = [c for c in meta.get("hidden", []) if c in columns]
        return Board(slug, meta.get("title", slug), columns, hidden,
                     area=meta.get("area") or None, position=int(meta.get("position") or 0),
                     kind=kind, parent=meta.get("parent") or None,
                     settings=meta.get("settings") or {}, rules=meta.get("rules") or [],
                     labels=meta.get("labels") or [], archived=bool(meta.get("archived")),
                     extra=extra_fields(meta, _BOARD_KEYS))

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
        if board.settings:
            meta["settings"] = board.settings
        if board.rules:
            meta["rules"] = board.rules
        if board.labels:
            meta["labels"] = board.labels
        if board.archived:
            meta["archived"] = True
        _write(self._board_dir(board.slug) / "board.md", {**board.extra, **meta})

    def create_board(self, title: str, columns: list[str] | None = None, kind: str = "kanban") -> Board:
        if kind not in BOARD_KINDS:
            raise ValueError(f"unknown board kind: {kind}")
        slug, n = slugify(title), 2
        while (self.root / slug).exists():
            slug, n = f"{slugify(title)}-{n}", n + 1
        last = max((b.position for b in self.list_boards()), default=0)
        if kind == "tasks":
            chosen = [TASKS_COLUMN]
        else:
            chosen = columns or self.global_settings().get("default_columns") or list(DEFAULT_COLUMNS)
        board = Board(slug, title, chosen, position=last + 1, kind=kind)
        (self.root / slug / "cards").mkdir(parents=True)
        self._save_board(board)
        return board

    # -- labels: a board's own small, named, coloured set ------------------

    def list_labels(self, slug: str) -> list[dict]:
        return self.get_board(slug).labels

    def add_label(self, slug: str, name: str, color: str) -> dict:
        board = self.get_board(slug)
        if len(board.labels) >= L.MAX_LABELS:
            raise ValueError(f"at most {L.MAX_LABELS} labels")
        label = L.clean_label({"name": name, "color": color}, board.labels)
        board.labels = [*board.labels, label]
        self._save_board(board)
        return label

    def update_label(self, slug: str, label_id: str, name: str, color: str) -> dict:
        board = self.get_board(slug)
        others = [x for x in board.labels if x["id"] != label_id]
        if not any(x["id"] == label_id for x in board.labels):
            raise KeyError(label_id)
        label = L.clean_label({"name": name, "color": color}, others, label_id)
        board.labels = [label if x["id"] == label_id else x for x in board.labels]
        self._save_board(board)
        return label

    def delete_label(self, slug: str, label_id: str) -> None:
        board = self.get_board(slug)
        if not any(x["id"] == label_id for x in board.labels):
            raise KeyError(label_id)
        board.labels = [x for x in board.labels if x["id"] != label_id]
        self._save_board(board)
        for card in self.list_cards(slug):          # a deleted label can't linger on a card
            if label_id in card.labels:
                card.labels = [x for x in card.labels if x != label_id]
                self._save(slug, card)

    # -- areas: named groups of boards in the sidebar ---------------------

    def _meta_path(self) -> Path:
        return self.root / ".trellis.yml"

    def _meta(self) -> dict:
        path = self._meta_path()
        return (yaml.safe_load(path.read_text(encoding="utf-8")) or {}) if path.exists() else {}

    def _save_areas(self, names: list[str]) -> None:
        meta = self._meta()
        meta["areas"] = names
        self._write_meta(meta)

    def areas(self) -> list[str]:
        """Ordered area names, including any a board mentions that the meta file lacks."""
        names = list(self._meta().get("areas") or [])
        for board in self.list_boards():
            if board.area and board.area not in names:
                names.append(board.area)
        return names

    def sidebar(self) -> dict:
        """Boards grouped for the sidebar: {'unassigned': [...], 'areas': [(name, [...])]}.
        Archived boards are left out -- see list_archived_boards."""
        boards = [b for b in self.list_boards() if b.parent is None and not b.archived]
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

    def delete_area(self, name: str) -> tuple[int, list[str]]:
        """Delete an area; its boards become unassigned, not deleted.
        Returns (its position, the slugs it held) so the deletion can be undone."""
        names = self.areas()
        if name not in names:
            raise ValueError(f"unknown area: {name}")
        held = [b.slug for b in self.list_boards() if b.area == name]
        for slug in held:
            board = self.get_board(slug)
            board.area = None
            self._save_board(board)
        self._save_areas([n for n in names if n != name])
        return names.index(name), held

    def restore_area(self, name: str, index: int, slugs: list[str]) -> None:
        names = [n for n in self.areas() if n != name]
        names.insert(max(0, min(index, len(names))), self._clean_name(name, names))
        self._save_areas(names)
        for slug in slugs:
            try:
                board = self.get_board(slug)
            except KeyError:
                continue
            board.area = name
            self._save_board(board)

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
        if any(c.column == name and not c.archived for c in self.list_cards(slug)):
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
        if card.start:
            meta["start"] = card.start
        if card.due:
            meta["due"] = card.due
        if card.repeat:
            meta["repeat"] = card.repeat
        if card.tags:
            meta["tags"] = card.tags
        if card.labels:
            meta["labels"] = card.labels
        if card.priority:
            meta["priority"] = card.priority
        if card.done:
            meta["done"] = True
            if card.completed:
                meta["completed"] = card.completed
        if card.last_completed:
            meta["last_completed"] = card.last_completed
        if card.archived:
            meta["archived"] = True
        _write(self._card_path(slug, card.id), {**card.extra, **meta}, card.body)

    def _load_card(self, path: Path) -> Card:
        return _card_from(*_read(path))

    def _reindex(self, slug: str) -> None:
        """Close gaps in list positions (after a card leaves)."""
        for cards in self.cards_by_column(slug).values():
            for pos, card in enumerate(cards):
                if card.position != pos:
                    card.position = pos
                    self._save(slug, card)

    def list_cards(self, slug: str) -> list[Card]:
        self.get_board(slug)
        cards = [_card_from(*_read(p)) for p in (self._board_dir(slug) / "cards").glob("*.md")]
        return sorted(cards, key=lambda c: c.position)

    def cards_by_column(self, slug: str) -> dict[str, list[Card]]:
        board = self.get_board(slug)
        grouped: dict[str, list[Card]] = {col: [] for col in board.columns}
        for card in self.list_cards(slug):
            if not card.archived:
                grouped.setdefault(card.column, []).append(card)
        return grouped

    def get_card(self, slug: str, card_id: str) -> Card:
        path = self._card_path(slug, card_id)
        if not path.exists():
            raise KeyError(card_id)
        return _card_from(*_read(path))

    def update_card(self, slug: str, card_id: str, title: str, body: str, due: str | None,
                    repeat: str | None = None, tags: list[str] | None = None,
                    start: str | None = None, labels: list[str] | None = None,
                    priority: str | None = None) -> Card:
        card = self.get_card(slug, card_id)
        board = self.get_board(slug)
        known = {x["id"] for x in board.labels}
        card.title, card.body, card.due, card.repeat = title, body, due or None, repeat or None
        card.tags, card.start = parse_tags(tags), start or None
        card.labels = [x for x in (labels or []) if x in known]
        card.priority = priority if priority in PRIORITIES else None
        self._save(slug, card)
        return card

    def _set_done(self, slug: str, board: Board, card: Card, now: datetime) -> None:
        stamp = now.isoformat(timespec="minutes")
        card.done, card.completed = True, stamp
        self._save(slug, card)
        self.log_completion(board, card, stamp)

    def _unset_done(self, slug: str, card: Card) -> None:
        if card.completed:
            self.remove_completion(card.id, card.completed)
        card.done, card.completed, card.archived = False, None, False
        self._save(slug, card)

    def complete_card(self, slug: str, card_id: str, now: datetime | None = None) -> Card:
        """Stamp the completion time, then run the board's rules. Repeating cards advance to their
        next due date instead (rules do not apply: they never finish); others toggle done/not done.
        `card.effects` on the result says what rules did, e.g. ["moved to Done"]."""
        now = now or datetime.now()  # local time: the app is meant to run in the owner's zone
        board = self.get_board(slug)
        card = self.get_card(slug, card_id)
        effects: list[str] = []
        if card.repeat:
            stamp = now.isoformat(timespec="minutes")
            due = date.fromisoformat(card.due) if card.due else None
            card.due = next_occurrence(card.repeat, due, now.date()).isoformat()
            card.last_completed = stamp
            self._save(slug, card)
            self.log_completion(board, card, stamp)
        elif card.done:
            self._unset_done(slug, card)
            effects = self._run_rules(slug, "uncompleted", card_id, now)
        else:
            self._set_done(slug, board, card, now)
            effects = self._run_rules(slug, "completed", card_id, now)
        card = self.get_card(slug, card_id)
        card.effects = effects
        return card

    def edit_completion(self, slug: str, card_id: str, new_at: str) -> Card:
        """Change WHEN a completed card shows as completed (forgot to check it off yesterday?).
        Only for a currently-done, non-repeating card: a repeating card has no single `completed`
        stamp to move, only a rolling `last_completed`."""
        card = self.get_card(slug, card_id)
        if card.repeat or not card.done or not card.completed:
            raise ValueError("only a completed, non-repeating card has a date to change")
        old_at = card.completed
        card.completed = new_at
        self._save(slug, card)
        self.edit_completion_at(card.id, old_at, new_at)
        return card

    def undo_complete(self, slug: str, card_id: str, at: str, due: str | None = None,
                      last_completed: str | None = None, column: str | None = None,
                      index: int = 0, tags: str | None = None) -> Card:
        """Reverse a completion made at `at`: dates for a repeating card, and anything a rule did
        (`column`/`index`/`tags` are the card's state before the completion)."""
        board = self.get_board(slug)
        card = self.get_card(slug, card_id)
        if card.repeat:
            card.due, card.last_completed = due or None, last_completed or None
        else:
            card.done, card.completed, card.archived = False, None, False
        if tags is not None:
            card.tags = parse_tags(tags)
        self._save(slug, card)
        self.remove_completion(card_id, at)
        if column in board.columns and card.column != column:
            self._move(slug, card_id, column, index)
        return self.get_card(slug, card_id)

    def archive_done(self, slug: str, column: str) -> list[str]:
        """Clear completed cards out of a list; returns their ids (for undo)."""
        cleared = [c for c in self.cards_by_column(slug).get(column, []) if c.done]
        for card in cleared:
            card.archived = True
            self._save(slug, card)
        self._reindex(slug)
        return [c.id for c in cleared]

    def unarchive(self, slug: str, ids: list[str]) -> None:
        for card_id in ids:
            card = self.get_card(slug, card_id)
            if card.archived:
                card.archived = False
                card.position = len(self.cards_by_column(slug).get(card.column, []))
                self._save(slug, card)

    def move_card_to_board(self, slug: str, card_id: str, dest: str, column: str | None = None,
                           index: int = 0) -> dict:
        """Move a card to another board. Returns where it came from (enough to undo it)."""
        if slug == dest:
            raise ValueError("already on that board")
        target = self.get_board(dest)
        if target.kind not in ("kanban", "tasks") or not target.columns:
            raise ValueError("that board has no lists")
        card = self.get_card(slug, card_id)
        origin = {"board": slug, "column": card.column, "index": next(
            (i for i, c in enumerate(self.cards_by_column(slug).get(card.column, []))
             if c.id == card_id), 0)}
        if column not in target.columns:
            column = next((c for c in target.columns if c not in target.hidden), target.columns[0])
        if self._card_path(dest, card_id).exists():
            card.id = uuid.uuid4().hex[:8]
        card.column = column
        card.position = len(self.cards_by_column(dest)[column])
        self._save(dest, card)
        self._card_path(slug, card_id).unlink()
        self._reindex(slug)
        self._move(dest, card.id, column, index)
        origin["id"] = card.id
        return origin

    def all_cards(self) -> list[tuple[Board, Card]]:
        """Feeds Scheduled, tag counts and cards-with-tag. Archived boards' cards are left out --
        an archived board is meant to be out of the way everywhere active, not just the sidebar."""
        return [(b, c) for b in self.list_boards() if b.kind in ("kanban", "tasks") and not b.archived
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

    def scheduled_cards(self, date_from: str | None = None,
                        date_to: str | None = None) -> list[tuple[Board, Card]]:
        """Every open card with a start or due date, across all boards, soonest first.

        A card's position in this list is decided by `effective_date` (its due date, or its start
        date if it has no due date). `date_from`/`date_to` (inclusive ISO dates) narrow the range;
        leave either blank for an open end. Cards in hidden lists are left out: hiding a list means
        "not now".
        """
        found = [(b, c) for b, c in self.all_cards()
                 if effective_date(c) and not c.done and c.column not in b.hidden]
        if date_from:
            found = [(b, c) for b, c in found if effective_date(c) >= date_from]
        if date_to:
            found = [(b, c) for b, c in found if effective_date(c) <= date_to]
        return sorted(found, key=lambda bc: (effective_date(bc[1]), bc[0].slug, bc[1].position))

    def search(self, query: str) -> list[tuple[Board, Card]]:
        """Cards whose title, notes or board name contain every word of the query. Archived boards
        are left out, same as everywhere else active -- see all_cards."""
        terms = query.lower().split()
        if not terms:
            return []
        hits = []
        for b in self.list_boards():
            if b.archived:
                continue
            for c in self.list_cards(b.slug):
                hay = f"{c.title}\n{c.body}\n{b.title}\n{' '.join('#' + t for t in c.tags)}".lower()
                if all(t in hay for t in terms):
                    hits.append((b, c))
        return hits

    def add_card(self, slug: str, title: str, column: str, due: str | None = None,
                 repeat: str | None = None, tags: list[str] | None = None,
                 top: bool = False, start: str | None = None, labels: list[str] | None = None,
                 priority: str | None = None, body: str = "") -> Card:
        board = self.get_board(slug)
        if column not in board.columns:
            raise ValueError(f"unknown column: {column}")
        siblings = self.cards_by_column(slug)[column]
        known = {x["id"] for x in board.labels}
        card = Card(uuid.uuid4().hex[:8], title, column, position=len(siblings), due=due,
                    repeat=repeat, tags=parse_tags(tags), start=start, body=body,
                    labels=[x for x in (labels or []) if x in known],
                    priority=priority if priority in PRIORITIES else None)
        self._save(slug, card)
        if top and siblings:
            self._move(slug, card.id, column, 0)
        effects = self._run_rules(slug, "added", card.id)
        card = self.get_card(slug, card.id)
        card.effects = effects
        return card

    def import_cards(self, slug: str, rows: list[dict]) -> tuple[int, list[str]]:
        """Create cards from parsed CSV rows (csvimport.parse_csv). Returns (how many were
        created, problems worth mentioning) -- one bad row never aborts the rest of the import.
        A tasks-kind board ignores each row's "list" (there's only ever the one column); a kanban
        board creates any list name it doesn't already have, case-insensitively."""
        board = self.get_board(slug)
        errors: list[str] = []
        created = 0
        for row in rows:
            if board.kind == "tasks":
                column = TASKS_COLUMN
            else:
                wanted = row["list"]
                existing = next((c for c in board.columns if c.lower() == wanted.lower()), None) if wanted else None
                if existing:
                    column = existing
                elif wanted:
                    try:
                        self.add_column(slug, wanted)
                    except ValueError as exc:
                        errors.append(f"{row['title']!r}: {exc}")
                        continue
                    board = self.get_board(slug)
                    column = next(c for c in board.columns if c.lower() == wanted.lower())
                elif board.columns:
                    column = next((c for c in board.columns if c not in board.hidden), board.columns[0])
                else:
                    errors.append(f"{row['title']!r}: board has no lists to import into")
                    continue
            try:
                card = self.add_card(slug, row["title"], column, due=row["due"], tags=row["tags"],
                                     start=row["start"], priority=row["priority"], body=row["notes"])
            except ValueError as exc:
                errors.append(f"{row['title']!r}: {exc}")
                continue
            if row["done"]:
                self.complete_card(slug, card.id)
            created += 1
        return created, errors

    def move_card(self, slug: str, card_id: str, column: str, index: int) -> list[str]:
        """Move a card; if it changed lists, run the board's "moved into" rules.
        Returns what rules did (empty when none fired)."""
        before = self.get_card(slug, card_id).column
        self._move(slug, card_id, column, index)
        return self._run_rules(slug, "moved", card_id) if before != column else []

    def _move(self, slug: str, card_id: str, column: str, index: int) -> None:
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

    # -- saved filters: named date ranges, reused by Scheduled and Logbook ----------------------

    def list_filters(self) -> list[dict]:
        return [f for f in (self._meta().get("filters") or []) if isinstance(f, dict) and f.get("id")]

    def _store_filters(self, filters: list[dict]) -> None:
        meta = self._meta()
        meta["filters"] = filters
        self._write_meta(meta)

    def save_filter(self, name: str, date_from: str | None, date_to: str | None) -> dict:
        name = " ".join(name.split())
        if not name:
            raise ValueError("give the filter a name")
        filters = self.list_filters()
        entry = {"id": uuid.uuid4().hex[:8], "name": name, "from": date_from or None, "to": date_to or None}
        filters.append(entry)
        self._store_filters(filters)
        return entry

    def delete_filter(self, filter_id: str) -> tuple[int, dict]:
        filters = self.list_filters()
        for i, f in enumerate(filters):
            if f["id"] == filter_id:
                del filters[i]
                self._store_filters(filters)
                return i, f
        raise KeyError(filter_id)

    def restore_filter(self, entry: dict, index: int | None = None) -> None:
        filters = self.list_filters()
        filters.insert(len(filters) if index is None else max(0, min(index, len(filters))), entry)
        self._store_filters(filters)

    def rename_board(self, slug: str, title: str) -> None:
        board = self.get_board(slug)
        board.title = self._clean_name(title, [])
        self._save_board(board)
