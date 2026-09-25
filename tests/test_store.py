import os
import time
from datetime import datetime

import pytest

from kanban.store import Store


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path)


def test_cards_persist_as_markdown(store, tmp_path):
    board = store.create_board("Home Reno")
    card = store.add_card(board.slug, "Buy paint", "Todo")
    text = (tmp_path / board.slug / "cards" / f"{card.id}.md").read_text()
    assert text.startswith("---\n") and "title: Buy paint" in text


def test_move_between_columns_reindexes(store):
    b = store.create_board("B")
    a = store.add_card(b.slug, "a", "Todo")
    c = store.add_card(b.slug, "c", "Todo")
    d = store.add_card(b.slug, "d", "Doing")
    store.move_card(b.slug, c.id, "Doing", 0)
    cols = store.cards_by_column(b.slug)
    assert [x.id for x in cols["Todo"]] == [a.id]
    assert [x.id for x in cols["Doing"]] == [c.id, d.id]


def test_rejects_path_traversal(store):
    with pytest.raises(KeyError):
        store.get_board("../etc")


def test_unknown_column(store):
    b = store.create_board("B")
    with pytest.raises(ValueError):
        store.add_card(b.slug, "x", "Nope")


def test_update_and_dated_cards(store):
    b = store.create_board("B")
    c = store.add_card(b.slug, "x", "Todo")
    store.add_card(b.slug, "no date", "Todo")
    store.update_card(b.slug, c.id, "renamed", "notes", "2026-10-01")
    assert [(bd.slug, cd.title, cd.due) for bd, cd in store.scheduled_cards()] == [
        ("b", "renamed", "2026-10-01")]
    assert store.get_card(b.slug, c.id).body.strip() == "notes"


def test_hand_edited_unquoted_date(store, tmp_path):
    b = store.create_board("B")
    c = store.add_card(b.slug, "x", "Todo")
    path = tmp_path / b.slug / "cards" / f"{c.id}.md"
    path.write_text(path.read_text().replace("position: 0", "position: 0\ndue: 2026-10-01"))
    assert store.get_card(b.slug, c.id).due == "2026-10-01"


def test_complete_toggles_and_hides_from_agenda(store):
    from datetime import datetime
    b = store.create_board("B")
    c = store.add_card(b.slug, "x", "Todo", due="2026-10-01")
    done = store.complete_card(b.slug, c.id, datetime(2026, 9, 30, 15, 42))
    assert done.done and done.completed == "2026-09-30T15:42"
    assert store.get_card(b.slug, c.id).completed == "2026-09-30T15:42"  # persisted, not just returned
    assert store.scheduled_cards() == []
    assert not store.complete_card(b.slug, c.id).done  # second press undoes it
    assert len(store.scheduled_cards()) == 1


def test_complete_repeating_rolls_forward(store):
    from datetime import datetime
    b = store.create_board("B")
    c = store.add_card(b.slug, "water", "Todo", due="2026-09-14", repeat="every monday")
    card = store.complete_card(b.slug, c.id, datetime(2026, 9, 16, 8, 5))
    assert (card.due, card.done, card.repeat) == ("2026-09-21", False, "every monday")
    saved = store.get_card(b.slug, c.id)
    assert saved.due == "2026-09-21" and saved.last_completed == "2026-09-16T08:05"


def test_search(store):
    a = store.create_board("Home Reno")
    b = store.create_board("Work")
    c = store.add_card(a.slug, "Buy paint", "Todo")
    store.update_card(a.slug, c.id, "Buy paint", "Behr eggshell", None)
    store.add_card(b.slug, "Paint the roadmap", "Todo")
    assert len(store.search("paint")) == 2
    assert [cd.title for _, cd in store.search("eggshell paint")] == ["Buy paint"]
    assert len(store.search("home")) == 1  # board name matches
    assert store.search("  ") == []


def test_add_and_rename_column_moves_cards(store):
    b = store.create_board("B")
    c = store.add_card(b.slug, "x", "Doing")
    store.add_column(b.slug, "  Someday  ")
    store.rename_column(b.slug, "Doing", "In progress")
    board = store.get_board(b.slug)
    assert board.columns == ["Todo", "In progress", "Done", "Someday"]
    assert store.get_card(b.slug, c.id).column == "In progress"
    assert [x.id for x in store.cards_by_column(b.slug)["In progress"]] == [c.id]


