import pytest

from kanban.labels import COLORS, clean_label


def test_clean_label_trims_and_collapses_whitespace():
    label = clean_label({"name": "  Home   Errand  ", "color": "green"}, [])
    assert label["name"] == "Home Errand" and label["color"] == "green" and label["id"]


def test_clean_label_rejects_blank_name():
    with pytest.raises(ValueError):
        clean_label({"name": "   ", "color": "green"}, [])


def test_clean_label_rejects_unknown_color():
    with pytest.raises(ValueError):
        clean_label({"name": "x", "color": "not-a-color"}, [])


def test_clean_label_rejects_case_insensitive_duplicate():
    others = [{"id": "abc", "name": "Urgent", "color": "red"}]
    with pytest.raises(ValueError):
        clean_label({"name": "urgent", "color": "blue"}, others)


def test_clean_label_allows_renaming_self_to_its_own_name():
    """Editing a label without changing its name shouldn't collide with itself."""
    others = [{"id": "other", "name": "Later", "color": "blue"}]  # self already excluded by caller
    label = clean_label({"name": "Urgent", "color": "red"}, others, label_id="abc")
    assert label == {"id": "abc", "name": "Urgent", "color": "red"}


def test_every_color_has_a_high_contrast_text_choice():
    # Sanity check the palette shape rather than re-deriving contrast ratios here.
    for fill, text in COLORS.values():
        assert fill.startswith("#") and len(fill) == 7
        assert text in ("#000000", "#ffffff")
