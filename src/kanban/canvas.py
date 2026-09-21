"""Canvas boards: a freeform surface of notes, links, images and nested boards.

Each item is a Markdown file under `<board>/items/`; uploaded images live in `<board>/assets/`.
"""

from __future__ import annotations

import re
import shutil
import uuid
from dataclasses import dataclass
from urllib.parse import urlparse

from .mdfile import read_md, write_md

ITEM_KINDS = ("note", "link", "image", "board")
COLORS = ("yellow", "green", "blue", "pink", "white")
BOARD_KINDS = ("kanban", "canvas")
MAX_IMAGE_BYTES = 10 * 1024 * 1024
CANVAS_W, CANVAS_H = 5000, 4000
MAX_TEXT = 20_000

# Sniff the bytes, never trust a filename or Content-Type. SVG is deliberately not allowed:
# it can carry script.
_MAGIC = {b"\x89PNG\r\n\x1a\n": "png", b"\xff\xd8\xff": "jpg", b"GIF87a": "gif", b"GIF89a": "gif"}


def sniff_image(data: bytes) -> str | None:
    for magic, ext in _MAGIC.items():
        if data.startswith(magic):
            return ext
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def safe_url(url: str) -> str:
    """Only http(s) links: anything else (javascript:, data:, file:) would be stored XSS."""
    url = url.strip()
    parts = urlparse(url)
    if parts.scheme not in ("http", "https") or not parts.netloc or len(url) > 2000:
        raise ValueError("not an http(s) link")
    return url


def _clamp(value, low: int, high: int, default: int = 0) -> int:
    try:
        return max(low, min(high, int(float(value))))
    except (TypeError, ValueError):
        return default


@dataclass
class Item:
    id: str
    kind: str
    x: int = 0
    y: int = 0
    z: int = 0
    w: int | None = None
    color: str = "yellow"
    text: str = ""
    url: str | None = None
    file: str | None = None
    target: str | None = None  # nested board slug


