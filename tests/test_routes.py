import io

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
    assert "Pay rent" in client.get("/scheduled").text
    client.post(f"/b/my-board/cards/{cid}/complete")
    assert "Pay rent" not in client.get("/scheduled").text
    assert "Pay rent" in client.get("/search?q=rent").text
    assert "No cards match" in client.get("/search?q=zzzz").text


def test_advanced_search_narrows_by_tags_priority_board_and_status(client):
    home_id, _ = _add(client, "Paint fence #home")
    client.post("/boards", data={"title": "Second"})
    r = client.post("/b/second/cards", data={"title": "Write report", "column": "Todo"})
    work_id = r.text.split('data-id="')[1][:8]
    client.post(f"/b/second/cards/{work_id}", data={"title": "Write report", "body": "", "priority": "high"})

    page = client.get("/search?tags=%23home").text          # advanced-only, no q -- still searches
    assert "Paint fence" in page and "Write report" not in page

    page = client.get("/search?priority=high").text
    assert "Write report" in page and "Paint fence" not in page

    page = client.get("/search?board=second").text
    assert "Write report" in page and "Paint fence" not in page

    client.post(f"/b/my-board/cards/{home_id}/complete")
    page = client.get("/search?status=done").text
    assert "Paint fence" in page and "Write report" not in page


def test_saved_search_crud_and_pin_to_sidebar(client):
    r = client.post("/searches", data={"name": "Home stuff", "tags": "#home", "return_to": "/search?tags=%23home"})
    assert r.status_code == 302 and r.headers["Location"] == "/search?tags=%23home"
    [entry] = client.application.config["STORE"].list_searches()
    sid = entry["id"]
    assert entry == {"id": sid, "name": "Home stuff", "pinned": False, "q": "", "tags": ["home"],
                     "priority": [], "board": [], "status": []}

    # it shows up as a chip on the Search page and isn't in the sidebar until pinned
    page = client.get("/search").text
    assert "Home stuff" in page and 'aria-labelledby="searches-h"' not in page  # that's Settings, not here
    assert 'class="side-searches"' not in client.get("/b/my-board").text

    assert client.post(f"/searches/{sid}/pin").status_code == 204
    assert 'class="side-searches"' in client.get("/b/my-board").text  # now pinned into the sidebar
    assert client.post(f"/searches/{sid}/pin").status_code == 204     # toggles back off
    assert 'class="side-searches"' not in client.get("/b/my-board").text

    assert client.post(f"/searches/{sid}/rename", data={"name": "  Home  "}).status_code == 204
    assert client.post(f"/searches/{sid}/rename", data={"name": "   "}).status_code == 422

    dup = client.post(f"/searches/{sid}/duplicate")
    assert dup.status_code == 204
    names = {s["name"] for s in client.application.config["STORE"].list_searches()}
    assert names == {"Home", "Home (copy)"}

    assert client.post(f"/searches/{sid}/update", data={"q": "paint", "return_to": "/search"}).status_code == 302
    assert client.application.config["STORE"].get_search(sid)["q"] == "paint"

    assert client.post("/searches/nope/rename", data={"name": "x"}).status_code == 404
    assert client.post(f"/searches/{sid}/delete").status_code == 204
    assert len(client.application.config["STORE"].list_searches()) == 1  # the duplicate is still there


def test_duplicate_card_route_and_undo(client):
    cid, _ = _add(client, "Buy paint")
    assert 'class="dup-btn"' in client.get(f"/b/my-board/cards/{cid}").text

    r = client.post(f"/b/my-board/cards/{cid}/duplicate")
    assert r.status_code == 200
    data = r.get_json()
    assert "Duplicated" in data["message"] and data["undo"]["method"] == "DELETE"
    page = client.get("/b/my-board").text
    assert "Buy paint</span>" in page and "Buy paint (copy)</span>" in page

    assert client.delete(data["undo"]["url"]).status_code == 200  # trashed, same as any card delete
    assert "Buy paint (copy)" not in client.get("/b/my-board").text

    assert client.post("/b/my-board/cards/nope/duplicate").status_code == 404


