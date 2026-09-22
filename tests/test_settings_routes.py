"""Settings pages, rule endpoints, rule-aware card routes, and the standards-driven hardening."""

import json

import pytest

from kanban import create_app
from kanban.restore_check import check


@pytest.fixture
def app(tmp_path):
    app = create_app(tmp_path)
    app.test_client().get("/")
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def _add(client, title, column="Todo", slug="my-board"):
    r = client.post(f"/b/{slug}/cards", data={"title": title, "column": column})
    assert r.status_code == 200
    return r.text.split('data-id="')[1][:8]


def _rule(client, **fields):
    data = {"scope": "my-board", "when": "completed", "do": "move", "list": "Done", **fields}
    return client.post("/rules/add", data=data)


# ---- pages ---------------------------------------------------------------------------------------

def test_global_settings_page_and_save(client):
    page = client.get("/settings").text
    for needle in ("Appearance", "Defaults", "Rules for all boards", 'name="new_card_position"',
                   "Checking a card moves it to Done", 'id="all-lists"', "Build a rule"):
        assert needle in page
    assert client.post("/settings", data={"new_card_position": "bottom", "auto_hide_done_days": "7",
                                          "hide_done": "1", "default_columns": "Backlog, Doing, Shipped"}).text == "Saved"
    page = client.get("/settings").text
    assert 'value="Backlog, Doing, Shipped"' in page and '<option value="bottom" selected' in page
    bad = client.post("/settings", data={"auto_hide_done_days": "999"})
    assert bad.status_code == 422 and "between 0 and 365" in bad.text
    assert client.post("/settings", data={"default_columns": " , "}).status_code == 422


def test_board_settings_page_save_and_inherit_toggle(client):
    page = client.get("/b/my-board/settings").text
    assert "Use global (at the top)" in page and "Rules for this board" in page
    assert client.post("/b/my-board/settings", data={"new_card_position": "bottom", "hide_done": "",
                                                     "inherit_global_rules": ["0"]}).text == "Saved"
    page = client.get("/b/my-board/settings").text
    assert '<option value="bottom" selected' in page and 'name="inherit_global_rules" value="1" checked' not in page
    assert client.post("/b/my-board/settings", data={"inherit_global_rules": ["0", "1"]}).text == "Saved"
    assert 'value="1" checked' in client.get("/b/my-board/settings").text          # hidden 0 then checkbox 1 = on
    assert client.get("/b/nope/settings").status_code == 404


def test_board_page_links_to_settings_and_reports_hidden_done(client):
    _add(client, "finished")
    client.post("/b/my-board/settings", data={"hide_done": "1"})
    cid = client.get("/b/my-board").text.split('data-id="')[1][:8]
    client.post(f"/b/my-board/cards/{cid}/complete")
    page = client.get("/b/my-board").text
    assert 'href="/b/my-board/settings"' in page and "1 completed hidden" in page and "finished" not in page.split("</header>")[1]
    assert "finished" in client.get("/logbook").text


# ---- rule endpoints ---------------------------------------------------------------------------------

def test_add_toggle_delete_and_undo_a_rule(client):
    assert _rule(client).headers["HX-Refresh"] == "true"
    page = client.get("/b/my-board/settings").text
    assert "When a card is completed, move it to Done." in page
    rid = page.split("/rules/")[1].split("/toggle")[0]
    assert client.post(f"/rules/{rid}/toggle", data={"scope": "my-board", "enabled": ["0", "1"]}).status_code == 204
    assert 'class="rule"' in client.get("/b/my-board/settings").text
    client.post(f"/rules/{rid}/toggle", data={"scope": "my-board", "enabled": ["0"]})
    assert 'class="rule off"' in client.get("/b/my-board/settings").text
    r = client.post(f"/rules/{rid}/delete", data={"scope": "my-board"}).get_json()
    assert r["undo"]["body"]["index"] == 0 and r["later"] is True and "Deleted rule" in r["message"]
    page = client.get("/b/my-board/settings").text
    assert "No rules yet" in page and "When a card is completed, move it to Done." not in page
    assert client.post(r["undo"]["url"], data=r["undo"]["body"]).status_code == 204
    assert "When a card is completed, move it to Done." in client.get("/b/my-board/settings").text
    assert client.post("/rules/nope/toggle", data={"scope": "my-board"}).status_code == 404
    assert client.post("/rules/restore", data={"scope": "my-board", "rule": "junk"}).status_code == 400


def test_invalid_rules_explain_themselves(client):
    r = _rule(client, list="Nowhere")
    assert r.status_code == 422 and "no list called" in r.text
    assert "Say which list" in _rule(client, when="moved", do="archive", **{"in": ""}).text
    assert "Choose when" in _rule(client, when="").text
    assert _rule(client, scope="nope").status_code == 404


