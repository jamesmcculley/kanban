import os
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, abort, jsonify, request, url_for

from . import notes
from .store import Store


def _stamp(value: str | None) -> str:
    """'2026-09-19T15:42' -> 'Sep 19, 3:42 PM'; date-only values -> 'Sep 19'."""
    if not value:
        return ""
    try:
        dt = datetime.fromisoformat(str(value).replace(" ", "T"))
    except ValueError:
        return str(value)
    return dt.strftime("%b %-d") if len(str(value)) <= 10 else dt.strftime("%b %-d, %-I:%M %p")


def _clock(value: str | None) -> str:
    """'2026-09-19T15:42' -> '3:42 PM' (empty for date-only values)."""
    if not value or len(str(value)) <= 10:
        return ""
    return datetime.fromisoformat(str(value).replace(" ", "T")).strftime("%-I:%M %p")


def _day_label(day: str) -> str:
    """'2026-09-19' -> 'Today' / 'Yesterday' / 'Sat, Sep 19'."""
    d = datetime.fromisoformat(day).date()
    delta = (datetime.now().date() - d).days
    return {0: "Today", 1: "Yesterday"}.get(delta) or d.strftime("%a, %b %-d" + ("" if d.year == datetime.now().year else ", %Y"))


def create_app(data_dir: str | Path | None = None) -> Flask:
    app = Flask(__name__)
    root = data_dir or os.environ.get("KANBAN_DATA_DIR") or Path.home() / "kanban-data"
    app.config["STORE"] = Store(Path(root))
    app.jinja_env.filters.update(stamp=_stamp, clock=_clock, day_label=_day_label)

    def render_notes(card, board):
        """A card's notes as HTML; checklist boxes tick through the server (see toggle_task)."""
        base = url_for("boards.toggle_task", slug=board.slug, card_id=card.id, n=0)
        return notes.render(card.body, task_url=base.rsplit("/", 1)[0] + "/{n}",
                            target=f"[data-id='{card.id}']")

    app.jinja_env.globals.update(render_notes=render_notes, notes_progress=notes.progress)

    app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024  # text forms only now; no image uploads

    from .routes import bp

    app.register_blueprint(bp)

    @app.before_request
    def refuse_cross_origin_writes():
        """The app has no login (it is LAN-only), so a web page on another site must not be able to
        drive it from a device on the LAN. Browsers send Origin on writes; it must be this host."""
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return
        origin = request.headers.get("Origin")
        if (origin and urlparse(origin).netloc != request.host) or \
                request.headers.get("Sec-Fetch-Site") == "cross-site":
            abort(403)

    @app.after_request
    def security_headers(resp):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "same-origin"
        if resp.mimetype == "text/html":
            # Live views of your data: without no-store the Back button shows a cached copy from
            # before your last change.
            resp.headers["Cache-Control"] = "no-store"
            resp.headers["Content-Security-Policy"] = "frame-ancestors 'none'"
        return resp

    @app.get("/api/health")
    def health():
        """Used by the container healthcheck. 200 only when the data folder can be read."""
        app.config["STORE"].list_boards()
        return jsonify(status="ok", version=os.environ.get("APP_VERSION", "dev"))
    return app