def test_duplicate_card_to_another_board(client):
    cid, _ = _add(client, "Buy paint")
    client.post("/boards", data={"title": "Second"})

    r = client.post(f"/b/my-board/cards/{cid}/duplicate", data={"to": "second", "column": "Todo"})
    assert r.status_code == 200
    data = r.get_json()
    assert "Duplicated" in data["message"] and "Second" in data["message"]
    assert data["undo"]["url"].startswith("/b/second/cards/")
    assert "Buy paint (copy)" in client.get("/b/second").text
    assert "Buy paint (copy)" not in client.get("/b/my-board").text  # stayed on my-board, not copied there too

    assert client.post(f"/b/my-board/cards/{cid}/duplicate", data={"to": "second", "column": "nope"}).status_code == 400
    assert client.post(f"/b/my-board/cards/{cid}/duplicate", data={"to": "nope", "column": "Todo"}).status_code == 404


def test_duplicate_board_route(client):
    assert 'title="Duplicate this board"' in client.get("/b/my-board").text

    r = client.post("/b/my-board/duplicate", follow_redirects=False)
    assert r.status_code == 302
    dest = r.headers["Location"]
    assert dest == "/b/my-board-copy"
    page = client.get(dest).text
    assert "My Board (copy)" in page

    assert client.post("/b/nope/duplicate").status_code == 404


def test_bulk_select_markup_present_on_board_and_tasks_boards(client):
    _add(client, "x")
    page = client.get("/b/my-board").text
    assert 'data-select-toggle' in page
    assert 'class="select-check"' in page
    assert 'class="bulk-bar" hidden' in page
    assert 'data-duplicate-url="/b/my-board/cards/ID/duplicate"' in page
    assert 'data-delete-url="/b/my-board/cards/ID"' in page  # same path as update, DELETE verb
    assert 'bulk-move-to' in page          # kanban: more than one list, so the move picker shows

    client.post("/boards", data={"title": "Tasks Only", "kind": "tasks"})
    task_page = client.get("/b/tasks-only").text
    assert 'data-select-toggle' in task_page
    assert 'bulk-move-to' not in task_page  # a tasks board has only one list -- no picker to show


def test_board_export_dialog_and_csv(client):
    _add(client, "Paint fence #home")
    r = client.post("/b/my-board/cards", data={"title": "Mow lawn", "column": "Doing"})
    mow_id = r.text.split('data-id="')[1][:8]
    client.post(f"/b/my-board/cards/{mow_id}", data={"title": "Mow lawn", "body": "", "priority": "high"})

    dialog = client.get("/b/my-board/export/dialog")
    assert dialog.status_code == 200
    assert 'action="/b/my-board/export.csv"' in dialog.text
    assert 'name="list" value="Todo"' in dialog.text and 'name="board"' not in dialog.text  # single board: no board picker

    full = client.get("/b/my-board/export.csv")
    assert full.status_code == 200
    assert 'filename="my-board.csv"' in full.headers["Content-Disposition"]
    assert "Paint fence" in full.text and "Mow lawn" in full.text
    assert full.text.splitlines()[0] == "title,board,list,start,due,tags,priority,notes,done"

    by_list = client.get("/b/my-board/export.csv?list=Doing").text
    assert "Mow lawn" in by_list and "Paint fence" not in by_list
    by_priority = client.get("/b/my-board/export.csv?priority=high").text
    assert "Mow lawn" in by_priority and "Paint fence" not in by_priority

    assert client.get("/b/nope/export/dialog").status_code == 404
    assert client.get("/b/nope/export.csv").status_code == 404


def test_scheduled_export_dialog_and_csv(client):
    cid, _ = _add(client, "Paint fence")
    client.post(f"/b/my-board/cards/{cid}", data={"title": "Paint fence", "body": "", "due": "today"})

    dialog = client.get("/scheduled/export/dialog")
    assert dialog.status_code == 200
    assert 'action="/scheduled/export.csv"' in dialog.text
    assert 'name="board" value="my-board"' in dialog.text

    csv_text = client.get("/scheduled/export.csv").text
    assert "Paint fence" in csv_text
    assert client.get("/scheduled/export.csv?board=elsewhere").text.count("\n") == 1  # header only


