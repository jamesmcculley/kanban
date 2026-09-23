"""Pure aggregation over Logbook events -- see kanban/metrics.py."""

from kanban import metrics as M


def _event(board_title, list_name, at, repeat=False):
    e = {"at": at, "title": "x", "board_title": board_title, "list": list_name}
    if repeat:
        e["repeat"] = True
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
    assert rows[0] == "completed_at,title,board,list,repeating"
    assert rows[1].startswith("2026-09-01T08:00")   # oldest first, despite input order
    assert rows[1].endswith("yes")
    assert rows[2].startswith("2026-09-02T09:00") and rows[2].endswith(",")


def test_to_csv_empty():
    assert M.to_csv([]) == "completed_at,title,board,list,repeating\r\n"