def test_column_name_validation(store):
    b = store.create_board("B")
    for bad in ("", "   ", "todo"):  # empty, blank, case-insensitive duplicate
        with pytest.raises(ValueError):
            store.add_column(b.slug, bad)
    with pytest.raises(ValueError):
        store.rename_column(b.slug, "Todo", "done")
    with pytest.raises(ValueError):
        store.rename_column(b.slug, "Nope", "X")
    store.rename_column(b.slug, "Todo", "TODO")  # changing only the case of itself is fine
    assert store.get_board(b.slug).columns[0] == "TODO"


def test_hidden_columns_persist_and_leave_agenda(store):
    b = store.create_board("B")
    store.add_card(b.slug, "later thing", "Done", due="2026-10-01")
    store.add_card(b.slug, "now thing", "Todo", due="2026-10-01")
    store.set_column_hidden(b.slug, "Done", True)
    assert store.get_board(b.slug).hidden == ["Done"]
    assert [c.title for _, c in store.scheduled_cards()] == ["now thing"]
    assert len(store.search("later")) == 1  # still findable
    store.rename_column(b.slug, "Done", "Archive")
    assert store.get_board(b.slug).hidden == ["Archive"]
    store.set_column_hidden(b.slug, "Archive", False)
    assert store.get_board(b.slug).hidden == [] and len(store.scheduled_cards()) == 2


def test_delete_column_only_when_empty(store):
    b = store.create_board("B")
    store.add_card(b.slug, "x", "Todo")
    with pytest.raises(ValueError):
        store.delete_column(b.slug, "Todo")
    store.delete_column(b.slug, "Doing")
    assert store.get_board(b.slug).columns == ["Todo", "Done"]


def test_tags_parse_and_split():
    from kanban.tags import parse_tags, split_tags
    assert parse_tags("#Home, errand  home #9lives") == ["home", "errand"]
    assert split_tags("Buy paint #home #Errand tomorrow") == ("Buy paint tomorrow", ["home", "errand"])
    assert split_tags("Fix bug #123") == ("Fix bug #123", [])           # numbers are not tags
    assert split_tags("mail a#b") == ("mail a#b", [])                    # must start a word


def test_tags_persist_search_counts(store):
    b = store.create_board("B")
    c = store.add_card(b.slug, "paint", "Todo", tags=["home", "errand"])
    store.add_card(b.slug, "other", "Todo", tags=["home"])
    assert store.get_card(b.slug, c.id).tags == ["home", "errand"]
    assert store.tag_counts() == [("errand", 1), ("home", 2)]
    assert len(store.search("#errand")) == 1
    store.complete_card(b.slug, c.id)
    assert store.tag_counts() == [("home", 1)]            # done cards stop counting
    assert [x.title for _, x in store.cards_with_tag("home")] == ["other", "paint"]  # open first
    store.update_card(b.slug, c.id, "paint", "", None, None, ["Garden"])
    assert store.get_card(b.slug, c.id).tags == ["garden"]


def test_board_order_and_areas(store):
    for title in ("Alpha", "Beta", "Gamma"):
        store.create_board(title)
    assert [x.slug for x in store.list_boards()] == ["alpha", "beta", "gamma"]
    store.add_area("Home")
    store.add_area("Work")
    store.apply_layout(["Work", "Home"], {"": ["gamma"], "Work": ["beta"], "Home": ["alpha"]})
    assert store.areas() == ["Work", "Home"]
    assert [x.slug for x in store.list_boards()] == ["gamma", "beta", "alpha"]
    tree = store.sidebar()
    assert [x.slug for x in tree["unassigned"]] == ["gamma"]
    assert [(n, [x.slug for x in bs]) for n, bs in tree["areas"]] == [("Work", ["beta"]), ("Home", ["alpha"])]
    store.rename_area("Work", "Job")
    assert store.get_board("beta").area == "Job" and store.areas() == ["Job", "Home"]
    index, held = store.delete_area("Job")             # boards are kept, just unassigned
    assert (index, held) == (0, ["beta"]) and store.get_board("beta").area is None
    store.restore_area("Job", index, held)              # ...and it can be undone
    assert store.areas() == ["Job", "Home"] and store.get_board("beta").area == "Job"
    store.apply_layout(["Job", "Home"], {"": ["gamma", "beta"], "Home": ["alpha"]})
    store.delete_area("Job")
    assert store.areas() == ["Home"]
    with pytest.raises(ValueError):
        store.apply_layout(["Home", "Ghost"], {})       # stale area list
    with pytest.raises(KeyError):
        store.apply_layout(["Home"], {"Home": ["nope"]})  # forged slug