def test_today_export_dialog_and_csv_combines_sections(client):
    due_id, _ = _add(client, "needs doing")
    client.post(f"/b/my-board/cards/{due_id}", data={"title": "needs doing", "body": "", "due": "today"})
    done_id, _ = _add(client, "already finished")
    client.post(f"/b/my-board/cards/{done_id}/complete")

    dialog = client.get("/today/export/dialog")
    assert dialog.status_code == 200
    assert 'action="/today/export.csv"' in dialog.text
    assert 'name="section" value="due"' in dialog.text

    csv_text = client.get("/today/export.csv").text
    assert csv_text.splitlines()[0] == "section,title,board,list,start,due,tags,priority,notes,done"
    rows = csv_text.splitlines()[1:]
    sections = {r.split(",")[0] for r in rows}
    assert "due" in sections and "completed" in sections and "created" in sections

    due_only = client.get("/today/export.csv?section=due").text
    assert "needs doing" in due_only and "already finished" not in due_only

    # a plain empty search (no q, no advanced fields) is still "type something", not "show all"
    assert "Type something" in client.get("/search").text


def test_column_routes(client):
    assert client.post("/b/my-board/columns", data={"name": "Later"}).headers["HX-Refresh"] == "true"
    assert client.post("/b/my-board/columns", data={"name": "later"}).status_code == 400
    r = client.post("/b/my-board/columns/rename", data={"old": "Later", "new": "Someday"})
    assert r.status_code == 200
    page = client.get("/b/my-board").text
    assert 'value="Someday"' in page and 'value="Later"' not in page
    client.post("/b/my-board/columns/hide", data={"name": "Someday", "hidden": "1"})
    page = client.get("/b/my-board").text
    assert 'class="icon-badge">1<' in page and 'data-column="Someday"' not in page
    client.post("/b/my-board/columns/hide", data={"name": "Someday", "hidden": "0"})
    assert 'data-column="Someday"' in client.get("/b/my-board").text
    assert client.post("/b/my-board/columns/delete", data={"name": "Someday"}).status_code == 200
    assert client.post("/b/my-board/columns/delete", data={"name": "Nope"}).status_code == 400
    assert client.post("/b/nope/columns", data={"name": "x"}).status_code == 404


def test_today_view_shows_due_completed_and_created(client):
    # titles avoid embedded date words ("today"/"tomorrow"/...) -- quick-add would strip them into
    # a due date instead of keeping them in the title, same as "Buy paint tomorrow" -> due tomorrow.
    due_id, _ = _add(client, "needs doing")
    r = client.post(f"/b/my-board/cards/{due_id}", data={"title": "needs doing", "body": "", "due": "today"})
    assert r.status_code == 200
    done_id, _ = _add(client, "already finished")
    client.post(f"/b/my-board/cards/{done_id}/complete")

    page = client.get("/today").text
    assert 'data-page="today"' in page
    due_section = page.split('data-today-section="due"')[1].split('data-today-section="completed"')[0]
    completed_section = page.split('data-today-section="completed"')[1].split('data-today-section="created"')[0]
    created_section = page.split('data-today-section="created"')[1]
    assert "needs doing" in due_section
    assert "already finished" not in due_section                    # completed cards leave the due list
    assert "already finished" in completed_section
    assert "needs doing" in created_section and "already finished" in created_section  # both made today
    assert page.count('aria-label="Edit this card"') >= 4          # every row gets one


def test_star_toggle(client):
    cid, _ = _add(client, "x")
    r = client.post(f"/b/my-board/cards/{cid}/star")
    assert r.status_code == 200 and r.json == {"starred": True}
    r = client.post(f"/b/my-board/cards/{cid}/star")
    assert r.json == {"starred": False}
    assert client.post("/b/my-board/cards/deadbeef/star").status_code == 404


