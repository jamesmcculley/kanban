"""Settings, rules and the engine. The domain modules are pure; the Store applies them."""

from datetime import datetime

import pytest

from kanban import rules as R
from kanban import settings as S
from kanban.store import Store


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path)


def _board(store):
    return store.create_board("Work")            # Todo / Doing / Done


# ---- pure: settings ------------------------------------------------------------------------------

def test_settings_validation_and_inheritance():
    assert S.clean({"new_card_position": "bottom", "auto_hide_done_days": "7", "hide_done": "1"}, S.BOARD_KEYS) == {
        "new_card_position": "bottom", "auto_hide_done_days": 7, "hide_done": True}
    assert S.clean({"new_card_position": "", "hide_done": ""}, S.BOARD_KEYS) == {}   # blank = inherit
    for bad in ({"new_card_position": "middle"}, {"auto_hide_done_days": "-1"}, {"auto_hide_done_days": "x"},
                {"auto_hide_done_days": "400"}, {"hide_done": "maybe"}):
        with pytest.raises(ValueError):
            S.clean(bad, S.BOARD_KEYS)
    assert S.clean({"default_columns": "Inbox, Next ,inbox,\nDone"}, S.GLOBAL_KEYS) == {"default_columns": ["Inbox", "Next", "Done"]}
    with pytest.raises(ValueError):
        S.clean({"default_columns": " , "}, S.GLOBAL_KEYS)
    merged = S.resolve({"new_card_position": "bottom", "hide_done": True}, {"hide_done": False})
    assert merged["new_card_position"] == "bottom" and merged["hide_done"] is False   # board beats global
    assert S.resolve({}, {})["new_card_position"] == "top" and S.resolve({}, {})["default_columns"] == S.DEFAULT_COLUMNS


# ---- pure: rules -------------------------------------------------------------------------------------

LISTS = ["Todo", "Doing", "Done"]


def test_clean_rule_validates_and_normalises():
    r = R.clean_rule({"when": "completed", "do": "move", "arg": " Done "}, LISTS)
    assert (r["when"], r["do"], r["arg"], r["enabled"]) == ("completed", "move", "Done", True) and len(r["id"]) == 8
    assert R.clean_rule({"when": "added", "do": "add_tag", "arg": "#Urgent", "tag": "Home"}, LISTS)["arg"] == "urgent"
    for bad in ({"when": "nope", "do": "archive"}, {"when": "moved", "do": "archive"},          # moved needs a list
                {"when": "completed", "do": "move"}, {"when": "completed", "do": "move", "arg": "Nowhere"},
                {"when": "completed", "in": "Nowhere", "do": "archive"}, {"when": "completed", "do": "add_tag"},
                {"when": "completed", "do": "zap"}, {"when": "completed", "do": "archive", "tag": "9bad"}):
        with pytest.raises(ValueError):
            R.clean_rule(bad, LISTS)
    assert R.clean_rule({"when": "completed", "do": "move", "arg": "Anywhere"}, None)["arg"] == "Anywhere"  # global: any name


def test_matches_and_describe():
    rule = R.clean_rule({"when": "completed", "in": "Todo", "tag": "home", "do": "move", "arg": "Done"}, LISTS)
    assert R.matches(rule, "completed", "Todo", ["home"])
    assert not R.matches(rule, "completed", "Doing", ["home"]) and not R.matches(rule, "completed", "Todo", [])
    assert not R.matches(rule, "added", "Todo", ["home"]) and not R.matches({**rule, "enabled": False}, "completed", "Todo", ["home"])
    assert R.describe(rule) == "When a card is completed in Todo, tagged #home, move it to Done."
    assert R.describe(R.clean_rule({"when": "moved", "in": "Done", "do": "complete"}, LISTS)) == \
        "When a card is moved into Done, mark it complete."
    assert R.describe(R.clean_rule({"when": "added", "in": "Todo", "do": "add_tag", "arg": "new"}, LISTS)) == \
        "When a card is added to Todo, add the tag #new."


