"""Pure aggregation over Logbook events -- see kanban/metrics.py."""

from kanban import metrics as M


def _event(board_title, list_name, at, repeat=False, board=None, tags=None, priority=None):
    e = {"at": at, "title": "x", "board": board or board_title.lower(), "board_title": board_title,
        "list": list_name}
    if repeat:
        e["repeat"] = True
    if tags:
        e["tags"] = tags
    if priority:
        e["priority"] = priority
    return e


def test_by_board_counts_and_sorts_busiest_first():
    events = [_event("A", "Todo", "2026-09-01T09:00")] * 3 + [_event("B", "Todo", "2026-09-01T09:00")]
    assert M.by_board(events) == [("A", 3), ("B", 1)]


def test_by_board_empty():
    assert M.by_board([]) == []


def test_by_weekday_always_returns_all_seven_days_with_zeros():
    # 2026-09-14 is a Monday.
    events = [_event("A", "Todo", "2026-09-14T09:00"), _event("A", "Todo", "2026-09-14T18:00")]
    result = M.by_weekday(events)
    assert [name for name, _ in result] == M.WEEKDAYS
    assert dict(result) == {"Monday": 2, "Tuesday": 0, "Wednesday": 0, "Thursday": 0,
                            "Friday": 0, "Saturday": 0, "Sunday": 0}


def test_to_csv_is_oldest_first_and_includes_repeat_flag():
    events = [_event("A", "Todo", "2026-09-02T09:00"), _event("A", "Doing", "2026-09-01T08:00", repeat=True)]
    rows = M.to_csv(events).splitlines()
    assert rows[0] == "completed_at,title,board,list,priority,tags,repeating"
    assert rows[1].startswith("2026-09-01T08:00")   # oldest first, despite input order
    assert rows[1].endswith("yes")
    assert rows[2].startswith("2026-09-02T09:00") and rows[2].endswith(",")


def test_to_csv_includes_priority_and_tags_columns():
    events = [_event("A", "Todo", "2026-09-01T09:00", tags=["home", "urgent"], priority="high")]
    rows = M.to_csv(events).splitlines()
    assert rows[1] == "2026-09-01T09:00,x,A,Todo,high,home urgent,"


def test_to_csv_empty():
    assert M.to_csv([]) == "completed_at,title,board,list,priority,tags,repeating\r\n"


# ---- filter_events ----------------------------------------------------------------------------

def test_filter_events_with_nothing_set_matches_everything():
    events = [_event("A", "Todo", "2026-09-01T09:00"), _event("B", "Todo", "2026-09-02T09:00")]
    assert M.filter_events(events) == events


def test_filter_events_by_text_is_case_insensitive_title_substring():
    events = [{**_event("A", "Todo", "2026-09-01T09:00"), "title": "Buy Paint"},
              {**_event("A", "Todo", "2026-09-02T09:00"), "title": "Mow lawn"}]
    assert [e["title"] for e in M.filter_events(events, q="paint")] == ["Buy Paint"]


def test_filter_events_by_tags_is_any_match_and_excludes_untagged():
    events = [_event("A", "Todo", "2026-09-01T09:00", tags=["home"]),
              _event("A", "Todo", "2026-09-02T09:00", tags=["work"]),
              _event("A", "Todo", "2026-09-03T09:00")]                   # never logged a tag
    assert len(M.filter_events(events, tags=["home", "errand"])) == 1


def test_filter_events_by_priority_none_bucket_covers_missing_and_explicit_none():
    events = [_event("A", "Todo", "2026-09-01T09:00", priority="high"),
              _event("A", "Todo", "2026-09-02T09:00")]                   # no priority ever logged
    assert len(M.filter_events(events, priorities=["none"])) == 1
    assert len(M.filter_events(events, priorities=["high"])) == 1


def test_filter_events_by_board():
    events = [_event("A", "Todo", "2026-09-01T09:00", board="a"),
              _event("B", "Todo", "2026-09-02T09:00", board="b")]
    assert [e["board"] for e in M.filter_events(events, boards=["b"])] == ["b"]


def test_filter_events_combines_all_filters_with_and():
    events = [_event("A", "Todo", "2026-09-01T09:00", board="a", tags=["home"], priority="high"),
              _event("A", "Todo", "2026-09-02T09:00", board="a", tags=["home"], priority="low")]
    result = M.filter_events(events, tags=["home"], priorities=["high"], boards=["a"])
    assert len(result) == 1 and result[0]["at"] == "2026-09-01T09:00"