def test_standup_default_back_and_forward_is_seven_days(client):
    done_id, _ = _add(client, "finished recently")
    client.post(f"/b/my-board/cards/{done_id}/complete")
    due_id, _ = _add(client, "coming up")
    client.post(f"/b/my-board/cards/{due_id}", data={"title": "coming up", "body": "", "due": "tomorrow"})

    page = client.get("/standup").text
    assert 'data-page="standup"' in page
    completed_section = page.split('data-standup-section="completed"')[1].split('data-standup-section="upcoming"')[0]
    upcoming_section = page.split('data-standup-section="upcoming"')[1]
    assert "finished recently" in completed_section
    assert "coming up" in upcoming_section


def test_standup_back_zero_shows_no_completed_items(client):
    done_id, _ = _add(client, "finished recently")
    client.post(f"/b/my-board/cards/{done_id}/complete")
    page = client.get("/standup?back=0").text
    completed_section = page.split('data-standup-section="completed"')[1].split('data-standup-section="upcoming"')[0]
    assert "finished recently" not in completed_section


def test_standup_forward_zero_shows_no_upcoming_items(client):
    due_id, _ = _add(client, "coming up")
    client.post(f"/b/my-board/cards/{due_id}", data={"title": "coming up", "body": "", "due": "tomorrow"})
    page = client.get("/standup?forward=0").text
    upcoming_section = page.split('data-standup-section="upcoming"')[1]
    assert "coming up" not in upcoming_section


def test_standup_starred_only_ignores_day_counts(client):
    far_id, _ = _add(client, "far off but starred")
    client.post(f"/b/my-board/cards/{far_id}", data={"title": "far off but starred", "body": "", "due": "in 999 days"})
    client.post(f"/b/my-board/cards/{far_id}/star")
    unstarred_id, _ = _add(client, "not starred")
    client.post(f"/b/my-board/cards/{unstarred_id}", data={"title": "not starred", "body": "", "due": "tomorrow"})

    page = client.get("/standup?starred=1").text
    assert "far off but starred" in page
    assert "not starred" not in page
    # without starred=1 and default 7-day forward window, the far-off card is excluded
    page = client.get("/standup").text
    assert "far off but starred" not in page


def test_standup_exclude_today_only_expires_by_date(client):
    cid, _ = _add(client, "excluded today")
    client.post(f"/b/my-board/cards/{cid}", data={"title": "excluded today", "body": "", "due": "today"})
    assert "excluded today" in client.get("/standup").text
    r = client.post("/standup/exclude", data={"board": "my-board", "card": cid, "scope": "today"})
    assert r.status_code == 204
    assert "excluded today" not in client.get("/standup").text


def test_standup_exclude_always_and_include_again(client):
    cid, _ = _add(client, "excluded always")
    client.post(f"/b/my-board/cards/{cid}", data={"title": "excluded always", "body": "", "due": "today"})
    client.post("/standup/exclude", data={"board": "my-board", "card": cid, "scope": "always"})
    assert "excluded always" not in client.get("/standup").text
    client.post("/standup/include", data={"card": cid})
    assert "excluded always" in client.get("/standup").text


def test_standup_exclude_missing_card_404s(client):
    r = client.post("/standup/exclude", data={"board": "my-board", "card": "deadbeef", "scope": "always"})
    assert r.status_code == 404


def test_completion_stamp_shown_and_sidebar_layout(client):
    cid, _ = _add(client, "x")
    html = client.post(f"/b/my-board/cards/{cid}/complete").text
    assert 'class="stamp"' in html and "✓" in html
    page = client.get("/b/my-board").text
    assert 'class="sidebar"' in page and 'data-go="s"' in page
    assert 'id="fab"' in page and 'data-list-url="/b/my-board/columns"' in page
    assert 'class="add-column"' not in page and 'class="newboard"' not in page      # moved into the +
    assert 'aria-label="Hide list"' in page and 'aria-label="Add card"' in page
    # the eye icon next to "Boards" links to Settings' own "Boards in the sidebar" management --
    # not a popover here, so nothing to assert on this page beyond the link existing
    assert 'href="/settings#boards-h"' in page

    settings_page = client.get("/settings").text
    assert 'class="board-eye-check" data-slug="my-board"' in settings_page


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
    # class="board-row", not just data-slug: the sidebar's "show/hide boards" checklist also
    # carries a data-slug for each board, earlier in the page than the rows themselves.
    assert (page.index('class="board-row" data-slug="second"') < page.index('data-area="Home"')
            < page.index('class="board-row" data-slug="my-board"'))
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


