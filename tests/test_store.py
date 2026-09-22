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