def test_domain_modules_are_pure():
    """Standard 01: domain logic never imports UI, HTTP or the filesystem."""
    import ast
    import pathlib
    banned = {"flask", "pathlib", "os", "shutil", "yaml", "kanban.store", "store"}
    root = pathlib.Path(__file__).parent.parent / "src" / "kanban"
    for name in ("rules.py", "settings.py", "dates.py", "notes.py", "tags.py"):
        for node in ast.walk(ast.parse((root / name).read_text())):
            mods = ([a.name for a in node.names] if isinstance(node, ast.Import)
                    else [node.module or ""] if isinstance(node, ast.ImportFrom) and node.level == 0 else [])
            assert not {m.split(".")[0] for m in mods} & banned, f"{name} imports {mods}"


# ---- the engine ------------------------------------------------------------------------------------

def test_checking_a_card_moves_it_to_done(store):
    """The motivating example: complete a card on a board -> it moves to that board's Done list."""
    b = _board(store)
    store.add_rule(b.slug, {"when": "completed", "do": "move", "arg": "Done"})
    a = store.add_card(b.slug, "a", "Todo")
    store.add_card(b.slug, "b", "Todo")
    done = store.complete_card(b.slug, a.id, datetime(2026, 9, 21, 9, 0))
    assert done.column == "Done" and done.done and done.effects == ["moved to Done"]
    assert [c.title for c in store.cards_by_column(b.slug)["Todo"]] == ["b"]
    assert [c.title for c in store.cards_by_column(b.slug)["Done"]] == ["a"]
    assert [e["title"] for e in store.logbook()] == ["a"]                   # still logged, exactly once
    again = store.complete_card(b.slug, a.id)                                # un-check: no uncompleted rule
    assert again.column == "Done" and not again.done and again.effects == []


def test_moving_into_done_completes_and_unchecking_moves_back(store):
    b = _board(store)
    store.add_rule(b.slug, {"when": "moved", "in": "Done", "do": "complete"})
    store.add_rule(b.slug, {"when": "uncompleted", "in": "Done", "do": "move", "arg": "Todo"})
    c = store.add_card(b.slug, "x", "Doing")
    assert store.move_card(b.slug, c.id, "Done", 0) == ["marked complete"]
    card = store.get_card(b.slug, c.id)
    assert card.done and card.completed and store.logbook()[0]["title"] == "x"
    assert store.move_card(b.slug, c.id, "Doing", 0) == []                  # other lists: rule does not match
    store.move_card(b.slug, c.id, "Done", 0)
    back = store.complete_card(b.slug, c.id)                                # check it off again in Done
    assert not back.done and back.column == "Todo" and back.effects == ["moved to Todo"]


def test_rules_do_not_chain_or_loop(store):
    b = _board(store)
    store.add_rule(b.slug, {"when": "completed", "do": "move", "arg": "Done"})
    store.add_rule(b.slug, {"when": "moved", "in": "Done", "do": "uncomplete"})   # would undo it if it chained
    c = store.add_card(b.slug, "x", "Todo")
    card = store.complete_card(b.slug, c.id)
    assert card.done and card.column == "Done"                               # the move did not fire the moved rule
    store.add_rule(b.slug, {"when": "added", "do": "add_tag", "arg": "new"})
    assert store.add_card(b.slug, "y", "Todo").tags == ["new"]