def test_reorder_columns_keeps_hidden_slots(store):
    b = store.create_board("B", ["A", "B", "C", "D"])
    store.set_column_hidden(b.slug, "B", True)
    store.reorder_columns(b.slug, ["D", "C", "A"])
    assert store.get_board(b.slug).columns == ["D", "B", "C", "A"]
    with pytest.raises(ValueError):
        store.reorder_columns(b.slug, ["A", "B", "C", "D"])  # includes hidden -> mismatch


def test_add_card_at_top(store):
    b = store.create_board("B")
    first = store.add_card(b.slug, "first", "Todo")
    second = store.add_card(b.slug, "second", "Todo", top=True)
    third = store.add_card(b.slug, "third", "Todo", top=True)
    assert [c.id for c in store.cards_by_column(b.slug)["Todo"]] == [third.id, second.id, first.id]
    assert [c.position for c in store.cards_by_column(b.slug)["Todo"]] == [0, 1, 2]
    other = store.add_card(b.slug, "elsewhere", "Doing", top=True)          # empty list: no shuffling
    assert store.get_card(b.slug, other.id).position == 0


def test_duplicate_card_copies_fields_and_lands_right_after_the_original(store):
    b = store.create_board("B")
    store.add_card(b.slug, "before", "Todo")
    original = store.add_card(b.slug, "Buy paint", "Todo", due="2026-10-01", tags=["home"],
                              priority="high", repeat="every monday", body="get primer too")
    store.add_card(b.slug, "after", "Todo")

    copy = store.duplicate_card(b.slug, original.id)
    assert copy.id != original.id
    assert copy.title == "Buy paint (copy)"
    assert (copy.due, copy.tags, copy.priority, copy.repeat, copy.body) == (
        original.due, original.tags, original.priority, original.repeat, original.body)
    assert copy.created is not None

    ordered = store.cards_by_column(b.slug)["Todo"]
    assert [c.title for c in ordered] == ["before", "Buy paint", "Buy paint (copy)", "after"]


def test_duplicate_card_of_a_done_card_starts_fresh(store):
    b = store.create_board("B")
    card = store.add_card(b.slug, "x", "Todo")
    store.complete_card(b.slug, card.id, datetime(2026, 9, 1, 9, 0))
    copy = store.duplicate_card(b.slug, card.id)
    assert copy.done is False and copy.completed is None    # not the original's done state


def test_duplicate_card_keeps_labels(store):
    b = store.create_board("B")
    lbl = store.add_label(b.slug, "Urgent", "red")
    card = store.add_card(b.slug, "x", "Todo", labels=[lbl["id"]])
    copy = store.duplicate_card(b.slug, card.id)
    assert copy.labels == [lbl["id"]]


def test_duplicate_card_missing_card_raises_keyerror(store):
    b = store.create_board("B")
    with pytest.raises(KeyError):
        store.duplicate_card(b.slug, "nope")


def test_duplicate_card_to_another_board_lands_at_the_end_of_the_chosen_list(store):
    a = store.create_board("A")
    b = store.create_board("B")
    store.add_card(b.slug, "already here", "Doing")
    card = store.add_card(a.slug, "Buy paint", "Todo", tags=["home"], priority="high")

    copy = store.duplicate_card(a.slug, card.id, b.slug, "Doing")
    assert copy.title == "Buy paint (copy)"
    assert [c.title for c in store.cards_by_column(b.slug)["Doing"]] == ["already here", "Buy paint (copy)"]
    assert [c.title for c in store.list_cards(a.slug)] == ["Buy paint"]   # the original never moved
    assert copy.tags == ["home"] and copy.priority == "high"


def test_duplicate_card_to_another_board_only_keeps_labels_that_board_has(store):
    a = store.create_board("A")
    b = store.create_board("B")
    lbl = store.add_label(a.slug, "Urgent", "red")
    card = store.add_card(a.slug, "x", "Todo", labels=[lbl["id"]])
    copy = store.duplicate_card(a.slug, card.id, b.slug, "Todo")
    assert copy.labels == []          # b.slug has no labels at all, let alone this id


def test_duplicate_card_to_another_board_unknown_list_raises_valueerror(store):
    a = store.create_board("A")
    b = store.create_board("B")
    card = store.add_card(a.slug, "x", "Todo")
    with pytest.raises(ValueError):
        store.duplicate_card(a.slug, card.id, b.slug, "Nope")