def test_fab_has_no_list_option_off_board_pages(client):
    page = client.get("/scheduled").text
    assert 'id="fab"' in page and "data-list-url" not in page and 'data-action="list"' not in page


def test_html_pages_are_not_cached_so_back_button_is_fresh(client):
    for path in ("/b/my-board", "/today", "/logbook", "/trash"):
        assert client.get(path).headers["Cache-Control"] == "no-store"
    assert "no-store" not in client.get("/static/app.css").headers.get("Cache-Control", "")   # assets stay cacheable


# ---- tasks board -----------------------------------------------------------------------------

def test_create_and_use_a_tasks_board(client):
    r = client.post("/boards", data={"title": "Errands", "kind": "tasks"})
    assert r.status_code == 302 and r.headers["Location"].endswith("/b/errands")
    page = client.get("/b/errands").text
    assert 'id="fab"' in page and "New card" not in page          # tasks.html, not board.html
    r = client.post("/b/errands/cards", data={"title": "Buy milk", "column": "Tasks"})
    assert r.status_code == 200 and "Buy milk" in r.text
    page = client.get("/b/errands").text
    assert "Buy milk" in page
    assert client.get("/b/errands/settings").status_code == 200


def test_unknown_board_kind_is_rejected(client):
    assert client.post("/boards", data={"title": "X", "kind": "canvas"}).status_code == 400


def test_tasks_board_cards_appear_in_search_and_scheduled(client):
    client.post("/boards", data={"title": "Errands", "kind": "tasks"})
    client.post("/b/errands/cards", data={"title": "Call mum tomorrow", "column": "Tasks"})
    assert "Call mum" in client.get("/search?q=mum").text
    assert "Call mum" in client.get("/scheduled").text


# ---- priorities and labels ---------------------------------------------------------------------

def test_update_card_with_priority(client):
    cid, _ = _add(client, "x")
    r = client.post(f"/b/my-board/cards/{cid}", data={"title": "x", "priority": "high"})
    assert r.status_code == 200 and 'p-high' in r.text
    bad = client.post(f"/b/my-board/cards/{cid}", data={"title": "x", "priority": "urgent-ish"})
    assert bad.status_code == 400


def test_label_crud_routes(client):
    r = client.post("/b/my-board/labels", data={"name": "Urgent", "color": "red"})
    assert r.status_code == 200
    page = client.get("/b/my-board/settings").text
    assert "Urgent" in page and 'c-red' in page
    label_id = page.split('data-label="')[1][:8]
    r = client.post(f"/b/my-board/labels/{label_id}", data={"name": "Urgent!", "color": "orange"})
    assert r.status_code == 200
    assert "Urgent!" in client.get("/b/my-board/settings").text
    bad = client.post("/b/my-board/labels", data={"name": "Urgent!", "color": "blue"})
    assert bad.status_code == 422       # duplicate name
    r = client.post(f"/b/my-board/labels/{label_id}/delete")
    assert r.status_code == 200
    assert "Urgent!" not in client.get("/b/my-board/settings").text


def test_card_labels_round_trip_through_update_card(client):
    client.post("/b/my-board/labels", data={"name": "Urgent", "color": "red"})
    label_id = client.get("/b/my-board/settings").text.split('data-label="')[1][:8]
    cid, _ = _add(client, "x")
    r = client.post(f"/b/my-board/cards/{cid}", data={"title": "x", "labels": label_id})
    assert r.status_code == 200 and "label-chip" in r.text and "Urgent" in r.text


def test_archive_and_unarchive_board_routes(client):
    client.post("/boards", data={"title": "Side project"})
    assert "Side project" in client.get("/b/my-board").text  # in the sidebar before archiving

    r = client.post("/b/side-project/archive")
    assert r.status_code == 200 and "Archived" in r.text

    page = client.get("/b/my-board").text
    assert "Side project" not in page                        # gone from the sidebar
    assert client.get("/search?q=side").text.count("side-project") == 0

    archived = client.get("/archived").text
    assert "Side project" in archived and "Unarchive" in archived

    still_reachable = client.get("/b/side-project").text
    assert "Archived" in still_reachable and "Side project" in still_reachable

    r = client.post("/b/side-project/unarchive")
    assert r.status_code == 200
    assert "Side project" in client.get("/b/my-board").text   # back in the sidebar
    archived_main = client.get("/archived").text.split('<main class="agenda trash">')[1].split("</main>")[0]
    assert "Side project" not in archived_main                # gone from the archived list itself


