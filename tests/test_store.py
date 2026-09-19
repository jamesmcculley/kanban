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
    assert [(bd.slug, cd.title, cd.due) for bd, cd in store.dated_cards()] == [
        ("b", "renamed", "2026-10-01")]
    assert store.get_card(b.slug, c.id).body.strip() == "notes"


def test_hand_edited_unquoted_date(store, tmp_path):
    b = store.create_board("B")
    c = store.add_card(b.slug, "x", "Todo")
    path = tmp_path / b.slug / "cards" / f"{c.id}.md"
    path.write_text(path.read_text().replace("position: 0", "position: 0\ndue: 2026-10-01"))
    assert store.get_card(b.slug, c.id).due == "2026-10-01"