def test_duplicate_card_to_another_board_unknown_board_raises_keyerror(store):
    a = store.create_board("A")
    card = store.add_card(a.slug, "x", "Todo")
    with pytest.raises(KeyError):
        store.duplicate_card(a.slug, card.id, "nope", "Todo")


# ---- duplicate_board ---------------------------------------------------------------------------

def test_duplicate_board_copies_structure_settings_rules_and_labels(store):
    b = store.create_board("Home Reno")
    store.add_column(b.slug, "Someday")
    store.set_column_hidden(b.slug, "Someday", True)
    store.add_area("House")
    store.apply_layout(["House"], {"House": [b.slug]})
    store.save_board_settings(b.slug, {"hide_done": "1"})
    store.add_rule(b.slug, {"when": "completed", "do": "move", "arg": "Done"})
    lbl = store.add_label(b.slug, "Urgent", "red")

    copy = store.duplicate_board(b.slug)
    assert copy.slug != b.slug
    assert copy.title == "Home Reno (copy)"
    assert copy.kind == "kanban" and copy.columns == store.get_board(b.slug).columns
    assert copy.hidden == ["Someday"] and copy.area == "House"
    assert copy.pinned is False and copy.archived is False
    assert store.settings_for(copy.slug)["hide_done"] is True
    assert len(copy.rules) == 1 and copy.rules[0]["do"] == "move"
    assert copy.labels == [lbl]


def test_duplicate_board_copies_every_card_as_is_including_done_ones(store):
    b = store.create_board("B")
    store.add_card(b.slug, "open one", "Todo", tags=["home"], priority="high")
    done = store.add_card(b.slug, "done one", "Todo")
    store.complete_card(b.slug, done.id, datetime(2026, 9, 1, 9, 0))

    copy = store.duplicate_board(b.slug)
    cards = {c.title: c for c in store.list_cards(copy.slug)}
    assert set(cards) == {"open one", "done one"}          # titles unchanged, unlike duplicate_card
    assert cards["open one"].tags == ["home"] and cards["open one"].priority == "high"
    assert cards["done one"].done is True                  # a full snapshot, not reset like a single card
    assert all(c.id != orig.id for c, orig in zip(
        store.list_cards(copy.slug), store.list_cards(b.slug), strict=False))


def test_duplicate_board_starts_unpinned_and_unarchived_even_if_original_was(store):
    b = store.create_board("B")
    store.set_pinned(b.slug, True)
    store.archive_board(b.slug)
    copy = store.duplicate_board(b.slug)
    assert copy.pinned is False and copy.archived is False


def test_duplicate_board_missing_board_raises_keyerror(store):
    with pytest.raises(KeyError):
        store.duplicate_board("nope")


def test_card_created_timestamp_round_trips_and_survives_an_edit(store):
    b = store.create_board("B")
    card = store.add_card(b.slug, "x", "Todo", now=datetime(2026, 9, 1, 8, 30))
    assert card.created == "2026-09-01T08:30"
    assert store.get_card(b.slug, card.id).created == "2026-09-01T08:30"   # round-trips through disk
    updated = store.update_card(b.slug, card.id, "renamed", "", None)
    assert updated.created == "2026-09-01T08:30"                            # unrelated edits don't touch it


def test_created_on_filters_by_day_across_boards_and_ignores_cards_without_one(store, tmp_path):
    a = store.create_board("A")
    b = store.create_board("B")
    store.add_card(a.slug, "today a", "Todo", now=datetime(2026, 9, 14, 9, 0))
    store.add_card(a.slug, "today a, later", "Todo", now=datetime(2026, 9, 14, 17, 0))
    store.add_card(b.slug, "today b", "Todo", now=datetime(2026, 9, 14, 12, 0))
    store.add_card(b.slug, "yesterday", "Todo", now=datetime(2026, 9, 13, 9, 0))
    old = store.add_card(a.slug, "no created field at all", "Todo")   # simulate a pre-upgrade card
    path = tmp_path / a.slug / "cards" / f"{old.id}.md"
    path.write_text(path.read_text().replace("created: '2026-09-14T", "was: '2026-09-14T"))

    todays = store.created_on("2026-09-14")
    assert [c.title for _, c in todays] == ["today a, later", "today b", "today a"]  # newest first
    assert store.created_on("2026-09-15") == []


# ---- tasks board kind ------------------------------------------------------------------------

def test_create_tasks_board_gets_a_single_hidden_tasks_list(store):
    b = store.create_board("Errands", kind="tasks")
    assert b.kind == "tasks" and b.columns == ["Tasks"]


