import os
from pathlib import Path

from flask import Flask

from .store import Store


def create_app(data_dir: str | Path | None = None) -> Flask:
    app = Flask(__name__)
    root = data_dir or os.environ.get("KANBAN_DATA_DIR") or Path.home() / "kanban-data"
    app.config["STORE"] = Store(Path(root))

    from .routes import bp

    app.register_blueprint(bp)
    return app
