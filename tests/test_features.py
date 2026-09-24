"""Logbook, trash/undo, clear-completed, inbox, moving cards between boards, notes."""

import base64
import json
from datetime import datetime

import pytest

from kanban import create_app, notes
from kanban.store import Store

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path)


@pytest.fixture
def client(tmp_path):
    app = create_app(tmp_path)
    c = app.test_client()
    c.get("/")
    return c


def _add(client, title, slug="my-board", column="Todo"):
    r = client.post(f"/b/{slug}/cards", data={"title": title, "column": column})
    assert r.status_code == 200
    return r.text.split('data-id="')[1][:8]


# ---- logbook ---------------------------------------------------------------------------------

def test_logbook_records_where_it_came_from(store):
    b = store.create_board("Home Reno")
    c = store.add_card(b.slug, "Buy paint", "Doing")
    store.complete_card(b.slug, c.id, datetime(2026, 9, 19, 15, 42))
    [event] = store.logbook()
    assert (event["title"], event["board"], event["board_title"], event["list"], event["at"]) == (
        "Buy paint", "home-reno", "Home Reno", "Doing", "2026-09-19T15:42")
    store.rename_board(b.slug, "Renovation")
    store.rename_column(b.slug, "Doing", "Underway")
    assert store.logbook()[0]["board_title"] == "Home Reno"        # a snapshot: survives renames


def test_logbook_keeps_history_of_repeating_cards_and_undo(store):
    b = store.create_board("B")
    c = store.add_card(b.slug, "water plants", "Todo", due="2026-09-14", repeat="every monday")
    store.complete_card(b.slug, c.id, datetime(2026, 9, 14, 8, 0))
    store.complete_card(b.slug, c.id, datetime(2026, 9, 21, 8, 0))
    events = store.logbook()
    assert [e["at"] for e in events] == ["2026-09-21T08:00", "2026-09-14T08:00"]
    assert all(e.get("repeat") for e in events)
    store.undo_complete(b.slug, c.id, "2026-09-21T08:00", due="2026-09-21", last_completed="2026-09-14T08:00")
    card = store.get_card(b.slug, c.id)
    assert (card.due, card.last_completed) == ("2026-09-21", "2026-09-14T08:00")
    assert [e["at"] for e in store.logbook()] == ["2026-09-14T08:00"]


def test_logbook_uncheck_removes_entry_and_backfills_old_cards(store, tmp_path):
    b = store.create_board("B")
    c = store.add_card(b.slug, "x", "Todo")
    store.complete_card(b.slug, c.id, datetime(2026, 9, 1, 9, 0))
    store.complete_card(b.slug, c.id)                               # un-check
    assert store.logbook() == []
    old = store.add_card(b.slug, "from before the log", "Todo")     # completed by an older version
    path = tmp_path / b.slug / "cards" / f"{old.id}.md"
    path.write_text(path.read_text().replace("position: 1", "position: 1\ndone: true\ncompleted: '2026-08-30T10:00'"))
    [event] = store.logbook()
    assert event["title"] == "from before the log" and event["at"] == "2026-08-30T10:00"


def test_logbook_survives_a_corrupt_line(store, tmp_path):
    b = store.create_board("B")
    c = store.add_card(b.slug, "x", "Todo")
    store.complete_card(b.slug, c.id, datetime(2026, 9, 1, 9, 0))
    with (tmp_path / ".trellis-log.jsonl").open("a") as f:
        f.write("{not json\n")
    assert len(store.logbook()) == 1


def test_logbook_limit_none_returns_everything_the_page_would_truncate(store, tmp_path):
    """Metrics and the CSV export need real totals, not the Logbook page's newest-500 cap. Writes
    the log file directly -- 510 real add_card/complete_card round trips would work too, just far
    more slowly, and this test only cares what logbook() does with an already-full log file."""
    lines = [json.dumps({"at": f"2026-01-{(i % 28) + 1:02d}T09:00", "card": f"c{i}", "title": "x",
                         "board": "b", "board_title": "B", "list": "Todo"}) for i in range(510)]
    (tmp_path / ".trellis-log.jsonl").write_text("\n".join(lines) + "\n")
    assert len(store.logbook()) == 500          # the page's own default is still capped
    assert len(store.logbook(limit=None)) == 510


# ---- trash / undo ---------------------------------------------------------------------------

def test_trash_and_restore_card_keeps_its_place(store):
    b = store.create_board("B")
    ids = [store.add_card(b.slug, t, "Todo").id for t in ("a", "b", "c")]
    store.trash_card(b.slug, ids[1])
    assert [c.title for c in store.cards_by_column(b.slug)["Todo"]] == ["a", "c"]
    assert [t[1].title for t in store.list_trash()["cards"]] == ["b"]
    store.restore_card(b.slug, ids[1])
    assert [c.title for c in store.cards_by_column(b.slug)["Todo"]] == ["a", "b", "c"]
    assert store.list_trash()["cards"] == []


