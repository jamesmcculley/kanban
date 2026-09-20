import os
from datetime import datetime
from pathlib import Path

from flask import Flask

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


def create_app(data_dir: str | Path | None = None) -> Flask:
    app = Flask(__name__)
    root = data_dir or os.environ.get("KANBAN_DATA_DIR") or Path.home() / "kanban-data"
    app.config["STORE"] = Store(Path(root))
    app.jinja_env.filters["stamp"] = _stamp

    from .routes import bp

    app.register_blueprint(bp)
    return app
