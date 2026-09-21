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
    assert 'class="sidebar"' in page and 'data-go="t"' in page
    assert 'id="fab"' in page and 'data-list-url="/b/my-board/columns"' in page
    assert 'class="add-column"' not in page and 'class="newboard"' not in page      # moved into the +
    assert 'aria-label="Hide list"' in page and 'aria-label="Add card"' in page


def test_quick_add_tags_and_tag_page(client):
    _, html = _add(client, "Buy paint #home tomorrow")
    assert "Buy paint" in html and "#home" in html and "tomorrow" not in html.split("</a>")[0]
    page = client.get("/tag/home").text
    assert "Buy paint" in page and "#home" in page
    assert "#home" in client.get("/b/my-board").text      # sidebar tag list
    assert "No cards with this tag." in client.get("/tag/zzz").text


def test_layout_and_order_routes(client):
    client.post("/areas", data={"name": "Home"})
    client.post("/boards", data={"title": "Second"})
    r = client.post("/layout", json={"areas": ["Home"], "boards": {"": ["second"], "Home": ["my-board"]}})
    assert r.status_code == 204
    page = client.get("/b/second").text
    assert page.index('data-slug="second"') < page.index('data-area="Home"') < page.index('data-slug="my-board"')
    assert client.post("/layout", json={"areas": ["Nope"], "boards": {}}).status_code == 400
    assert client.post("/layout", data="junk").status_code == 400
    client.post("/b/my-board/columns", data={"name": "Extra"})
    r = client.post("/b/my-board/columns/order", json={"names": ["Extra", "Todo", "Doing", "Done"]})
    assert r.status_code == 204
    assert client.post("/b/my-board/columns/order", json={"names": ["Todo"]}).status_code == 400
    page = client.get("/b/my-board").text
    assert page.index('data-column="Extra"') < page.index('data-column="Todo"')


def test_cards_added_from_the_header_land_on_top(client):
    _add(client, "zz-first-added")
    _add(client, "zz-second-added")
    page = client.get("/b/my-board").text
    assert page.index("zz-second-added") < page.index("zz-first-added")


def test_fab_has_no_list_option_on_canvas_pages(client):
    client.post("/boards", data={"title": "Sketch", "kind": "canvas"})
    page = client.get("/b/sketch").text
    assert 'id="fab"' in page and "data-list-url" not in page and 'data-action="list"' not in page


def test_html_pages_are_not_cached_so_back_button_is_fresh(client):
    for path in ("/b/my-board", "/today", "/logbook", "/trash"):
        assert client.get(path).headers["Cache-Control"] == "no-store"
    assert "no-store" not in client.get("/static/app.css").headers.get("Cache-Control", "")   # assets stay cacheable