def test_restore_card_whose_list_was_deleted(store):
    b = store.create_board("B")
    c = store.add_card(b.slug, "x", "Doing")
    store.trash_card(b.slug, c.id)
    store.delete_column(b.slug, "Doing")
    assert store.restore_card(b.slug, c.id).column == "Todo"          # falls back to the first list


def test_trash_board_and_restore(store):
    store.create_board("Ideas")
    tid = store.trash_board("ideas")
    assert store.list_boards() == []
    assert store.list_trash()["boards"][0]["title"] == "Ideas"
    store.create_board("Ideas")                                       # slug taken meanwhile
    restored = store.restore_board(tid)
    assert restored.slug == "ideas-2" and restored.title == "Ideas"
    with pytest.raises(KeyError):
        store.restore_board("../etc@1")


def test_empty_trash_is_permanent(store):
    b = store.create_board("B")
    c = store.add_card(b.slug, "x", "Todo")
    store.trash_card(b.slug, c.id)
    store.trash_board(store.create_board("Gone").slug)
    store.empty_trash()
    assert store.list_trash() == {"boards": [], "cards": []}
    with pytest.raises(KeyError):
        store.restore_card(b.slug, c.id)


# ---- clear completed, move, inbox, rename ------------------------------------------------------

def test_archive_done_hides_but_keeps_logbook_and_undo(store):
    b = store.create_board("B")
    done = store.add_card(b.slug, "done", "Todo")
    store.add_card(b.slug, "open", "Todo")
    store.complete_card(b.slug, done.id, datetime(2026, 9, 1, 9, 0))
    assert store.archive_done(b.slug, "Todo") == [done.id]
    assert [c.title for c in store.cards_by_column(b.slug)["Todo"]] == ["open"]
    assert [e["title"] for e in store.logbook()] == ["done"]
    store.delete_column(b.slug, "Doing")                               # archived cards don't block deletes
    store.unarchive(b.slug, [done.id])
    assert [c.title for c in store.cards_by_column(b.slug)["Todo"]] == ["open", "done"]
    store.archive_done(b.slug, "Todo")
    store.complete_card(b.slug, done.id)                               # un-checking returns it to the board
    assert "done" in [c.title for c in store.cards_by_column(b.slug)["Todo"]]


def test_move_card_to_board_and_back(store):
    a, b = store.create_board("A"), store.create_board("B")
    keep = store.add_card("a", "keep", "Todo", tags=["x"])
    moved = store.add_card("a", "moved", "Todo")
    store.add_card("b", "existing", "Doing")
    origin = store.move_card_to_board("a", moved.id, "b")
    assert origin == {"board": "a", "column": "Todo", "index": 1, "id": moved.id}
    assert [c.title for c in store.cards_by_column("a")["Todo"]] == ["keep"]
    assert [c.title for c in store.cards_by_column("b")["Todo"]] == ["moved"]   # first visible list
    store.move_card_to_board("b", moved.id, "a", origin["column"], origin["index"])
    assert [c.title for c in store.cards_by_column("a")["Todo"]] == ["keep", "moved"]
    assert store.get_card("a", keep.id).tags == ["x"] and a and b
    with pytest.raises(ValueError):
        store.move_card_to_board("a", keep.id, "a")
    with pytest.raises(KeyError):
        store.move_card_to_board("a", keep.id, "nope")


def test_rename_board(store):
    b = store.create_board("Old")
    store.rename_board(b.slug, "  New   name ")
    assert store.get_board(b.slug).title == "New name" and store.get_board(b.slug).slug == "old"
    with pytest.raises(ValueError):
        store.rename_board(b.slug, "   ")


# ---- notes / checklists --------------------------------------------------------------------------

BODY = "Intro\n\n- [ ] one\n- [x] two\n  - [ ] nested\n\n```\n- [ ] in code\n```\n\n1. [ ] ordered\n"


def test_notes_tasks_progress_and_toggle():
    assert notes.progress(BODY) == (1, 4)
    assert notes.progress("no list") == (0, 0)
    flipped = notes.toggle_task(BODY, 0)
    assert "- [x] one" in flipped and "- [ ] in code" in flipped        # code block untouched
    assert notes.progress(flipped) == (2, 4)
    assert "- [ ] two" in notes.toggle_task(BODY, 1)
    assert "1. [x] ordered" in notes.toggle_task(BODY, 3)
    with pytest.raises(IndexError):
        notes.toggle_task(BODY, 9)


