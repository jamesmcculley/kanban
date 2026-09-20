from datetime import date

import pytest

from kanban.dates import (
    first_due,
    next_occurrence,
    parse_due,
    parse_repeat,
    split_due,
    split_repeat,
)

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




@pytest.mark.parametrize("text,expected", [
    ("daily", "every day"), ("Every Day", "every day"), ("weekly", "every week"),
    ("every 2 weeks", "every 2 weeks"), ("every 1 month", "every month"),
    ("every mon", "every monday"), ("every weekday", "every weekday"),
])
def test_parse_repeat(text, expected):
    assert parse_repeat(text) == expected


@pytest.mark.parametrize("text", ["every", "every 0 days", "every funday", "sometimes"])
def test_parse_repeat_rejects(text):
    assert parse_repeat(text) is None


def test_split_repeat():
    assert split_repeat("Water plants every monday") == ("Water plants", "every monday")
    assert split_repeat("Stretch daily") == ("Stretch", "every day")
    assert split_repeat("every monday") == ("every monday", None)


def test_first_due():
    assert first_due("every wednesday", WED) == WED               # today fits
    assert first_due("every friday", WED) == date(2026, 9, 18)
    assert first_due("every weekday", date(2026, 9, 19)) == date(2026, 9, 21)  # Sat -> Mon
    assert first_due("every 2 weeks", WED) == WED


def test_next_occurrence_weekday():
    assert next_occurrence("every monday", date(2026, 9, 14), WED) == date(2026, 9, 21)
    # finished early: due Fri, done Wed -> the Friday after, not the same Friday
    assert next_occurrence("every friday", date(2026, 9, 18), WED) == date(2026, 9, 25)
    assert next_occurrence("every weekday", date(2026, 9, 18), date(2026, 9, 18)) == date(2026, 9, 21)


def test_next_occurrence_interval_keeps_schedule():
    # biweekly on Mondays, finished late on Wed: stays on the Monday grid
    assert next_occurrence("every 2 weeks", date(2026, 9, 14), WED) == date(2026, 9, 28)
    # very overdue: skips missed occurrences
    assert next_occurrence("every day", date(2026, 9, 1), WED) == date(2026, 9, 17)
    assert next_occurrence("every day", None, WED) == date(2026, 9, 17)


def test_next_occurrence_month_clamps():
    assert next_occurrence("every month", date(2026, 1, 31), date(2026, 1, 31)) == date(2026, 2, 28)
    assert next_occurrence("every month", date(2026, 1, 31), date(2026, 3, 1)) == date(2026, 3, 31)
