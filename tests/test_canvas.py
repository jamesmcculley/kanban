import base64

import pytest

from kanban import create_app
from kanban.store import Store

# a valid 1x1 PNG
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path)


@pytest.fixture
def canvas(store):
    return store.create_board("Ideas", kind="canvas")


def test_canvas_board_basics(store, canvas):
    assert canvas.kind == "canvas" and canvas.columns == []
    assert store.get_board("ideas").kind == "canvas"
    assert store.list_items("ideas") == []
    assert store.all_cards() == []                              # canvas boards hold no cards
    with pytest.raises(ValueError):
        store.create_board("x", kind="spreadsheet")
    kanban = store.create_board("Plain")
    with pytest.raises(ValueError):
        store.add_item(kanban.slug, "note")                     # items only on canvas boards


def test_notes_move_bring_to_front_and_clamp(store, canvas):
    a = store.add_item("ideas", "note", 10, 20, text="one")
    b = store.add_item("ideas", "note", 5000, -50, text="two")
    assert b.z > a.z and (b.x, b.y) == (4940, 0)                # clamped inside the canvas
    moved = store.update_item("ideas", a.id, x=300, y=400)
    assert (moved.x, moved.y) == (300, 400) and moved.z > b.z   # moving raises it to the front
    store.update_item("ideas", a.id, text="edited", color="blue", w=9999)
    saved = store.get_item("ideas", a.id)
    assert (saved.text, saved.color, saved.w) == ("edited", "blue", 1200)
    store.update_item("ideas", a.id, color="hotpink")            # unknown colours ignored
    assert store.get_item("ideas", a.id).color == "blue"
    assert [i.id for i in store.list_items("ideas")] == [b.id, a.id]  # stacking order


def test_link_urls_must_be_http(store, canvas):
    item = store.add_item("ideas", "link", url="https://www.example.com/a/b")
    assert item.text == "example.com"
    for bad in ("javascript:alert(1)", "data:text/html,<script>", "file:///etc/passwd", "ftp://x", "", "example.com"):
        with pytest.raises(ValueError):
            store.add_item("ideas", "link", url=bad)


def test_images_are_sniffed_not_trusted(store, canvas, tmp_path):
    item = store.add_image("ideas", PNG, 10, 10)
    assert item.file.endswith(".png") and store.asset_path("ideas", item.file).exists()
    for bad in (b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>",
                b"<html>", b"GIF", b""):
        with pytest.raises(ValueError):
            store.add_image("ideas", bad)
    with pytest.raises(ValueError):
        store.add_image("ideas", PNG + b"0" * (10 * 1024 * 1024))   # over the size cap
    for evil in ("../board.md", "abc.png", "12345678.svg", "12345678.png/../x"):
        with pytest.raises(KeyError):
            store.asset_path("ideas", evil)
    store.delete_item("ideas", item.id)
    assert not (tmp_path / "ideas" / "assets" / item.file).exists()  # asset removed with its item


def test_nested_boards_and_safe_delete(store, canvas):
    item = store.add_child_board("ideas", "Roadmap", "canvas", 50, 60)
    child = store.get_board(item.target)
    assert child.parent == "ideas" and child.kind == "canvas"
    assert [b.slug for b in store.sidebar()["unassigned"]] == ["ideas"]   # nested = not in sidebar
    with pytest.raises(ValueError):
        store.add_child_board("ideas", "  ", "kanban")
    store.delete_item("ideas", item.id)
    assert store.get_board("roadmap").parent is None                     # data kept, promoted
    assert {b.slug for b in store.sidebar()["unassigned"]} == {"ideas", "roadmap"}


def test_canvas_files_are_plain_markdown(store, canvas, tmp_path):
    item = store.add_item("ideas", "note", 1, 2, text="hello\nworld")
    text = (tmp_path / "ideas" / "items" / f"{item.id}.md").read_text()
    assert text.startswith("---\n") and "kind: note" in text and text.rstrip().endswith("hello\nworld")


@pytest.fixture
def client(tmp_path):
    app = create_app(tmp_path)
    app.config["STORE"].create_board("Ideas", kind="canvas")
    return app.test_client()


def test_canvas_page_and_item_routes(client):
    page = client.get("/b/ideas").text
    assert 'id="canvas"' in page and "Double-click" in page
    r = client.post("/b/ideas/items", json={"kind": "note", "x": 30, "y": 40, "text": "<b>hi</b>"})
    assert r.status_code == 200 and "&lt;b&gt;hi&lt;/b&gt;" in r.text and "left:30px" in r.text
    item_id = r.text.split('data-id="')[1][:8]
    assert client.patch(f"/b/ideas/items/{item_id}", json={"x": 99, "text": "moved"}).status_code == 204
    assert "left:99px" in client.get("/b/ideas").text
    assert client.patch("/b/ideas/items/deadbeef", json={"x": 1}).status_code == 404
    assert client.delete(f"/b/ideas/items/{item_id}").status_code == 204
    assert client.delete(f"/b/ideas/items/{item_id}").status_code == 404
    assert client.post("/b/ideas/items", json={"kind": "link", "url": "javascript:alert(1)"}).status_code == 400
    assert client.post("/b/ideas/items", json={"kind": "bogus"}).status_code == 400
    assert client.post("/b/nope/items", json={"kind": "note"}).status_code == 404


def test_upload_and_asset_serving(client):
    r = client.post("/b/ideas/upload", data={"file": (__import__("io").BytesIO(PNG), "x.png"), "x": "5", "y": "6"})
    assert r.status_code == 200 and "<img" in r.text
    src = r.text.split('src="')[1].split('"')[0]
    a = client.get(src)
    assert a.status_code == 200 and a.data == PNG
    assert a.headers["X-Content-Type-Options"] == "nosniff" and "sandbox" in a.headers["Content-Security-Policy"]
    svg = __import__("io").BytesIO(b"<svg xmlns='http://www.w3.org/2000/svg'/>")
    assert client.post("/b/ideas/upload", data={"file": (svg, "x.png")}).status_code == 400  # name lies
    assert client.post("/b/ideas/upload", data={}).status_code == 400
    assert client.get("/b/ideas/assets/12345678.png").status_code == 404
    assert client.get("/b/ideas/assets/..%2Fboard.md").status_code == 404


def test_nested_board_route_and_breadcrumb(client):
    r = client.post("/b/ideas/items", json={"kind": "board", "title": "Sub Board", "board_kind": "kanban"})
    assert r.status_code == 200 and "Sub Board" in r.text and "/b/sub-board" in r.text
    page = client.get("/b/sub-board").text
    assert 'class="crumb"' in page and "Ideas" in page
    assert 'data-slug="sub-board"' not in page                       # not in the sidebar
    assert client.post("/boards", data={"title": "New Canvas", "kind": "canvas"}).status_code == 302
    assert 'id="canvas"' in client.get("/b/new-canvas").text
    assert client.post("/boards", data={"title": "Bad", "kind": "nope"}).status_code == 400
