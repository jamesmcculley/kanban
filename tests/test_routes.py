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