def test_added_rules_conditions_and_actions(store):
    b = _board(store)
    store.add_rule(b.slug, {"when": "added", "in": "Todo", "tag": "home", "do": "add_tag", "arg": "seen"})
    store.add_rule(b.slug, {"when": "completed", "do": "remove_tag", "arg": "seen"})
    store.add_rule(b.slug, {"when": "completed", "tag": "temp", "do": "archive"})
    plain = store.add_card(b.slug, "plain", "Todo")
    home = store.add_card(b.slug, "home", "Todo", tags=["home"])
    assert plain.tags == [] and home.tags == ["home", "seen"] and home.effects == ["tagged #seen"]
    assert store.add_card(b.slug, "elsewhere", "Doing", tags=["home"]).tags == ["home"]   # wrong list
    done = store.complete_card(b.slug, home.id)
    assert done.tags == ["home"] and done.effects == ["removed #seen"]
    temp = store.add_card(b.slug, "temp", "Todo", tags=["temp"])
    store.complete_card(b.slug, temp.id)
    assert temp.id not in [c.id for c in store.cards_by_column(b.slug)["Todo"]]           # archived


def test_global_rules_apply_everywhere_unless_a_board_opts_out(store):
    a, b = store.create_board("A"), store.create_board("B")
    store.add_rule(None, {"when": "completed", "do": "move", "arg": "Done"})
    store.save_board_settings(b.slug, {"inherit_global_rules": "0"})
    for board in (a, b):
        c = store.add_card(board.slug, "x", "Todo")
        assert store.complete_card(board.slug, c.id).column == ("Done" if board is a else "Todo")
    store.add_rule(b.slug, {"when": "completed", "do": "add_tag", "arg": "mine"})       # its own rules still run
    c = store.add_card(b.slug, "y", "Todo")
    assert store.complete_card(b.slug, c.id).tags == ["mine"]
    store.create_board("C", columns=["Only"])                                            # global rule names a missing list
    c = store.add_card("c", "z", "Only")
    assert store.complete_card("c", c.id).effects == []                                  # ...so it quietly does nothing


def test_repeating_cards_roll_forward_and_skip_rules(store):
    b = _board(store)
    store.add_rule(b.slug, {"when": "completed", "do": "move", "arg": "Done"})
    c = store.add_card(b.slug, "water", "Todo", due="2026-09-14", repeat="every monday")
    card = store.complete_card(b.slug, c.id, datetime(2026, 9, 16, 8, 0))
    assert card.column == "Todo" and card.due == "2026-09-21" and card.effects == []


def test_disabled_rules_and_rule_crud(store):
    b = _board(store)
    r = store.add_rule(b.slug, {"when": "completed", "do": "move", "arg": "Done"})
    store.toggle_rule(b.slug, r["id"], False)
    c = store.add_card(b.slug, "x", "Todo")
    assert store.complete_card(b.slug, c.id).column == "Todo"
    store.toggle_rule(b.slug, r["id"], True)
    store.complete_card(b.slug, c.id)                                                    # un-check
    assert store.complete_card(b.slug, c.id).column == "Done"
    second = store.add_rule(b.slug, {"when": "added", "do": "archive"})
    index, removed = store.delete_rule(b.slug, second["id"])
    assert (index, removed["id"]) == (1, second["id"]) and [x["id"] for x in store.list_rules(b.slug)] == [r["id"]]
    store.add_rule(b.slug, removed, index)                                               # undo puts it back in place
    assert [x["id"] for x in store.list_rules(b.slug)] == [r["id"], second["id"]]
    with pytest.raises(KeyError):
        store.delete_rule(b.slug, "nope")
    with pytest.raises(ValueError):
        store.add_rule(b.slug, {"when": "completed", "do": "move", "arg": "Nowhere"})    # validated against this board


def test_undo_restores_what_a_rule_changed(store):
    b = _board(store)
    store.add_rule(b.slug, {"when": "completed", "do": "move", "arg": "Done"})
    store.add_rule(b.slug, {"when": "completed", "do": "add_tag", "arg": "shipped"})
    a = store.add_card(b.slug, "a", "Todo", tags=["x"])
    store.add_card(b.slug, "b", "Todo")
    before = store.get_card(b.slug, a.id)
    done = store.complete_card(b.slug, a.id, datetime(2026, 9, 21, 9, 0))
    assert done.column == "Done" and "shipped" in done.tags
    undone = store.undo_complete(b.slug, a.id, done.completed, column=before.column, index=0, tags="x")
    assert (undone.column, undone.done, undone.tags) == ("Todo", False, ["x"])
    assert store.logbook() == []


