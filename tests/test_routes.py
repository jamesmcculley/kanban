import pytest

from kanban import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app(tmp_path)
    c = app.test_client()
    c.get("/")  # creates the default board
    return c


def _add(client, title):
    r = client.post("/b/my-board/cards", data={"title": title, "column": "Todo"})
    assert r.status_code == 200
    return r.text.split('data-id="')[1][:8], r.text


def test_quick_add_parses_repeat_and_due(client):
    _, html = _add(client, "Water plants every monday")
    assert "Water plants" in html and "every monday" in html and "↻" in html
    _, html = _add(client, "Pay rent tomorrow")
    assert 'class="due' in html


def test_update_returns_card_in_place(client):
    cid, _ = _add(client, "x")
    r = client.post(f"/b/my-board/cards/{cid}",
                    data={"title": "renamed", "due": "fri", "repeat": "weekly", "body": "n"})
    assert r.status_code == 200 and "renamed" in r.text and f'data-id="{cid}"' in r.text
    bad = client.post(f"/b/my-board/cards/{cid}", data={"title": "t", "due": "", "repeat": "nope"})
    assert bad.status_code == 400


def test_complete_and_refresh_mode(client):
    cid, _ = _add(client, "x")
    r = client.post(f"/b/my-board/cards/{cid}/complete")
    assert "done" in r.text and "checked" in r.text
    r = client.post(f"/b/my-board/cards/{cid}/complete?refresh=1")
    assert r.headers["HX-Refresh"] == "true"
    assert client.post("/b/my-board/cards/deadbeef/complete").status_code == 404


def test_agenda_hides_done_and_search_page(client):
    cid, _ = _add(client, "Pay rent tomorrow")
    assert "Pay rent" in client.get("/upcoming").text
    client.post(f"/b/my-board/cards/{cid}/complete")
    assert "Pay rent" not in client.get("/upcoming").text
    assert "Pay rent" in client.get("/search?q=rent").text
    assert "No cards match" in client.get("/search?q=zzzz").text


def test_column_routes(client):
    assert client.post("/b/my-board/columns", data={"name": "Later"}).headers["HX-Refresh"] == "true"
    assert client.post("/b/my-board/columns", data={"name": "later"}).status_code == 400
    r = client.post("/b/my-board/columns/rename", data={"old": "Later", "new": "Someday"})
    assert r.status_code == 200
    page = client.get("/b/my-board").text
    assert 'value="Someday"' in page and 'value="Later"' not in page
    client.post("/b/my-board/columns/hide", data={"name": "Someday", "hidden": "1"})
    page = client.get("/b/my-board").text
    assert "Hidden lists:" in page and 'data-column="Someday"' not in page
    client.post("/b/my-board/columns/hide", data={"name": "Someday", "hidden": "0"})
    assert 'data-column="Someday"' in client.get("/b/my-board").text
    assert client.post("/b/my-board/columns/delete", data={"name": "Someday"}).status_code == 200
    assert client.post("/b/my-board/columns/delete", data={"name": "Nope"}).status_code == 400
    assert client.post("/b/nope/columns", data={"name": "x"}).status_code == 404


def test_completion_stamp_shown_and_sidebar_layout(client):
    cid, _ = _add(client, "x")
    html = client.post(f"/b/my-board/cards/{cid}/complete").text
    assert 'class="stamp"' in html and "✓" in html
    page = client.get("/b/my-board").text
    assert 'class="sidebar"' in page and 'data-go="t"' in page and "New board" in page
