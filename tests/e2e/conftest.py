"""Real-browser tests. Optional: needs `playwright` and a system Chrome.

    uv run --with playwright pytest tests/e2e
"""

import threading

import pytest
from werkzeug.serving import make_server

from kanban import create_app

sync_api = pytest.importorskip("playwright.sync_api")  # skip the module when not installed
sync_playwright, PlaywrightError = sync_api.sync_playwright, sync_api.Error


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as p:
        try:
            b = p.chromium.launch(channel="chrome", headless=True)
        except PlaywrightError as exc:  # no Chrome installed
            pytest.skip(f"Chrome not available: {exc}")
        yield b
        b.close()


@pytest.fixture
def server(tmp_path):
    app = create_app(tmp_path)
    srv = make_server("127.0.0.1", 0, app, threaded=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


@pytest.fixture
def page(browser, server):
    ctx = browser.new_context(viewport={"width": 1280, "height": 800})
    pg = ctx.new_page()
    problems: list[str] = []
    pg.on("pageerror", lambda e: problems.append(f"pageerror: {e}"))
    pg.on("console", lambda m: m.type == "error" and problems.append(f"console: {m.text}"))
    pg.base = server
    pg.goto(server + "/")
    yield pg
    ctx.close()
    assert not problems, problems