def test_archive_unknown_board_404s(client):
    assert client.post("/b/nope/archive").status_code == 404
    assert client.post("/b/nope/unarchive").status_code == 404


# ---- CSV import -------------------------------------------------------------------------------

def _csv_file(text):
    return (io.BytesIO(text.encode()), "cards.csv")


def test_import_page_and_example_csv(client):
    assert "Import from CSV" in client.get("/b/my-board").text  # reachable from the fab menu
    page = client.get("/import")
    assert page.status_code == 200 and "CSV file" in page.text
    example = client.get("/import/example.csv")
    assert example.status_code == 200 and "text/csv" in example.headers["Content-Type"]
    assert b"title" in example.data


def test_import_creates_a_new_board(client):
    csv_text = "title,list,tags\nBuy paint,Todo,home\nFix bug,Doing,\n"
    r = client.post("/import", data={
        "file": _csv_file(csv_text), "target": "new", "new_title": "Imported Board", "new_kind": "kanban",
    }, content_type="multipart/form-data")
    assert r.status_code == 200 and "Imported <strong>2</strong>" in r.text
    page = client.get("/b/imported-board").text
    assert "Buy paint" in page and "Fix bug" in page and "#home" in page


def test_import_into_an_existing_board(client):
    csv_text = "title,list\nExisting board card,Todo\n"
    r = client.post("/import", data={"file": _csv_file(csv_text), "target": "existing", "existing_slug": "my-board"},
                    content_type="multipart/form-data")
    assert r.status_code == 200
    assert "Existing board card" in client.get("/b/my-board").text


def test_import_into_a_tasks_board(client):
    client.post("/boards", data={"title": "Quick Tasks", "kind": "tasks"})
    csv_text = "title\nDo the thing\n"
    r = client.post("/import", data={"file": _csv_file(csv_text), "target": "existing", "existing_slug": "quick-tasks"},
                    content_type="multipart/form-data")
    assert r.status_code == 200
    assert "Do the thing" in client.get("/b/quick-tasks").text


def test_import_without_a_file_shows_an_error(client):
    r = client.post("/import", data={"target": "new", "new_title": "X"}, content_type="multipart/form-data")
    assert r.status_code == 400 and "Choose a CSV file" in r.text


def test_import_bad_row_and_missing_title_are_reported(client):
    csv_text = "title,due\n,tomorrow\nOk row,not-a-date\n"
    r = client.post("/import", data={"file": _csv_file(csv_text), "target": "new", "new_title": "X"},
                    content_type="multipart/form-data")
    assert r.status_code == 200
    assert "Imported <strong>1</strong>" in r.text
    assert "no title" in r.text and "couldn&#39;t understand" in r.text.lower()


def test_import_unknown_existing_board_400s(client):
    r = client.post("/import", data={"file": _csv_file("title\nx\n"), "target": "existing", "existing_slug": "nope"},
                    content_type="multipart/form-data")
    assert r.status_code == 400


# ---- pinning ------------------------------------------------------------------------------------

def test_toggle_pin_route(client):
    client.post("/boards", data={"title": "Side project"})
    r = client.post("/b/side-project/pin")
    assert r.status_code == 200 and "Pinned" in r.text
    page = client.get("/b/my-board").text
    assert page.index('data-slug="side-project"') < page.index('data-slug="my-board"')  # pinned first

    r = client.post("/b/side-project/pin")
    assert r.status_code == 200 and "Unpinned" in r.text
    page = client.get("/b/my-board").text
    assert page.index('data-slug="my-board"') < page.index('data-slug="side-project"')  # back to normal


def test_pin_unknown_board_404s(client):
    assert client.post("/b/nope/pin").status_code == 404