def test_unknown_board_kind_rejected(store):
    with pytest.raises(ValueError):
        store.create_board("B", kind="canvas")


def test_tasks_board_cards_show_up_everywhere_kanban_cards_do(store):
    b = store.create_board("Errands", kind="tasks")
    store.add_card(b.slug, "buy milk", "Tasks", tags=["home"])
    assert [c.title for _, c in store.all_cards()] == ["buy milk"]
    assert [c.title for _, c in store.search("milk")] == ["buy milk"]


def test_move_card_onto_a_tasks_board(store):
    kanban = store.create_board("K")
    tasks = store.create_board("T", kind="tasks")
    card = store.add_card(kanban.slug, "x", "Todo")
    origin = store.move_card_to_board(kanban.slug, card.id, tasks.slug)
    assert origin["board"] == "k" and origin["column"] == "Todo" and origin["index"] == 0
    assert store.get_card(tasks.slug, origin["id"]).column == "Tasks"


def test_move_card_onto_a_board_with_no_lists_fails(store):
    empty = store.create_board("Empty")
    for col in list(empty.columns):
        store.delete_column(empty.slug, col)
    kanban = store.create_board("K")
    card = store.add_card(kanban.slug, "x", "Todo")
    with pytest.raises(ValueError):
        store.move_card_to_board(kanban.slug, card.id, empty.slug)


# ---- labels and priorities --------------------------------------------------------------------

def test_add_update_delete_label(store):
    b = store.create_board("B")
    label = store.add_label(b.slug, "Urgent", "red")
    assert store.list_labels(b.slug) == [label]
    updated = store.update_label(b.slug, label["id"], "Urgent!", "orange")
    assert updated["name"] == "Urgent!" and updated["color"] == "orange"
    assert store.list_labels(b.slug) == [updated]
    store.delete_label(b.slug, label["id"])
    assert store.list_labels(b.slug) == []


def test_delete_label_removes_it_from_every_card(store):
    b = store.create_board("B")
    label = store.add_label(b.slug, "Urgent", "red")
    c1 = store.add_card(b.slug, "a", "Todo", labels=[label["id"]])
    c2 = store.add_card(b.slug, "b", "Todo", labels=[label["id"]])
    store.delete_label(b.slug, label["id"])
    assert store.get_card(b.slug, c1.id).labels == [] and store.get_card(b.slug, c2.id).labels == []


def test_add_label_rejects_duplicate_or_bad_color(store):
    b = store.create_board("B")
    store.add_label(b.slug, "Urgent", "red")
    with pytest.raises(ValueError):
        store.add_label(b.slug, "urgent", "blue")   # duplicate, case-insensitive
    with pytest.raises(ValueError):
        store.add_label(b.slug, "Later", "not-a-color")


def test_add_label_caps_at_max(store, monkeypatch):
    import kanban.labels as L
    monkeypatch.setattr(L, "MAX_LABELS", 2)
    b = store.create_board("B")
    store.add_label(b.slug, "one", "red")
    store.add_label(b.slug, "two", "blue")
    with pytest.raises(ValueError):
        store.add_label(b.slug, "three", "green")


def test_card_labels_and_priority_persist(store):
    b = store.create_board("B")
    label = store.add_label(b.slug, "Urgent", "red")
    card = store.add_card(b.slug, "x", "Todo", labels=[label["id"]], priority="high")
    reloaded = store.get_card(b.slug, card.id)
    assert reloaded.labels == [label["id"]] and reloaded.priority == "high"


def test_unknown_label_ids_and_priorities_are_dropped(store):
    b = store.create_board("B")
    card = store.add_card(b.slug, "x", "Todo", labels=["forged"], priority="urgent-ish")
    reloaded = store.get_card(b.slug, card.id)
    assert reloaded.labels == [] and reloaded.priority is None


def test_update_card_labels_and_priority(store):
    b = store.create_board("B")
    label = store.add_label(b.slug, "Urgent", "red")
    card = store.add_card(b.slug, "x", "Todo")
    store.update_card(b.slug, card.id, "x", "", None, labels=[label["id"]], priority="low")
    reloaded = store.get_card(b.slug, card.id)
    assert reloaded.labels == [label["id"]] and reloaded.priority == "low"


# ---- archive/unarchive boards -----------------------------------------------------------------

def test_archive_and_unarchive_a_board(store):
    b = store.create_board("B")
    assert store.get_board(b.slug).archived is False
    store.archive_board(b.slug)
    assert store.get_board(b.slug).archived is True
    assert [x.slug for x in store.list_archived_boards()] == [b.slug]
    store.unarchive_board(b.slug)
    assert store.get_board(b.slug).archived is False
    assert store.list_archived_boards() == []


