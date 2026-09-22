"""Prove a backup opens: load every board, card and the Logbook with the app's own loader.

    python -m kanban.restore_check /path/to/unpacked/data

Exits non-zero and says what failed. A backup nobody has restored is not a backup (standard 04).
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from .store import Store


def check(root: Path) -> dict:
    """Open everything under `root` read-only in spirit (the Store is pointed at a scratch copy)."""
    if not root.is_dir():
        raise SystemExit(f"restore-check: {root} is not a directory")
    store = Store(root)
    boards = store.list_boards()
    counts = {"boards": len(boards), "cards": 0, "logbook": len(store.logbook())}
    for board in boards:
        counts["cards"] += len(store.list_cards(board.slug))
    store.global_settings()
    store.list_trash()
    return counts


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    source = Path(argv[1])
    with tempfile.TemporaryDirectory() as scratch:      # never open the real data
        import shutil
        copy = Path(scratch) / "data"
        shutil.copytree(source, copy)
        counts = check(copy)
    print("restore-check ok:", ", ".join(f"{n} {k}" for k, n in counts.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
