"""Soft delete. Deleting moves things into a `.trash` folder; nothing is destroyed until the
trash is emptied, and every deletion can be undone.

    <board>/.trash/cards/<id>.md      trashed cards
    <board>/.trash/items/<id>.md      trashed canvas items (their image files stay put)
    .trash/boards/<slug>@<time>/      whole trashed boards
"""

from __future__ import annotations

import re
import shutil
import time

from .mdfile import read_md


class TrashMixin:
    def _trash_root(self):
        return self.root / ".trash"

    # -- cards ----------------------------------------------------------

    def trash_card(self, slug: str, card_id: str) -> None:
        src = self._card_path(slug, card_id)
        if not src.exists():
            raise KeyError(card_id)
        dest = self._board_dir(slug) / ".trash" / "cards"
        dest.mkdir(parents=True, exist_ok=True)
        shutil.move(src, dest / src.name)
        self._reindex(slug)

    def restore_card(self, slug: str, card_id: str):
        board = self.get_board(slug)
        self._card_path(slug, card_id)  # validates the id's shape
        src = self._board_dir(slug) / ".trash" / "cards" / f"{card_id}.md"
        if not src.exists():
            raise KeyError(card_id)
        card = self._load_card(src)
        if card.column not in board.columns:  # its list was deleted meanwhile
            if not board.columns:
                raise ValueError("board has no lists")
            card.column = board.columns[0]
        wanted = card.position
        card.position = len(self.cards_by_column(slug)[card.column])
        shutil.move(src, self._card_path(slug, card_id))
        self._save(slug, card)
        self.move_card(slug, card_id, card.column, wanted)
        return card

    # -- boards ---------------------------------------------------------

    def trash_board(self, slug: str) -> str:
        """Returns the trash id to restore it with. Boards nested inside become top-level."""
        self.get_board(slug)
        for child in self.list_boards():
            if child.parent == slug:
                child.parent = None
                self._save_board(child)
        dest = self._trash_root() / "boards"
        dest.mkdir(parents=True, exist_ok=True)
        trash_id = f"{slug}@{int(time.time())}"
        shutil.move(self._board_dir(slug), dest / trash_id)
        return trash_id

    def restore_board(self, trash_id: str):
        if not re.fullmatch(r"[a-z0-9-]+@\d+", trash_id):
            raise KeyError(trash_id)
        src = self._trash_root() / "boards" / trash_id
        if not src.exists():
            raise KeyError(trash_id)
        base = trash_id.split("@")[0]
        slug, n = base, 2
        while (self.root / slug).exists():
            slug, n = f"{base}-{n}", n + 1
        shutil.move(src, self.root / slug)
        return self.get_board(slug)

    # -- listing and emptying ---------------------------------------------

    def list_trash(self) -> dict:
        boards = []
        base = self._trash_root() / "boards"
        for folder in sorted(base.iterdir()) if base.exists() else []:
            meta = read_md(folder / "board.md")[0] if (folder / "board.md").exists() else {}
            boards.append({"id": folder.name, "title": meta.get("title", folder.name),
                           "kind": meta.get("kind", "kanban")})
        cards, items = [], []
        for board in self.list_boards():
            trash = self._board_dir(board.slug) / ".trash"
            cards += [(board, self._load_card(p)) for p in sorted((trash / "cards").glob("*.md"))]
            items += [(board, self._item_from(*read_md(p))) for p in sorted((trash / "items").glob("*.md"))]
        return {"boards": boards, "cards": cards, "items": items}

    def empty_trash(self) -> None:
        shutil.rmtree(self._trash_root(), ignore_errors=True)
        for board in self.list_boards():
            trash = self._board_dir(board.slug) / ".trash"
            for path in (trash / "items").glob("*.md"):
                item = self._item_from(*read_md(path))
                if item.file:
                    self.asset_path(board.slug, item.file).unlink(missing_ok=True)
            shutil.rmtree(trash, ignore_errors=True)