def test_archiving_leaves_everything_else_alone(store):
    """Archiving is a visibility toggle, not a lock: position, area, rules and cards survive."""
    store.add_area("Home")
    b = store.create_board("B")
    store.apply_layout(["Home"], {"Home": [b.slug]})
    card = store.add_card(b.slug, "still here", "Todo")
    store.archive_board(b.slug)
    reloaded = store.get_board(b.slug)
    assert reloaded.area == "Home" and reloaded.columns == b.columns
    assert store.get_card(b.slug, card.id).title == "still here"
    assert store.add_card(b.slug, "can still add cards", "Todo")  # not locked


def test_archived_boards_are_excluded_from_active_surfaces(store):
    b = store.create_board("B")
    store.add_card(b.slug, "hideme", "Todo", due="2026-10-01")
    store.archive_board(b.slug)
    assert store.sidebar()["unassigned"] == []
    assert store.all_cards() == []
    assert store.search("hideme") == []
    assert store.scheduled_cards() == []
    # still fully reachable directly, and list_boards() still sees it (area/layout/trash need to)
    assert store.get_board(b.slug).title == "B"
    assert b.slug in {x.slug for x in store.list_boards()}


# ---- CSV import -----------------------------------------------------------------------------

def _row(**over):
    row = {"title": "x", "list": "", "start": None, "due": None, "tags": [],
           "priority": None, "notes": "", "done": False}
    row.update(over)
    return row


def test_import_creates_cards_in_existing_columns(store):
    b = store.create_board("B", ["Todo", "Doing"])
    created, errors = store.import_cards(b.slug, [_row(title="a", list="Todo"), _row(title="b", list="Doing")])
    assert created == 2 and errors == []
    cols = store.cards_by_column(b.slug)
    assert [c.title for c in cols["Todo"]] == ["a"] and [c.title for c in cols["Doing"]] == ["b"]


def test_import_creates_missing_columns(store):
    b = store.create_board("B", ["Todo"])
    created, errors = store.import_cards(b.slug, [_row(title="a", list="Someday")])
    assert created == 1 and errors == []
    assert "Someday" in store.get_board(b.slug).columns
    assert store.cards_by_column(b.slug)["Someday"][0].title == "a"


def test_import_column_match_is_case_insensitive(store):
    b = store.create_board("B", ["Todo"])
    created, errors = store.import_cards(b.slug, [_row(title="a", list="todo")])
    assert created == 1 and errors == []
    assert store.get_board(b.slug).columns == ["Todo"]  # no duplicate "todo" column created
    assert store.cards_by_column(b.slug)["Todo"][0].title == "a"


def test_import_with_no_list_uses_first_visible_column(store):
    b = store.create_board("B", ["Todo", "Doing"])
    store.set_column_hidden(b.slug, "Todo", True)
    created, errors = store.import_cards(b.slug, [_row(title="a")])
    assert created == 1 and errors == []
    assert store.cards_by_column(b.slug)["Doing"][0].title == "a"


def test_import_into_a_tasks_board_ignores_list(store):
    b = store.create_board("B", kind="tasks")
    created, errors = store.import_cards(b.slug, [_row(title="a", list="Ignored")])
    assert created == 1 and errors == []
    assert store.cards_by_column(b.slug)["Tasks"][0].title == "a"


def test_import_sets_dates_tags_priority_notes_and_done(store):
    b = store.create_board("B", ["Todo"])
    row = _row(title="a", list="Todo", due="2026-10-01", start="2026-09-25",
               tags=["home"], priority="high", notes="body text", done=True)
    created, errors = store.import_cards(b.slug, [row])
    assert created == 1 and errors == []
    card = store.cards_by_column(b.slug)["Todo"][0]
    assert (card.due, card.start, card.tags, card.priority, card.body, card.done) == (
        "2026-10-01", "2026-09-25", ["home"], "high", "body text", True)


def test_import_one_bad_row_does_not_abort_the_rest(store):
    b = store.create_board("B")
    for col in list(b.columns):
        store.delete_column(b.slug, col)  # now genuinely has no lists at all
    rows = [_row(title="a"), _row(title="b")]
    created, errors = store.import_cards(b.slug, rows)
    assert created == 0
    assert len(errors) == 2 and all("no lists" in e for e in errors)


# ---- board created/updated timestamps (sidebar sort) -----------------------------------------