def test_global_rule_via_route_applies_to_boards(client):
    assert client.post("/rules/add", data={"scope": "global", "when": "completed", "do": "move", "list": "Done"}).status_code == 200
    cid = _add(client, "x")
    r = client.post(f"/b/my-board/cards/{cid}/complete")
    assert r.headers["HX-Refresh"] == "true"


# ---- rule-aware card routes -------------------------------------------------------------------------

def test_completing_with_a_rule_refreshes_and_undo_restores_the_card(client):
    _rule(client)
    cid = _add(client, "task")
    other = _add(client, "other")
    r = client.post(f"/b/my-board/cards/{cid}/complete")
    toast = json.loads(r.headers["HX-Trigger"])["toast"]
    assert r.headers["HX-Refresh"] == "true" and toast["later"] is True
    assert "Completed “task” · moved to Done" == toast["message"]
    page = client.get("/b/my-board").text
    assert page.index('data-column="Done"') < page.index("task") and other in page
    assert client.post(toast["undo"]["url"]).status_code == 204
    page = client.get("/b/my-board").text
    assert page.index("task") < page.index('data-column="Done"')                      # back in Todo
    assert "task" not in client.get("/logbook").text.split("<main")[1]                 # completion undone


def test_moving_into_done_with_a_rule_returns_a_refresh(client):
    _rule(client, when="moved", **{"in": "Done"}, do="complete")
    cid = _add(client, "drag me")
    r = client.post(f"/b/my-board/cards/{cid}/move", data={"column": "Done", "index": "0"})
    assert r.status_code == 200 and r.get_json()["refresh"] is True and "marked complete" in r.get_json()["message"]
    assert client.post(f"/b/my-board/cards/{_add(client, 'plain')}/move", data={"column": "Doing", "index": "0"}).status_code == 204


def test_added_rule_and_new_card_position(client):
    _rule(client, when="added", do="add_tag", tagarg="fresh")
    assert client.post("/b/my-board/cards", data={"title": "x", "column": "Todo"}).headers["HX-Refresh"] == "true"
    client.post("/rules/add", data={"scope": "my-board", "when": "added", "do": "archive"})   # nothing stops a silly rule
    client.post("/b/my-board/settings", data={"new_card_position": "bottom"})
    page = client.get("/b/my-board").text
    assert "beforeend" in page and "afterbegin" not in page.split("add-card")[1]              # form appends at the bottom


def test_bottom_position_appends(client):
    client.post("/b/my-board/settings", data={"new_card_position": "bottom"})
    _add(client, "first")
    _add(client, "second")
    page = client.get("/b/my-board").text
    assert page.index("first") < page.index("second")


# ---- hardening from the standards ---------------------------------------------------------------------

def test_cross_origin_writes_are_refused(client):
    ok = {"Origin": "http://localhost"}                       # test client's Host is localhost
    assert client.post("/boards", data={"title": "Same"}, headers=ok).status_code == 302
    for headers in ({"Origin": "https://evil.example"}, {"Origin": "null"}, {"Sec-Fetch-Site": "cross-site"}):
        assert client.post("/boards", data={"title": "Nope"}, headers=headers).status_code == 403
    assert client.get("/b/my-board", headers={"Origin": "https://evil.example"}).status_code == 200   # reads are fine
    assert client.post("/boards", data={"title": "Plain"}).status_code == 302                          # non-browser clients


def test_security_headers_and_health(client, monkeypatch):
    r = client.get("/b/my-board")
    assert r.headers["X-Content-Type-Options"] == "nosniff" and r.headers["Referrer-Policy"] == "same-origin"
    assert "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]
    monkeypatch.setenv("APP_VERSION", "abc1234")
    health = client.get("/api/health")
    assert health.status_code == 200 and health.get_json() == {"status": "ok", "version": "abc1234"}
    assert client.get("/static/app.css").headers["X-Content-Type-Options"] == "nosniff"


def test_manifest_and_pages_do_not_regress(client):
    assert client.get("/manifest.webmanifest").get_json()["name"] == "Kanban"
    for path in ("/scheduled", "/logbook", "/trash", "/settings", "/b/my-board/settings"):
        assert client.get(path).status_code == 200


# ---- restore check ------------------------------------------------------------------------------------

def test_restore_check_opens_a_good_backup_and_fails_on_a_corrupt_one(app, tmp_path):
    store = app.config["STORE"]
    cid = store.add_card("my-board", "keep", "Todo").id
    store.complete_card("my-board", cid)
    store.create_board("Second")
    counts = check(tmp_path)
    assert counts["boards"] == 2 and counts["cards"] == 1 and counts["logbook"] == 1
    (tmp_path / "my-board" / "cards" / f"{cid}.md").write_text("---\nid: [unclosed\n---\n")     # corrupt frontmatter
    with pytest.raises(Exception, match=r".+"):
        check(tmp_path)
    with pytest.raises(SystemExit):
        check(tmp_path / "missing")