def test_notes_render_is_safe_and_boxes_line_up_with_toggle():
    html = str(notes.render("<script>alert(1)</script> [x](javascript:alert(1)) [ok](https://e.com)\n\n"
                            "- [ ] a\n- [x] b\n", task_url="/t/{n}", target="#c"))
    assert "<script>" not in html and 'href="javascript' not in html
    assert 'target="_blank" rel="noopener noreferrer" href="https://e.com"' in html
    assert 'data-task="0"' in html and 'data-task="1" checked' in html and 'hx-post="/t/1"' in html
    assert "disabled" in str(notes.render("- [ ] a"))                   # read-only without a task url


# ---- routes ----------------------------------------------------------------------------------------

def test_delete_card_is_undoable_via_toast(client):
    cid = _add(client, "precious")
    r = client.delete(f"/b/my-board/cards/{cid}")
    toast = __import__("json").loads(r.headers["HX-Trigger"])["toast"]
    assert toast["message"] == "Deleted “precious”" and toast["undo"]["url"].endswith(f"/cards/{cid}/restore")
    assert "precious" not in client.get("/b/my-board").text
    assert "precious" in client.get("/trash").text
    assert client.post(toast["undo"]["url"]).status_code == 204
    assert "precious" in client.get("/b/my-board").text


def test_complete_toast_undo_and_logbook_page(client):
    cid = _add(client, "Zebra paint")
    r = client.post(f"/b/my-board/cards/{cid}/complete")
    toast = __import__("json").loads(r.headers["HX-Trigger"])["toast"]
    assert "Completed" in toast["message"]
    page = client.get("/logbook").text
    assert "Zebra paint" in page and "My Board" in page and "Todo" in page   # where it came from
    assert client.post(toast["undo"]["url"]).status_code == 204
    assert "Zebra paint" not in client.get("/logbook").text
    client.post(f"/b/my-board/cards/{cid}/complete")
    assert "HX-Trigger" not in client.post(f"/b/my-board/cards/{cid}/complete").headers   # an un-check: no toast


def test_metrics_page_and_csv_export(client):
    a = _add(client, "Paint fence")
    b = _add(client, "Mow lawn")
    client.post(f"/b/my-board/cards/{a}/complete")
    client.post(f"/b/my-board/cards/{b}/complete")
    page = client.get("/metrics").text
    assert ">2<" in page.split('class="metric-num"')[1][:10]   # total shown
    assert "My Board" in page                                  # by-board breakdown
    r = client.get("/export/activity.csv")
    assert r.status_code == 200
    assert r.headers["Content-Type"].startswith("text/csv")
    assert 'filename="activity.csv"' in r.headers["Content-Disposition"]
    body = r.text
    assert body.startswith("completed_at,title,board,list,priority,tags,repeating\r\n")
    assert "Paint fence" in body and "Mow lawn" in body
    # a date range both filters the page and carries into the export link
    ranged = client.get("/export/activity.csv?from=2099-01-01&to=2099-01-02")
    assert ranged.text == "completed_at,title,board,list,priority,tags,repeating\r\n"
    assert 'filename="activity_2099-01-01_2099-01-02.csv"' in ranged.headers["Content-Disposition"]


def test_export_activity_narrowed_by_text_tags_priority_and_board(client):
    home = _add(client, "Paint fence #home")
    work = _add(client, "Write report")
    client.post(f"/b/my-board/cards/{work}", data={"title": "Write report", "body": "", "priority": "high"})
    client.post(f"/b/my-board/cards/{home}/complete")
    client.post(f"/b/my-board/cards/{work}/complete")

    by_text = client.get("/export/activity.csv?q=fence").text
    assert "Paint fence" in by_text and "Write report" not in by_text

    by_tag = client.get("/export/activity.csv?tags=%23home").text
    assert "Paint fence" in by_tag and "Write report" not in by_tag

    by_priority = client.get("/export/activity.csv?priority=high").text
    assert "Write report" in by_priority and "Paint fence" not in by_priority

    by_board = client.get("/export/activity.csv?board=elsewhere").text
    assert "Paint fence" not in by_board and "Write report" not in by_board  # neither is on "elsewhere"


def test_export_dialog_renders_with_boards_and_current_range(client):
    r = client.get("/export/dialog?from=2026-09-01&to=2026-09-30")
    assert r.status_code == 200
    assert 'value="2026-09-01"' in r.text and 'value="2026-09-30"' in r.text
    assert 'name="board" value="my-board"' in r.text


def test_edit_card_dialog_standalone_reloads_instead_of_swapping_the_card(client):
    cid = _add(client, "x")
    normal = client.get(f"/b/my-board/cards/{cid}").text
    standalone = client.get(f"/b/my-board/cards/{cid}?standalone=1").text
    assert "hx-target=\"[data-id=" in normal and "hx-swap=\"outerHTML\"" in normal
    assert "hx-swap=\"none\"" in standalone and "location.reload()" in standalone