def test_created_is_set_once_and_never_changes(store):
    b = store.create_board("B")
    assert b.created is not None
    original = store.get_board(b.slug).created
    store.rename_board(b.slug, "New name")
    assert store.get_board(b.slug).created == original


def test_updated_reflects_board_md_mtime(store, tmp_path):
    b = store.create_board("B")
    path = tmp_path / b.slug / "board.md"
    old = time.time() - 120  # back-date first, so a real (not flaky, sub-second) gap shows up
    os.utime(path, (old, old))
    first = store.get_board(b.slug).updated
    assert first is not None
    store.rename_board(b.slug, "New name")  # re-saves board.md -> mtime jumps back to "now"
    assert store.get_board(b.slug).updated > first


def test_adding_a_card_touches_the_board_as_updated(store, tmp_path):
    b = store.create_board("B")
    path = tmp_path / b.slug / "board.md"
    old = time.time() - 120
    os.utime(path, (old, old))
    before = store.get_board(b.slug).updated
    store.add_card(b.slug, "x", "Todo")
    assert store.get_board(b.slug).updated > before


# ---- pinning boards ----------------------------------------------------------------------------

def test_set_pinned_toggles_and_persists(store):
    b = store.create_board("B")
    assert b.pinned is False
    store.set_pinned(b.slug, True)
    assert store.get_board(b.slug).pinned is True
    store.set_pinned(b.slug, False)
    assert store.get_board(b.slug).pinned is False


def test_pinned_boards_sort_first_in_the_sidebar(store):
    a = store.create_board("Alpha")
    z = store.create_board("Zulu")
    m = store.create_board("Mid")
    store.set_pinned(m.slug, True)
    order = [b.slug for b in store.sidebar()["unassigned"]]
    assert order == [m.slug, a.slug, z.slug]  # pinned first, then creation/position order


def test_pinned_boards_sort_first_within_their_own_area(store):
    store.add_area("Home")
    a = store.create_board("A")
    b = store.create_board("B")
    store.apply_layout(["Home"], {"Home": [a.slug, b.slug]})
    store.set_pinned(b.slug, True)
    order = [x.slug for x in dict(store.sidebar()["areas"])["Home"]]
    assert order == [b.slug, a.slug]


def test_unpinning_returns_a_board_to_its_position_order(store):
    a = store.create_board("A")
    b = store.create_board("B")
    store.set_pinned(b.slug, True)
    assert [x.slug for x in store.sidebar()["unassigned"]] == [b.slug, a.slug]
    store.set_pinned(b.slug, False)
    assert [x.slug for x in store.sidebar()["unassigned"]] == [a.slug, b.slug]


# ---- concurrent read/write safety (the sidebar's stats fetch races card writes constantly) -----

def test_reading_cards_while_writing_never_sees_a_half_written_file(store):
    """Regression: write_md() used to write straight to the target path, so a read landing between
    the truncate and the new content finishing could see an empty/partial file and crash with a
    KeyError on a required field (id/title/column). Hit for real by an e2e run where /sidebar/stats
    raced a card save. write_md is now write-to-temp + atomic rename; this drives the same race
    directly, many times, to prove a reader never sees anything but a fully-formed file."""
    import threading

    b = store.create_board("B")
    card = store.add_card(b.slug, "x", "Todo")
    stop = threading.Event()
    errors = []

    def writer():
        i = 0
        while not stop.is_set():
            try:
                store.update_card(b.slug, card.id, f"x{i}", "", None)
            except Exception as exc:  # noqa: BLE001 - anything here is the bug under test
                errors.append(exc)
                return
            i += 1

    def reader():
        while not stop.is_set():
            try:
                store.list_cards(b.slug)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)
                return

    threads = [threading.Thread(target=writer), *(threading.Thread(target=reader) for _ in range(3))]
    for t in threads:
        t.start()
    stop.wait(0.5)
    stop.set()
    for t in threads:
        t.join()
    assert errors == []


# ---- saved searches ---------------------------------------------------------------------------

def test_save_search_stores_criteria_and_defaults_unpinned(store):
    entry = store.save_search("Home tasks", {"q": "", "tags": ["home"], "priority": [], "board": [], "status": []})
    assert entry["name"] == "Home tasks" and entry["tags"] == ["home"] and entry["pinned"] is False
    assert store.list_searches() == [entry]


def test_save_search_rejects_a_blank_name(store):
    with pytest.raises(ValueError):
        store.save_search("   ", {"q": "x"})


