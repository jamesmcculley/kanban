from dataclasses import dataclass, field
from datetime import date

from kanban.csvimport import cards_to_csv, parse_csv


def test_parses_a_full_row():
    csv_text = "title,list,due,start,tags,priority,notes,done\n" \
               "Buy paint,Todo,2026-10-01,2026-09-25,home errand,high,Get primer too,\n"
    rows, errors = parse_csv(csv_text)
    assert errors == []
    assert rows == [{
        "title": "Buy paint", "list": "Todo", "due": "2026-10-01", "start": "2026-09-25",
        "tags": ["home", "errand"], "priority": "high", "notes": "Get primer too", "done": False,
    }]


def test_only_title_is_required():
    rows, errors = parse_csv("title\nJust a title\n")
    assert errors == []
    assert rows[0]["title"] == "Just a title"
    assert rows[0]["list"] == "" and rows[0]["due"] is None and rows[0]["tags"] == []


def test_name_and_column_and_body_are_accepted_aliases():
    rows, errors = parse_csv("name,column,body\nFix bug,Doing,Notes here\n")
    assert errors == []
    assert rows[0]["title"] == "Fix bug" and rows[0]["list"] == "Doing" and rows[0]["notes"] == "Notes here"


def test_missing_title_is_reported_and_skipped():
    rows, errors = parse_csv("title,list\n,Todo\nReal one,Todo\n")
    assert [r["title"] for r in rows] == ["Real one"]
    assert "row 2" in errors[0] and "no title" in errors[0]


def test_unparseable_date_is_reported_not_fatal():
    rows, errors = parse_csv("title,due\nSomething,not a date\n")
    assert rows[0]["due"] is None
    assert any("couldn't understand due date" in e for e in errors)


def test_natural_language_due_date_resolves_relative_to_today():
    rows, _ = parse_csv("title,due\nx,tomorrow\n")
    from datetime import timedelta
    assert rows[0]["due"] == (date.today() + timedelta(days=1)).isoformat()


def test_done_column_recognizes_common_truthy_spellings():
    for value in ("yes", "TRUE", "1", "x", "Completed"):
        rows, _ = parse_csv(f"title,done\nx,{value}\n")
        assert rows[0]["done"] is True, value
    for value in ("no", "false", "0", ""):
        rows, _ = parse_csv(f"title,done\nx,{value}\n")
        assert rows[0]["done"] is False, value


def test_empty_file_reports_an_error():
    rows, errors = parse_csv("")
    assert rows == [] and errors == ["The file has no header row."]


def test_unknown_columns_are_ignored_not_an_error():
    rows, errors = parse_csv("title,some_other_tool_column\nx,whatever\n")
    assert errors == [] and rows[0]["title"] == "x"


# ---- cards_to_csv (export) ---------------------------------------------------------------------

@dataclass
class _Board:
    title: str


@dataclass
class _Card:
    title: str
    column: str = "Todo"
    start: str | None = None
    due: str | None = None
    tags: list = field(default_factory=list)
    priority: str | None = None
    body: str = ""
    done: bool = False


def test_cards_to_csv_matches_the_columns_parse_csv_reads():
    results = [(_Board("My Board"), _Card("Buy paint", tags=["home"], priority="high", due="2026-10-01"))]
    out = cards_to_csv(results)
    lines = out.splitlines()
    assert lines[0] == "title,board,list,start,due,tags,priority,notes,done"
    assert lines[1] == "Buy paint,My Board,Todo,,2026-10-01,home,high,,"

    # round trips: export -> parse_csv reads the same shape back out
    rows, errors = parse_csv(out)
    assert errors == []
    assert rows[0]["title"] == "Buy paint" and rows[0]["tags"] == ["home"] and rows[0]["priority"] == "high"


def test_cards_to_csv_done_flag():
    out = cards_to_csv([(_Board("B"), _Card("x", done=True))])
    assert out.splitlines()[1].endswith(",yes")


def test_cards_to_csv_with_sections_adds_a_leading_column():
    results = [(_Board("B"), _Card("due card")), (_Board("B"), _Card("created card"))]
    out = cards_to_csv(results, sections=["due", "created"])
    lines = out.splitlines()
    assert lines[0].startswith("section,title,")
    assert lines[1].startswith("due,due card,")
    assert lines[2].startswith("created,created card,")


def test_cards_to_csv_empty():
    assert cards_to_csv([]) == "title,board,list,start,due,tags,priority,notes,done\r\n"