class CanvasMixin:
    """Mixed into Store; relies on its `_board_dir`, `get_board`, `create_board`, `_save_board`."""

    def _require_canvas(self, slug: str):
        board = self.get_board(slug)
        if board.kind != "canvas":
            raise ValueError("not a canvas board")
        return board

    def _item_path(self, slug: str, item_id: str):
        if not re.fullmatch(r"[0-9a-f]{8}", item_id):
            raise KeyError(item_id)
        return self._board_dir(slug) / "items" / f"{item_id}.md"

    def _save_item(self, slug: str, item: Item) -> None:
        meta = {"id": item.id, "kind": item.kind, "x": item.x, "y": item.y, "z": item.z}
        for key in ("w", "url", "file", "target"):
            if getattr(item, key):
                meta[key] = getattr(item, key)
        if item.kind == "note":
            meta["color"] = item.color
        write_md(self._item_path(slug, item.id), meta, item.text)

    @staticmethod
    def _item_from(meta: dict, body: str) -> Item:
        color = meta.get("color", "yellow")
        return Item(
            id=meta["id"], kind=meta["kind"], x=int(meta.get("x", 0)), y=int(meta.get("y", 0)),
            z=int(meta.get("z", 0)), w=meta.get("w"), color=color if color in COLORS else "yellow",
            text=body.rstrip("\n"), url=meta.get("url"), file=meta.get("file"),
            target=meta.get("target"),
        )

    def list_items(self, slug: str) -> list[Item]:
        self._require_canvas(slug)
        folder = self._board_dir(slug) / "items"
        items = [self._item_from(*read_md(p)) for p in folder.glob("*.md")]
        return sorted(items, key=lambda i: (i.z, i.id))

    def get_item(self, slug: str, item_id: str) -> Item:
        self._require_canvas(slug)
        path = self._item_path(slug, item_id)
        if not path.exists():
            raise KeyError(item_id)
        return self._item_from(*read_md(path))

    def _next_z(self, slug: str) -> int:
        return max((i.z for i in self.list_items(slug)), default=0) + 1

    def add_item(self, slug: str, kind: str, x=0, y=0, *, text: str = "", url: str | None = None,
                 color: str = "yellow", w=None, target: str | None = None,
                 file: str | None = None, item_id: str | None = None) -> Item:
        self._require_canvas(slug)
        if kind not in ITEM_KINDS:
            raise ValueError(f"unknown item kind: {kind}")
        if kind == "link":
            url = safe_url(url or "")
            text = text or urlparse(url).netloc.removeprefix("www.")
        item = Item(
            item_id or uuid.uuid4().hex[:8], kind, _clamp(x, 0, CANVAS_W - 60),
            _clamp(y, 0, CANVAS_H - 40), self._next_z(slug),
            _clamp(w, 80, 1200) if w else None, color if color in COLORS else "yellow",
            text[:MAX_TEXT], url, file, target,
        )
        self._save_item(slug, item)
        return item

    def update_item(self, slug: str, item_id: str, **fields) -> Item:
        """Move, resize, recolour or re-text an item. Moving also brings it to the front."""
        item = self.get_item(slug, item_id)
        if "x" in fields or "y" in fields:
            item.x = _clamp(fields.get("x", item.x), 0, CANVAS_W - 60, item.x)
            item.y = _clamp(fields.get("y", item.y), 0, CANVAS_H - 40, item.y)
            item.z = self._next_z(slug)
        if "w" in fields:
            item.w = _clamp(fields["w"], 80, 1200, item.w or 240)
        if "color" in fields and fields["color"] in COLORS:
            item.color = fields["color"]
        if "text" in fields and item.kind in ("note", "link"):
            item.text = str(fields["text"])[:MAX_TEXT]
        self._save_item(slug, item)
        return item

    def delete_item(self, slug: str, item_id: str) -> None:
        """Move to the trash (an image's file stays until the trash is emptied)."""
        item = self.get_item(slug, item_id)
        if item.kind == "board" and item.target:
            try:  # never delete the child's data: promote it to a top-level board instead
                child = self.get_board(item.target)
            except KeyError:
                pass
            else:
                child.parent = None
                self._save_board(child)
        dest = self._board_dir(slug) / ".trash" / "items"
        dest.mkdir(parents=True, exist_ok=True)
        shutil.move(self._item_path(slug, item_id), dest / f"{item_id}.md")

    def restore_item(self, slug: str, item_id: str) -> Item:
        self._require_canvas(slug)
        self._item_path(slug, item_id)  # validates the id's shape
        src = self._board_dir(slug) / ".trash" / "items" / f"{item_id}.md"
        if not src.exists():
            raise KeyError(item_id)
        item = self._item_from(*read_md(src))
        shutil.move(src, self._item_path(slug, item_id))
        if item.kind == "board" and item.target:
            try:  # it was promoted when deleted; nest it again
                child = self.get_board(item.target)
            except KeyError:
                pass
            else:
                if child.parent is None:
                    child.parent = slug
                    self._save_board(child)
        return item

    def add_image(self, slug: str, data: bytes, x=0, y=0) -> Item:
        self._require_canvas(slug)
        if len(data) > MAX_IMAGE_BYTES:
            raise ValueError("image too large")
        ext = sniff_image(data)
        if ext is None:
            raise ValueError("not a supported image (png, jpg, gif, webp)")
        item_id = uuid.uuid4().hex[:8]
        assets = self._board_dir(slug) / "assets"
        assets.mkdir(exist_ok=True)
        filename = f"{item_id}.{ext}"
        (assets / filename).write_bytes(data)
        return self.add_item(slug, "image", x, y, w=320, file=filename, item_id=item_id)

    def asset_path(self, slug: str, filename: str):
        if not re.fullmatch(r"[0-9a-f]{8}\.(png|jpg|gif|webp)", filename):
            raise KeyError(filename)
        return self._board_dir(slug) / "assets" / filename

    def add_child_board(self, slug: str, title: str, kind: str = "kanban", x=0, y=0) -> Item:
        self._require_canvas(slug)
        if kind not in BOARD_KINDS:
            raise ValueError(f"unknown board kind: {kind}")
        title = " ".join(title.split())
        if not title:
            raise ValueError("board title is empty")
        child = self.create_board(title, kind=kind, parent=slug)
        return self.add_item(slug, "board", x, y, target=child.slug)