def test_update_search_replaces_criteria_keeps_id_name_and_pin(store):
    entry = store.save_search("Home", {"q": "", "tags": ["home"]})
    store.set_search_pinned(entry["id"], True)
    updated = store.update_search(entry["id"], {"q": "paint", "tags": ["home", "diy"]})
    assert updated["id"] == entry["id"] and updated["name"] == "Home"
    assert updated["q"] == "paint" and updated["tags"] == ["home", "diy"]
    assert updated["pinned"] is True


def test_rename_search(store):
    entry = store.save_search("Home", {"q": ""})
    renamed = store.rename_search(entry["id"], "  Home stuff  ")
    assert renamed["name"] == "Home stuff"
    with pytest.raises(ValueError):
        store.rename_search(entry["id"], "   ")


def test_duplicate_search_gets_a_new_id_and_copy_suffix_and_starts_unpinned(store):
    entry = store.save_search("Home", {"q": "", "tags": ["home"]})
    store.set_search_pinned(entry["id"], True)
    copy = store.duplicate_search(entry["id"])
    assert copy["id"] != entry["id"]
    assert copy["name"] == "Home (copy)"
    assert copy["tags"] == ["home"]
    assert copy["pinned"] is False                  # the original's pin doesn't carry over
    assert len(store.list_searches()) == 2


def test_set_search_pinned_toggles(store):
    entry = store.save_search("Home", {"q": ""})
    store.set_search_pinned(entry["id"], True)
    assert store.list_searches()[0]["pinned"] is True
    store.set_search_pinned(entry["id"], False)
    assert store.list_searches()[0]["pinned"] is False


def test_delete_search_removes_it(store):
    entry = store.save_search("Home", {"q": ""})
    store.delete_search(entry["id"])
    assert store.list_searches() == []


def test_search_actions_on_an_unknown_id_raise_keyerror(store):
    with pytest.raises(KeyError):
        store.update_search("nope", {"q": "x"})
    with pytest.raises(KeyError):
        store.rename_search("nope", "x")
    with pytest.raises(KeyError):
        store.duplicate_search("nope")
    with pytest.raises(KeyError):
        store.set_search_pinned("nope", True)
    with pytest.raises(KeyError):
        store.delete_search("nope")


def test_set_starred_toggles_and_persists(store, tmp_path):
    b = store.create_board("B")
    card = store.add_card(b.slug, "a", "Todo")
    assert card.starred is False
    store.set_starred(b.slug, card.id, True)
    assert store.get_card(b.slug, card.id).starred is True
    text = (tmp_path / b.slug / "cards" / f"{card.id}.md").read_text()
    assert "starred: true" in text
    store.set_starred(b.slug, card.id, False)
    assert store.get_card(b.slug, card.id).starred is False


def test_set_starred_missing_card_raises_keyerror(store):
    b = store.create_board("B")
    with pytest.raises(KeyError):
        store.set_starred(b.slug, "nope", True)


def test_standup_exclusions_round_trip(store):
    b = store.create_board("B")
    card = store.add_card(b.slug, "a", "Todo")
    assert store.list_standup_exclusions() == []
    entry = store.exclude_from_standup(b.slug, card.id, until=None)
    assert entry == {"board": b.slug, "card": card.id, "until": None}
    assert store.list_standup_exclusions() == [entry]


def test_exclude_from_standup_replaces_a_prior_exclusion_for_the_same_card(store):
    b = store.create_board("B")
    card = store.add_card(b.slug, "a", "Todo")
    store.exclude_from_standup(b.slug, card.id, until="2026-09-25")
    store.exclude_from_standup(b.slug, card.id, until=None)
    exclusions = store.list_standup_exclusions()
    assert len(exclusions) == 1
    assert exclusions[0]["until"] is None


def test_exclude_from_standup_missing_card_raises_keyerror(store):
    b = store.create_board("B")
    with pytest.raises(KeyError):
        store.exclude_from_standup(b.slug, "nope", until=None)


def test_include_in_standup_removes_the_exclusion(store):
    b = store.create_board("B")
    card = store.add_card(b.slug, "a", "Todo")
    store.exclude_from_standup(b.slug, card.id, until=None)
    store.include_in_standup(card.id)
    assert store.list_standup_exclusions() == []


def test_include_in_standup_on_an_unexcluded_card_is_a_no_op(store):
    b = store.create_board("B")
    store.create_board("Other")
    store.add_card(b.slug, "a", "Todo")
    store.include_in_standup("nope")
    assert store.list_standup_exclusions() == []