# ---- what the board shows: hide-completed is a view, never a write --------------------------------------------

def test_hide_done_settings_are_a_view_and_never_write(store, tmp_path):
    b = _board(store)
    old, recent, _open = (store.add_card(b.slug, t, "Done") for t in ("old", "recent", "open"))
    store.complete_card(b.slug, old.id, datetime(2026, 9, 1, 9, 0))
    store.complete_card(b.slug, recent.id, datetime(2026, 9, 20, 9, 0))
    now = datetime(2026, 9, 21, 12, 0)
    cols, hidden = store.view_columns(b.slug, now)
    assert hidden == 0 and len(cols["Done"]) == 3                                       # default: show everything
    store.save_board_settings(b.slug, {"auto_hide_done_days": "7"})
    cols, hidden = store.view_columns(b.slug, now)
    assert hidden == 1 and sorted(c.title for c in cols["Done"]) == ["open", "recent"]
    store.save_global_settings({"hide_done": "1"})
    cols, hidden = store.view_columns(b.slug, now)
    assert hidden == 2 and [c.title for c in cols["Done"]] == ["open"]
    store.save_board_settings(b.slug, {"hide_done": "0"})                                # board beats global
    assert store.view_columns(b.slug, now)[1] == 0
    files = {p: p.read_text() for p in (tmp_path / b.slug / "cards").glob("*.md")}
    store.view_columns(b.slug, now)
    assert files == {p: p.read_text() for p in files}, "reading the board must not write"
    assert old.id in [c.id for c in store.cards_by_column(b.slug)["Done"]]               # nothing was archived


def test_default_columns_and_new_card_position_settings(store):
    store.save_global_settings({"default_columns": "Backlog, Doing, Shipped", "new_card_position": "bottom"})
    board = store.create_board("Fresh")
    assert board.columns == ["Backlog", "Doing", "Shipped"] and store.settings_for(board.slug)["new_card_position"] == "bottom"
    store.save_board_settings(board.slug, {"new_card_position": "top"})
    assert store.settings_for(board.slug)["new_card_position"] == "top"
    assert store.create_board("Explicit", columns=["Solo"]).columns == ["Solo"]


def test_hand_edited_bad_settings_are_ignored_not_fatal(store, tmp_path):
    b = _board(store)
    path = tmp_path / b.slug / "board.md"
    path.write_text(path.read_text().replace("---\n\n", "settings:\n  new_card_position: sideways\n  hide_done: true\n---\n\n", 1))
    assert store.settings_for(b.slug)["new_card_position"] == "top" and store.settings_for(b.slug)["hide_done"] is True


# ---- unknown frontmatter survives (standard 07) --------------------------------------------------------------

def test_unknown_frontmatter_is_preserved_across_edits(store, tmp_path):
    b = _board(store)
    c = store.add_card(b.slug, "x", "Todo")
    card_path = tmp_path / b.slug / "cards" / f"{c.id}.md"
    card_path.write_text(card_path.read_text().replace("position: 0", "position: 0\naliases: [thing]\ncssclasses: wide"))
    board_path = tmp_path / b.slug / "board.md"
    board_path.write_text(board_path.read_text().replace("columns:", "obsidian_note: keep\ncolumns:", 1))
    store.update_card(b.slug, c.id, "renamed", "notes", None)
    store.complete_card(b.slug, c.id)
    store.rename_board(b.slug, "Renamed")
    store.add_rule(b.slug, {"when": "added", "do": "archive"})
    assert "aliases:" in card_path.read_text() and "cssclasses: wide" in card_path.read_text()
    assert "obsidian_note: keep" in board_path.read_text()