def test_complete_from_agenda_toast_survives_reload(client):
    cid = _add(client, "Pay rent tomorrow")
    r = client.post(f"/b/my-board/cards/{cid}/complete?refresh=1")
    assert r.headers["HX-Refresh"] == "true"
    assert __import__("json").loads(r.headers["HX-Trigger"])["toast"]["later"] is True


def test_capture_routes(client):
    r = client.post("/capture", data={"title": "Phone gran tomorrow #family", "board": "my-board"})
    data = r.get_json()
    assert r.status_code == 200 and data["board"] == "my-board" and data["undo"]["method"] == "DELETE"
    assert client.post("/capture", data={"title": "  ", "board": "my-board"}).status_code == 400
    assert client.post("/capture", data={"title": "x"}).status_code == 400          # no board given
    assert client.post("/capture", data={"title": "x", "board": "nope"}).status_code == 404
    page = client.get("/b/my-board").text
    assert "Phone gran" in page and "#family" in page and "Added to My Board" in data["message"]
    assert 'data-drop-board="my-board"' in page                       # boards are drop targets
    assert client.delete(data["undo"]["url"]).status_code == 200      # the undo really removes it
    assert "Phone gran" not in client.get("/b/my-board").text


def test_clear_done_and_unarchive_routes(client):
    cid = _add(client, "finished")
    _add(client, "still open")
    client.post(f"/b/my-board/cards/{cid}/complete")
    r = client.post("/b/my-board/columns/clear-done", data={"name": "Todo"}).get_json()
    assert r["message"] == "Cleared 1 completed card" and "finished" not in client.get("/b/my-board").text
    assert client.post(r["undo"]["url"], data=r["undo"]["body"]).status_code == 204
    assert "finished" in client.get("/b/my-board").text
    assert client.post("/b/my-board/columns/clear-done", data={"name": "Doing"}).get_json()["message"] == "No completed cards to clear"


def test_move_to_board_route_with_undo(client):
    client.post("/boards", data={"title": "Other"})
    cid = _add(client, "wanderer")
    r = client.post(f"/b/my-board/cards/{cid}/move-board", data={"to": "other"}).get_json()
    assert "Moved “wanderer” to Other" in r["message"]
    assert "wanderer" in client.get("/b/other").text and "wanderer" not in client.get("/b/my-board").text
    assert client.post(r["undo"]["url"], data=r["undo"]["body"]).get_json()["message"].startswith("Moved")
    assert "wanderer" in client.get("/b/my-board").text
    assert client.post(f"/b/my-board/cards/{cid}/move-board", data={"to": "nope"}).status_code == 404
    assert client.post(f"/b/my-board/cards/{cid}/move-board", data={"to": "my-board"}).status_code == 400


def test_board_rename_and_delete_undo_flow(client):
    client.post("/boards", data={"title": "Temp"})
    assert client.post("/b/temp/rename", data={"title": "Permanent"}).headers["HX-Refresh"] == "true"
    assert "Permanent" in client.get("/b/temp").text
    assert client.post("/b/temp/rename", data={"title": " "}).status_code == 400
    r = client.post("/b/temp/delete").get_json()
    assert client.get("/b/temp").status_code == 404 and "Permanent" in client.get("/trash").text
    assert client.post(r["undo"]["url"]).get_json()["board"] == "temp"
    assert client.get("/b/temp").status_code == 200
    client.post("/b/temp/delete")
    assert client.post("/trash/empty").status_code == 200
    assert "Permanent" not in client.get("/trash").text


def test_area_delete_and_restore_routes(client):
    client.post("/areas", data={"name": "Home"})
    client.post("/layout", json={"areas": ["Home"], "boards": {"": [], "Home": ["my-board"]}})
    r = client.post("/areas/delete", data={"name": "Home"}).get_json()
    assert "1 board kept" in r["message"] and r["later"] is True
    assert 'data-area="Home"' not in client.get("/b/my-board").text
    assert client.post(r["undo"]["url"], data=r["undo"]["body"]).status_code == 204
    assert 'data-area="Home"' in client.get("/b/my-board").text


def test_task_toggle_route_and_card_face(client):
    cid = _add(client, "shopping")
    client.post(f"/b/my-board/cards/{cid}", data={"title": "shopping", "body": "- [ ] milk\n- [ ] eggs\n"})
    face = client.post(f"/b/my-board/cards/{cid}/task/0").text
    assert "1/2" in face
    assert client.get(f"/b/my-board/cards/{cid}/body").text == "- [x] milk\n- [ ] eggs\n"
    assert client.post(f"/b/my-board/cards/{cid}/task/9").status_code == 400
    dialog = client.get(f"/b/my-board/cards/{cid}").text
    assert 'data-task="0" checked' in dialog and f"/cards/{cid}/task/1" in dialog
