from datetime import date

import pytest

from kanban.dates import parse_due, split_due

WED = date(2026, 9, 16)  # a Wednesday


@pytest.mark.parametrize("text,expected", [
    ("today", date(2026, 9, 16)),
    ("tomorrow", date(2026, 9, 17)),
    ("friday", date(2026, 9, 18)),
    ("wed", date(2026, 9, 23)),          # same weekday -> next week
    ("next mon", date(2026, 9, 21)),
    ("next fri", date(2026, 9, 25)),
    ("in 3 days", date(2026, 9, 19)),
    ("in 2 weeks", date(2026, 9, 30)),
    ("oct 5", date(2026, 10, 5)),
    ("jan 2", date(2027, 1, 2)),          # already passed -> next year
    ("2026-12-25", date(2026, 12, 25)),
])
def test_parse_due(text, expected):
    assert parse_due(text, WED) == expected


@pytest.mark.parametrize("text", ["someday", "feb 31", "2026-13-01", ""])
def test_parse_due_rejects(text):
    assert parse_due(text, WED) is None


def test_split_due():
    assert split_due("Buy paint tomorrow", WED) == ("Buy paint", date(2026, 9, 17))
    assert split_due("Call mum on friday", WED) == ("Call mum on", date(2026, 9, 18))
    assert split_due("tomorrow", WED) == ("tomorrow", None)  # never leave an empty title
    assert split_due("Plan trip", WED) == ("Plan trip", None)
