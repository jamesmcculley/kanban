import json
from datetime import date, datetime, timedelta
from urllib.parse import urlencode

from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    url_for,
)

from . import csvimport, notes
from . import labels as L
from . import metrics as M
from . import review as RV
from . import rules as R
from . import search as SR
from . import settings as S
from .dates import first_due, parse_due, parse_iso_range, parse_repeat, split_due, split_repeat
from .store import PRIORITIES, TASKS_COLUMN, effective_date
from .tags import parse_tags, split_tags
from .themes import TEXT_SIZES, THEME_NAMES, theme_cards

bp = Blueprint("boards", __name__)


def store():
    return current_app.config["STORE"]


def _short(text: str, n: int = 40) -> str:
    return text if len(text) <= n else text[: n - 1] + "…"


def _toast(message: str, undo: dict | None = None, later: bool = False) -> dict:
    """What the browser shows in the toast bar. `undo` = {url, method?, body?}."""
    toast = {"message": message}
    if undo:
        toast["undo"] = undo
    if later:
        toast["later"] = True  # the page is about to reload: show it afterwards
    return toast


def _with_toast(resp, toast: dict | None):
    if toast:  # ascii-only JSON: HTTP header values must be latin-1 safe
        resp.headers["HX-Trigger"] = json.dumps({"toast": toast})
    return resp


def _parse_quick(raw: str):
    """'Call mum tomorrow #home every friday' -> title, due (iso), repeat rule, tags."""
    title, tags = split_tags(raw)
    title, rule = split_repeat(title)
    title, due = split_due(title)
    if rule and not due:
        due = first_due(rule)
    return title, (due.isoformat() if due else None), rule, tags


def _search_run_url(entry: dict) -> str:
    """A saved search's own URL always carries `edit=<id>` -- opening Advanced Search from it
    shows an "Update" button (in place of "Save") the moment you change anything, rather than
    needing a separate edit mode. Used for both the Search page's saved-search chips and the
    sidebar's pinned ones."""
    params = [("q", entry["q"])] if entry.get("q") else []
    if entry.get("tags"):
        params.append(("tags", " ".join(entry["tags"])))
    params += [("priority", p) for p in entry.get("priority") or []]
    params += [("board", b) for b in entry.get("board") or []]
    params += [("status", s) for s in entry.get("status") or []]
    params.append(("edit", entry["id"]))
    return f"{url_for('boards.search')}?{urlencode(params)}"


def _search_criteria_from(args) -> dict:
    """`args`: request.args (GET, for /search itself) or request.form (POST, for saving/updating
    a saved search) -- both support .get()/.getlist(), so one helper covers both."""
    return {"q": args.get("q", "").strip(), "tags": parse_tags(args.get("tags", "")),
            "priority": args.getlist("priority"), "board": args.getlist("board"),
            "status": args.getlist("status")}


@bp.app_context_processor
def nav():
    today = date.today().isoformat()
    due_now = len(store().scheduled_cards(date_to=today))
    current = (request.view_args or {}).get("slug") if request.endpoint == "boards.board" else None
    card_boards = [b for b in store().list_boards()
                   if b.kind in ("kanban", "tasks") and b.parent is None and not b.archived]
    pinned_searches = [{**s, "url": _search_run_url(s)} for s in store().list_searches() if s.get("pinned")]
    return {"sidebar": store().sidebar(), "tags": store().tag_counts(), "today": today,
            "today_count": due_now, "current_board": current, "card_boards": card_boards,
            "theme_names": THEME_NAMES, "text_sizes": TEXT_SIZES, "pinned_searches": pinned_searches,
            "auth_enabled": bool(current_app.config.get("PASSWORD"))}


@bp.get("/")
def index():
    boards = [b for b in store().list_boards() if b.parent is None]
    if not boards:
        boards = [store().create_board("My Board")]
    return redirect(url_for("boards.board", slug=boards[0].slug))


@bp.post("/boards")
def create_board():
    title = request.form.get("title", "").strip()
    if not title:
        abort(400)
    try:
        board = store().create_board(title, kind=request.form.get("kind", "kanban"))
    except ValueError:
        abort(400)
    return redirect(url_for("boards.board", slug=board.slug))


def _importable_boards():
    return [b for b in store().list_boards() if b.kind in ("kanban", "tasks") and b.parent is None]


@bp.get("/import")
def import_csv():
    return render_template("import.html", card_boards=_importable_boards())


@bp.get("/import/example.csv")
def import_example_csv():
    return Response(csvimport.EXAMPLE_CSV, mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=example.csv"})


@bp.post("/import")
def do_import():
    file = request.files.get("file")
    if not file or not file.filename:
        return render_template("import.html", error="Choose a CSV file first.",
                               card_boards=_importable_boards()), 400
    try:
        text = file.read().decode("utf-8-sig")  # -sig: Excel/Numbers often add a BOM
    except UnicodeDecodeError:
        return render_template("import.html", error="That doesn't look like a text CSV file.",
                               card_boards=_importable_boards()), 400
    rows, parse_errors = csvimport.parse_csv(text)

    target = request.form.get("target")
    if target == "existing":
        slug = request.form.get("existing_slug", "")
        try:
            board = store().get_board(slug)
        except KeyError:
            abort(400)
    else:
        title = request.form.get("new_title", "").strip() or "Imported"
        kind = request.form.get("new_kind", "kanban")
        try:
            board = store().create_board(title, kind=kind)
        except ValueError:
            abort(400)

    created, import_errors = store().import_cards(board.slug, rows)
    return render_template("import_result.html", board=board, created=created,
                           errors=parse_errors + import_errors, total=len(rows))


@bp.get("/b/<slug>")
def board(slug):
    try:
        b = store().get_board(slug)
    except KeyError:
        abort(404)
    parent = store().get_board(b.parent) if b.parent else None
    display = store().settings_for(slug)
    if b.kind == "tasks":
        cards, hidden_done = store().view_columns(slug)
        cards = cards.get(TASKS_COLUMN, [])
        return render_template("tasks.html", board=b, parent=parent, cards=cards,
                               hidden_done=hidden_done, hidden_cards=store().hidden_cards(slug),
                               new_top=display["new_card_position"] == "top",
                               display=display, labels=store().list_labels(slug))
    columns, hidden_done = store().view_columns(slug)
    return render_template("board.html", board=b, parent=parent, columns=columns,
                           hidden_done=hidden_done, hidden_cards=store().hidden_cards(slug),
                           new_top=display["new_card_position"] == "top",
                           display=display, labels=store().list_labels(slug))


@bp.get("/b/<slug>/export/dialog")
def board_export_dialog(slug):
    try:
        b = store().get_board(slug)
    except KeyError:
        abort(404)
    return render_template("_cards_export_dialog.html", action=url_for("boards.board_export", slug=slug),
                           title=b.title, boards=None, columns=b.columns, show_status=True, sections=None)


@bp.get("/b/<slug>/export.csv")
def board_export(slug):
    try:
        b = store().get_board(slug)
    except KeyError:
        abort(404)
    results = [(b, c) for c in store().list_cards(slug)]
    results = SR.refine(results, q=request.args.get("q", ""), tags=parse_tags(request.args.get("tags", "")),
                        priorities=request.args.getlist("priority"), lists=request.args.getlist("list"),
                        statuses=request.args.getlist("status"))
    resp = make_response(csvimport.cards_to_csv(results))
    resp.headers["Content-Type"] = "text/csv; charset=utf-8"
    resp.headers["Content-Disposition"] = f'attachment; filename="{slug}.csv"'
    return resp


@bp.post("/b/<slug>/cards")
def add_card(slug):
    title, due, rule, tags = _parse_quick(request.form.get("title", ""))
    if not title:
        abort(400)
    try:
        top = store().settings_for(slug)["new_card_position"] == "top"
        card = store().add_card(slug, title, request.form.get("column", ""), due, rule, tags,
                                top=top)
    except (KeyError, ValueError):
        abort(400)
    if card.effects:  # a rule changed the card (moved it, tagged it...): show the board as it is now
        return _with_toast(_refresh(), _toast(f"Added “{_short(card.title)}” · {'; '.join(card.effects)}",
                                              later=True))
    return render_template("_card.html", board=store().get_board(slug), card=card)


@bp.get("/b/<slug>/cards/<card_id>")
def edit_card(slug, card_id):
    # `standalone`: opened from a page that isn't the card's own board (Scheduled, Logbook) --
    # there's no `.card[data-id]` there for the save to swap in place (Scheduled's row markup
    # looks nothing like a board card, and Logbook has no live card markup at all), and an edited
    # due date can move a Scheduled card to a different day-group entirely. _edit.html reloads the
    # whole page on save in that case instead of trying to patch the DOM. See _edit.html's comment.
    try:
        return render_template("_edit.html", board=store().get_board(slug),
                               card=store().get_card(slug, card_id),
                               standalone=bool(request.args.get("standalone")))
    except KeyError:
        abort(404)


@bp.post("/b/<slug>/cards/<card_id>")
def update_card(slug, card_id):
    title = request.form.get("title", "").strip()
    raw_due = request.form.get("due", "").strip()
    due = parse_due(raw_due) if raw_due else None
    raw_start = request.form.get("start", "").strip()
    start = parse_due(raw_start) if raw_start else None
    raw_repeat = request.form.get("repeat", "").strip()
    rule = parse_repeat(raw_repeat) if raw_repeat else None
    priority = request.form.get("priority") or None
    if (not title or (raw_due and due is None) or (raw_start and start is None)
            or (raw_repeat and rule is None) or (priority and priority not in PRIORITIES)):
        abort(400)
    try:
        card = store().update_card(slug, card_id, title, request.form.get("body", ""),
                                   due.isoformat() if due else None, rule,
                                   parse_tags(request.form.get("tags", "")),
                                   start.isoformat() if start else None,
                                   request.form.getlist("labels"), priority)
    except KeyError:
        abort(404)
    return render_template("_card.html", board=store().get_board(slug), card=card)


@bp.post("/b/<slug>/cards/<card_id>/duplicate")
def duplicate_card(slug, card_id):
    """Reachable from the card-edit dialog, so from anywhere a card can be opened -- board,
    Scheduled, Logbook, Today, Search. `to`/`column`, if given (the same "Move to" picker's
    value), duplicate onto that board/list instead of right after the original. Undo just trashes
    the fresh copy (boards.delete_card), same as undoing any other new card."""
    dest_slug = request.form.get("to") or None
    dest_column = request.form.get("column") or None
    try:
        copy = store().duplicate_card(slug, card_id, dest_slug, dest_column)
    except KeyError:
        abort(404)
    except ValueError:
        abort(400)
    dest_slug = dest_slug or slug
    undo = {"url": url_for("boards.delete_card", slug=dest_slug, card_id=copy.id), "method": "DELETE"}
    message = f"Duplicated “{_short(copy.title)}”"
    if dest_slug != slug:
        try:
            message += f" to {store().get_board(dest_slug).title}"
        except KeyError:
            pass
    message += "".join(f" · {e}" for e in copy.effects)
    return jsonify(_toast(message, undo))


@bp.post("/b/<slug>/cards/<card_id>/star")
def toggle_star(slug, card_id):
    """Reachable from the card-edit dialog (anywhere) and from a row in Review mode itself."""
    try:
        card = store().get_card(slug, card_id)
        card = store().set_starred(slug, card_id, not card.starred)
    except KeyError:
        abort(404)
    return jsonify(starred=card.starred)


@bp.post("/b/<slug>/cards/<card_id>/hide")
def hide_card(slug, card_id):
    """Reachable from a card's own quick hide button, anywhere a card is shown (its board, Today,
    Scheduled, Logbook, Review), and from its own board's "Hidden cards" eye menu on the way back
    -- same shape as hiding/reviving a list, just per-card. Takes an explicit `hidden` value (not a
    toggle): the eye menu's checkboxes need to set a specific state, same as hide_column."""
    try:
        card = store().set_card_hidden(slug, card_id, request.form.get("hidden", "1") == "1")
    except KeyError:
        abort(404)
    return jsonify(hidden=card.hidden)


@bp.post("/b/<slug>/cards/<card_id>/complete")
def complete(slug, card_id):
    try:
        before = store().get_card(slug, card_id)
        card = store().complete_card(slug, card_id)
    except KeyError:
        abort(404)
    refresh = bool(request.args.get("refresh"))  # agenda/search rows: re-render the whole page
    changed = card.column != before.column or set(card.tags) != set(before.tags) or card.archived
    toast = None
    completion = before.repeat or (card.done and not before.done)  # a completion, not an un-check
    if completion:
        at = card.last_completed if before.repeat else card.completed
        undo = url_for("boards.undo_complete", slug=slug, card_id=card_id, at=at,
                       due=before.due or "", last=before.last_completed or "", col=before.column,
                       idx=before.position, tags=",".join(before.tags))
        message = f"Completed “{_short(card.title)}”"
        if before.repeat and card.due:
            message += f" · next {card.due}"
        toast = _toast(message + "".join(f" · {e}" for e in card.effects), {"url": undo},
                       later=refresh or changed)
    elif card.effects:
        toast = _toast(f"Un-checked “{_short(card.title)}”" + "".join(f" · {e}" for e in card.effects),
                       later=True)
    if refresh or changed:  # the card moved or was cleared: reload the board rather than patch it
        resp = _refresh()
        return _with_toast(resp, toast)
    resp = make_response(render_template("_card.html", board=store().get_board(slug), card=card))
    return _with_toast(resp, toast)


@bp.post("/b/<slug>/cards/<card_id>/undo-complete")
def undo_complete(slug, card_id):
    at = request.args.get("at", "")
    if not at:
        abort(400)
    try:
        store().undo_complete(slug, card_id, at, request.args.get("due") or None,
                              request.args.get("last") or None, request.args.get("col"),
                              int(request.args.get("idx") or 0), request.args.get("tags"))
    except KeyError:
        abort(404)
    except ValueError:
        abort(400)
    return "", 204


@bp.get("/b/<slug>/cards/<card_id>/body")
def card_body(slug, card_id):
    try:
        return store().get_card(slug, card_id).body, 200, {"Content-Type": "text/plain; charset=utf-8"}
    except KeyError:
        abort(404)


@bp.post("/b/<slug>/cards/<card_id>/task/<int:n>")
def toggle_task(slug, card_id, n):
    """Tick or untick the n-th checklist item in a card's notes."""
    try:
        card = store().get_card(slug, card_id)
        body = notes.toggle_task(card.body, n)
    except KeyError:
        abort(404)
    except IndexError:
        abort(400)
    card = store().update_card(slug, card_id, card.title, body, card.due, card.repeat, card.tags,
                               card.start, card.labels, card.priority)
    return render_template("_card.html", board=store().get_board(slug), card=card)


@bp.get("/search")
def search():
    criteria = _search_criteria_from(request.args)
    q, tags, priorities, board_slugs, statuses = (criteria["q"], criteria["tags"], criteria["priority"],
                                                   criteria["board"], criteria["status"])
    advanced = bool(tags or priorities or board_slugs or statuses)
    if not q and not advanced:
        results = []
    else:
        # Advanced-only (no text typed): browse everything instead of Store.search()'s "no terms,
        # no results" -- a plain empty search still means "type something", but checking a Tags or
        # Priority box with an empty search box means "show me what matches those".
        base = store().search(q) if q else store().all_cards()
        results = SR.refine(base, tags=tags, priorities=priorities, boards=board_slugs, statuses=statuses)
    heading = f"Search: {q}" if q else ("Advanced search" if advanced else "Search")
    empty = ("No cards match." if (q or advanced) else
            "Type something to search cards, notes, tags and board names.")
    search_boards = _card_boards()
    editing = request.args.get("edit", "")
    saved = [{**s, "url": _search_run_url(s)} for s in store().list_searches()]
    return render_template("results.html", q=q, heading=heading, results=results, empty=empty,
                           advanced=advanced, tags_raw=request.args.get("tags", ""),
                           priorities=priorities, board_slugs=board_slugs, statuses=statuses,
                           search_boards=search_boards, saved=saved, editing=editing,
                           editing_name=next((s["name"] for s in saved if s["id"] == editing), None))


@bp.post("/searches")
def create_search():
    name = request.form.get("name", "")
    try:
        store().save_search(name, _search_criteria_from(request.form))
    except ValueError as exc:
        return str(exc), 422
    return redirect(request.form.get("return_to") or url_for("boards.search"))


@bp.post("/searches/<search_id>/update")
def update_search(search_id):
    try:
        store().update_search(search_id, _search_criteria_from(request.form))
    except KeyError:
        abort(404)
    return redirect(request.form.get("return_to") or url_for("boards.search"))


@bp.post("/searches/<search_id>/rename")
def rename_search(search_id):
    try:
        store().rename_search(search_id, request.form.get("name", ""))
    except KeyError:
        abort(404)
    except ValueError as exc:
        return str(exc), 422
    return "", 204


@bp.post("/searches/<search_id>/duplicate")
def duplicate_search(search_id):
    try:
        store().duplicate_search(search_id)
    except KeyError:
        abort(404)
    return "", 204


@bp.post("/searches/<search_id>/pin")
def toggle_search_pin(search_id):
    try:
        entry = store().get_search(search_id)
        store().set_search_pinned(search_id, not entry["pinned"])
    except KeyError:
        abort(404)
    return "", 204


@bp.post("/searches/<search_id>/delete")
def delete_search(search_id):
    try:
        store().delete_search(search_id)
    except KeyError:
        abort(404)
    return "", 204


@bp.get("/sidebar/stats")
def sidebar_stats():
    """Fragment with the Today badge and tag list, fetched after a card changes (see sidebar.js)."""
    return render_template("_stats.html")


@bp.get("/tag/<tag>")
def tag_view(tag):
    tag = tag.lower()
    return render_template("results.html", q="", heading=f"#{tag}",
                           results=store().cards_with_tag(tag), empty="No cards with this tag.")


@bp.post("/b/<slug>/cards/<card_id>/move")
def move_card(slug, card_id):
    try:
        effects = store().move_card(slug, card_id, request.form["column"], int(request.form["index"]))
    except (KeyError, ValueError):
        abort(400)
    if effects:  # tell the page to reload so it shows what the rules did
        return jsonify({**_toast("Rule applied: " + "; ".join(effects)), "refresh": True})
    return "", 204


@bp.delete("/b/<slug>/cards/<card_id>")
def delete_card(slug, card_id):
    try:
        card = store().get_card(slug, card_id)
        store().trash_card(slug, card_id)
    except KeyError:
        abort(404)
    undo = {"url": url_for("boards.restore_card", slug=slug, card_id=card_id)}
    return _with_toast(make_response(""), _toast(f"Deleted “{_short(card.title)}”", undo))


@bp.post("/b/<slug>/cards/<card_id>/restore")
def restore_card(slug, card_id):
    try:
        store().restore_card(slug, card_id)
    except KeyError:
        abort(404)
    except ValueError:
        abort(400)
    return "", 204


@bp.post("/b/<slug>/cards/<card_id>/move-board")
def move_to_board(slug, card_id):
    """Move a card onto another board (dropped on it in the sidebar)."""
    try:
        card = store().get_card(slug, card_id)
        origin = store().move_card_to_board(
            slug, card_id, request.form.get("to", ""), request.form.get("column"),
            int(request.form.get("index") or 0))
        target = store().get_board(request.form.get("to", ""))
    except KeyError:
        abort(404)
    except ValueError:
        abort(400)
    undo = {"url": url_for("boards.move_to_board", slug=target.slug, card_id=origin["id"]),
            "body": {"to": origin["board"], "column": origin["column"], "index": origin["index"]}}
    return jsonify(_toast(f"Moved “{_short(card.title)}” to {target.title}", undo))


@bp.post("/b/<slug>/columns/clear-done")
def clear_done(slug):
    try:
        ids = store().archive_done(slug, request.form.get("name", ""))
    except KeyError:
        abort(404)
    if not ids:
        return jsonify(_toast("No completed cards to clear"))
    undo = {"url": url_for("boards.unarchive", slug=slug), "body": {"ids": ",".join(ids)}}
    return jsonify(_toast(f"Cleared {len(ids)} completed card{'s' * (len(ids) != 1)}", undo))


@bp.post("/b/<slug>/cards/unarchive")
def unarchive(slug):
    try:
        store().unarchive(slug, [i for i in request.form.get("ids", "").split(",") if i])
    except KeyError:
        abort(404)
    return "", 204


def _week_bounds(today):
    from datetime import timedelta
    monday = today - timedelta(days=today.weekday())
    return monday, monday + timedelta(days=6)


def _presets(today, overdue: bool):
    """Quick-filter chips. `overdue` is left out for the Logbook (nothing is "overdue" once done)."""
    from datetime import timedelta
    monday, sunday = _week_bounds(today)
    presets = [("Today", today.isoformat(), today.isoformat()), ("This week", monday.isoformat(), sunday.isoformat())]
    if overdue:
        presets.insert(1, ("Overdue", None, (today - timedelta(days=1)).isoformat()))
    presets.append(("All", None, None))
    return [{"label": label, "from": f, "to": t} for label, f, t in presets]


def _filter_from_query():
    """The from/to this GET request asked for. A malformed query string is quietly ignored
    (unfiltered) rather than erroring — the only way to hit one is hand-editing the URL, since
    the date-range form and every preset/saved-filter link always produce well-formed values."""
    try:
        return parse_iso_range(request.args.get("from", ""), request.args.get("to", ""))
    except ValueError:
        return None, None


@bp.get("/scheduled")
def scheduled():
    date_from, date_to = _filter_from_query()
    groups: dict[str, list] = {}
    for b, c in store().scheduled_cards(date_from, date_to):
        groups.setdefault(effective_date(c), []).append((b, c))
    return render_template("agenda.html", title="Scheduled", groups=groups, date_from=date_from,
                           date_to=date_to, presets=_presets(date.today(), overdue=True),
                           saved=store().list_filters(), filter_url=url_for("boards.scheduled"))


def _card_boards():
    return [b for b in store().list_boards() if b.kind in ("kanban", "tasks") and not b.archived]


@bp.get("/scheduled/export/dialog")
def scheduled_export_dialog():
    date_from, date_to = _filter_from_query()
    return render_template("_cards_export_dialog.html", action=url_for("boards.scheduled_export"),
                           title="Scheduled", date_from=date_from, date_to=date_to, boards=_card_boards(),
                           columns=None, show_status=False, sections=None)


@bp.get("/scheduled/export.csv")
def scheduled_export():
    date_from, date_to = _filter_from_query()
    results = store().scheduled_cards(date_from, date_to)
    results = SR.refine(results, q=request.args.get("q", ""), tags=parse_tags(request.args.get("tags", "")),
                        priorities=request.args.getlist("priority"), boards=request.args.getlist("board"))
    resp = make_response(csvimport.cards_to_csv(results))
    resp.headers["Content-Type"] = "text/csv; charset=utf-8"
    resp.headers["Content-Disposition"] = 'attachment; filename="scheduled.csv"'
    return resp


@bp.get("/today")
def today_view():
    """Due-or-overdue, completed today and created today, in one glance -- not a date-range view
    (there's no filter form), just today. Each of the three sections can be hidden from the page
    itself (a personal, per-device preference -- see today-hide in sidebar.js), not here.

    "Due & overdue" is drag-reorderable (Card.today_order): a card with an order sorts by it, full
    stop, ahead of every card that's never been dragged -- those fall back to the original
    date/board/position order, stably, so touching one card doesn't reshuffle the rest. This only
    reorders *this* list; Scheduled and Review's own "upcoming" keep sorting by date alone."""
    today = date.today().isoformat()
    due = store().scheduled_cards(date_to=today)
    due.sort(key=lambda bc: (bc[1].today_order is None, bc[1].today_order or 0))
    completed = store().logbook(date_from=today, date_to=today)
    created = store().created_on(today)
    live = {b.slug for b in store().list_boards()}
    return render_template("today.html", due=due, completed=completed, created=created,
                           today=today, live=live)


@bp.post("/today/reorder")
def reorder_today():
    ids = (request.get_json(silent=True) or {}).get("ids")
    if not isinstance(ids, list):
        abort(400)
    store().reorder_today([str(i) for i in ids])
    return "", 204


@bp.get("/today/export/dialog")
def today_export_dialog():
    return render_template("_cards_export_dialog.html", action=url_for("boards.today_export"),
                           title="Today", boards=_card_boards(), columns=None, show_status=False,
                           sections=[("due", "Due & overdue"), ("completed", "Completed today"),
                                     ("created", "Created today")])


def _resolve_logged_cards(events: list[dict]) -> list[tuple]:
    """Logbook events reference a board+card by id, not a live Card object -- resolve whichever
    still exist (the vast majority, for "completed today") so they can be filtered and exported
    the same way as any other (board, card) pair. One that's gone (board or card deleted since)
    is silently skipped, same as it already is everywhere else logbook entries meet live data."""
    resolved = []
    for e in events:
        try:
            resolved.append((store().get_board(e["board"]), store().get_card(e["board"], e["card"])))
        except KeyError:
            continue
    return resolved


@bp.get("/today/export.csv")
def today_export():
    today = date.today().isoformat()
    wanted_sections = request.args.getlist("section")
    kwargs = {"q": request.args.get("q", ""), "tags": parse_tags(request.args.get("tags", "")),
              "priorities": request.args.getlist("priority"), "boards": request.args.getlist("board")}
    results, sections = [], []
    if not wanted_sections or "due" in wanted_sections:
        due = SR.refine(store().scheduled_cards(date_to=today), **kwargs)
        results += due
        sections += ["due"] * len(due)
    if not wanted_sections or "completed" in wanted_sections:
        completed = SR.refine(_resolve_logged_cards(store().logbook(date_from=today, date_to=today)), **kwargs)
        results += completed
        sections += ["completed"] * len(completed)
    if not wanted_sections or "created" in wanted_sections:
        created = SR.refine(store().created_on(today), **kwargs)
        results += created
        sections += ["created"] * len(created)
    resp = make_response(csvimport.cards_to_csv(results, sections=sections))
    resp.headers["Content-Type"] = "text/csv; charset=utf-8"
    resp.headers["Content-Disposition"] = 'attachment; filename="today.csv"'
    return resp


def _review_args():
    back = RV.clamp_days(request.args["back"], 7) if "back" in request.args else 7
    forward = RV.clamp_days(request.args["forward"], 7) if "forward" in request.args else 7
    return back, forward, bool(request.args.get("starred"))


def _review_cards(back: int, forward: int, starred_only: bool) -> tuple[list[tuple], list[tuple]]:
    """Shared by the page itself and its CSV export, so "what counts as Completed/Upcoming right
    now" is defined exactly once."""
    today = date.today()
    if starred_only:
        starred = [(b, c) for b, c in store().all_cards() if c.starred and not c.hidden]
        completed = [(b, c) for b, c in starred if c.done]
        upcoming = [(b, c) for b, c in starred if not c.done]
    else:
        completed = []
        if back > 0:
            since = (today - timedelta(days=back)).isoformat()
            events = store().logbook(limit=None, date_from=since, date_to=today.isoformat())
            completed = _resolve_logged_cards(events)
        upcoming = []
        if forward > 0:
            until = (today + timedelta(days=forward)).isoformat()
            upcoming = store().scheduled_cards(date_to=until)
    completed.sort(key=lambda bc: bc[1].completed or "", reverse=True)
    upcoming.sort(key=lambda bc: effective_date(bc[1]) or "9999-12-31")
    return completed, upcoming


@bp.get("/review")
def review():
    """A quick "what did I do / what am I doing" report: completed in the last `back` days,
    due-or-overdue within the next `forward` days -- or, with `starred=1`, every starred card ever
    (completed and open), ignoring both day counts entirely (built for an annual review, not a
    weekly one). Both counts are free text, not a dropdown -- 0 is a real answer ("nothing that
    direction"), so only a missing/unparseable value falls back to the 7-day default. Not worth
    mentioning something? Hide the card (its own quick hide button, or the edit dialog) -- it drops
    out of this report the same way it drops out of every other one; see set_card_hidden."""
    back, forward, starred_only = _review_args()
    completed, upcoming = _review_cards(back, forward, starred_only)
    return render_template("review.html", completed=completed, upcoming=upcoming, back=back,
                           forward=forward, starred_only=starred_only, today=date.today().isoformat())


@bp.get("/review/export/dialog")
def review_export_dialog():
    back, forward, starred_only = _review_args()
    return render_template("_cards_export_dialog.html", action=url_for("boards.review_export"),
                           title="Review", boards=_card_boards(), columns=None, show_status=False,
                           sections=[("completed", "Completed"), ("upcoming", "Upcoming")],
                           extra_fields={"back": back, "forward": forward, "starred": "1" if starred_only else ""})


@bp.get("/review/export.csv")
def review_export():
    back, forward, starred_only = _review_args()
    wanted_sections = request.args.getlist("section")
    kwargs = {"q": request.args.get("q", ""), "tags": parse_tags(request.args.get("tags", "")),
              "priorities": request.args.getlist("priority"), "boards": request.args.getlist("board")}
    completed, upcoming = _review_cards(back, forward, starred_only)
    results, sections = [], []
    if not wanted_sections or "completed" in wanted_sections:
        rows = SR.refine(completed, **kwargs)
        results += rows
        sections += ["completed"] * len(rows)
    if not wanted_sections or "upcoming" in wanted_sections:
        rows = SR.refine(upcoming, **kwargs)
        results += rows
        sections += ["upcoming"] * len(rows)
    resp = make_response(csvimport.cards_to_csv(results, sections=sections))
    resp.headers["Content-Type"] = "text/csv; charset=utf-8"
    resp.headers["Content-Disposition"] = 'attachment; filename="review.csv"'
    return resp


@bp.post("/filters")
def save_filter():
    try:
        date_from, date_to = parse_iso_range(request.form.get("from", ""), request.form.get("to", ""))
    except ValueError as exc:
        return str(exc), 422
    name = request.form.get("name", "")
    return_to = request.form.get("return_to") or url_for("boards.scheduled")
    try:
        store().save_filter(name, date_from, date_to)
    except ValueError as exc:
        return str(exc), 422
    return redirect(return_to)


# -- lists (columns): structural changes just refresh the board -----------------------------


def _refresh():
    resp = make_response("")
    resp.headers["HX-Refresh"] = "true"
    return resp


def _column_action(slug, action, *args):
    try:
        action(slug, *args)
    except KeyError:
        abort(404)
    except ValueError:
        abort(400)
    return _refresh()


@bp.post("/b/<slug>/columns")
def add_column(slug):
    return _column_action(slug, store().add_column, request.form.get("name", ""))


@bp.post("/b/<slug>/columns/rename")
def rename_column(slug):
    return _column_action(slug, store().rename_column, request.form.get("old", ""),
                          request.form.get("new", ""))


@bp.post("/b/<slug>/columns/hide")
def hide_column(slug):
    return _column_action(slug, store().set_column_hidden, request.form.get("name", ""),
                          request.form.get("hidden") == "1")


@bp.post("/b/<slug>/columns/delete")
def delete_column(slug):
    return _column_action(slug, store().delete_column, request.form.get("name", ""))


@bp.post("/b/<slug>/columns/order")
def order_columns(slug):
    names = (request.get_json(silent=True) or {}).get("names")
    if not isinstance(names, list):
        abort(400)
    try:
        store().reorder_columns(slug, [str(n) for n in names])
    except KeyError:
        abort(404)
    except ValueError:
        abort(400)
    return "", 204


# -- sidebar: areas and board order ---------------------------------------------------------


def _store_action(action, *args):
    try:
        action(*args)
    except (KeyError, ValueError):
        abort(400)
    return _refresh()


@bp.post("/areas")
def add_area():
    return _store_action(store().add_area, request.form.get("name", ""))


@bp.post("/areas/rename")
def rename_area():
    return _store_action(store().rename_area, request.form.get("old", ""),
                         request.form.get("new", ""))


@bp.post("/areas/delete")
def delete_area():
    name = request.form.get("name", "")
    try:
        index, held = store().delete_area(name)
    except ValueError:
        abort(400)
    undo = {"url": url_for("boards.restore_area"),
            "body": {"name": name, "index": index, "boards": ",".join(held)}}
    kept = f" · {len(held)} board{'s' * (len(held) != 1)} kept" if held else ""
    return jsonify(_toast(f"Deleted area “{_short(name)}”{kept}", undo, later=True))


@bp.post("/areas/restore")
def restore_area():
    try:
        store().restore_area(request.form.get("name", ""), int(request.form.get("index") or 0),
                             [b for b in request.form.get("boards", "").split(",") if b])
    except ValueError:
        abort(400)
    return "", 204


@bp.post("/layout")
def layout():
    data = request.get_json(silent=True) or {}
    areas, boards = data.get("areas"), data.get("boards")
    if not isinstance(areas, list) or not isinstance(boards, dict):
        abort(400)
    try:
        store().apply_layout([str(a) for a in areas],
                             {str(k): [str(s) for s in v] for k, v in boards.items()})
    except (KeyError, ValueError, TypeError):
        abort(400)
    return "", 204


# -- boards: rename, delete (to the trash), inbox, logbook, trash ---------------------------


@bp.post("/b/<slug>/rename")
def rename_board(slug):
    try:
        store().rename_board(slug, request.form.get("title", ""))
    except KeyError:
        abort(404)
    except ValueError:
        abort(400)
    return _refresh()


@bp.post("/b/<slug>/duplicate")
def duplicate_board(slug):
    """Redirects to the new board (the client follows it and navigates there itself --
    data-after="navigate", ui.js), same as creating one from the FAB. No undo toast (a redirect
    has no JSON body to carry one) -- the board's own "Delete board" button, right there once you
    land on it, is itself undoable (boards.restore_board) if the copy turns out unwanted."""
    try:
        copy = store().duplicate_board(slug)
    except KeyError:
        abort(404)
    return redirect(url_for("boards.board", slug=copy.slug))


@bp.post("/b/<slug>/delete")
def delete_board(slug):
    try:
        board = store().get_board(slug)
        trash_id = store().trash_board(slug)
    except KeyError:
        abort(404)
    undo = {"url": url_for("boards.restore_board", trash_id=trash_id)}
    return jsonify(_toast(f"Deleted board “{_short(board.title)}”", undo, later=True))


@bp.post("/trash/boards/<trash_id>/restore")
def restore_board(trash_id):
    try:
        board = store().restore_board(trash_id)
    except KeyError:
        abort(404)
    return jsonify(board=board.slug, message=f"Restored board “{_short(board.title)}”")


@bp.post("/b/<slug>/archive")
def archive_board(slug):
    try:
        board = store().get_board(slug)
        store().archive_board(slug)
    except KeyError:
        abort(404)
    return jsonify(_toast(f"Archived “{_short(board.title)}” · out of the sidebar and search"))


@bp.post("/b/<slug>/unarchive")
def unarchive_board(slug):
    try:
        board = store().get_board(slug)
        store().unarchive_board(slug)
    except KeyError:
        abort(404)
    return jsonify(_toast(f"Unarchived “{_short(board.title)}”"))


@bp.get("/archived")
def archived_boards():
    return render_template("archived.html", boards=store().list_archived_boards())


@bp.post("/b/<slug>/pin")
def toggle_pin(slug):
    try:
        board = store().get_board(slug)
        store().set_pinned(slug, not board.pinned)
    except KeyError:
        abort(404)
    pinned = not board.pinned
    return jsonify(_toast(f"{'Pinned' if pinned else 'Unpinned'} “{_short(board.title)}”"))


@bp.post("/capture")
def capture():
    """Quick-add from anywhere: lands at the top of whichever board the client asked for."""
    title, due, rule, tags = _parse_quick(request.form.get("title", ""))
    slug = request.form.get("board", "")
    if not title or not slug:
        abort(400)
    try:
        board = store().get_board(slug)
    except KeyError:
        abort(404)
    if board.kind not in ("kanban", "tasks") or not board.columns:
        abort(400)
    top = store().settings_for(board.slug)["new_card_position"] == "top"
    card = store().add_card(board.slug, title, board.columns[0], due, rule, tags, top=top)
    undo = {"url": url_for("boards.delete_card", slug=board.slug, card_id=card.id),
            "method": "DELETE"}
    return jsonify({**_toast(f"Added to {board.title}: “{_short(title)}”", undo), "board": board.slug})


@bp.get("/logbook")
def logbook():
    date_from, date_to = _filter_from_query()
    days: dict[str, list] = {}
    for event in store().logbook(date_from=date_from, date_to=date_to):
        days.setdefault(event["at"][:10], []).append(event)
    live = {b.slug for b in store().list_boards()}
    return render_template("logbook.html", days=days, live=live, date_from=date_from,
                           date_to=date_to, presets=_presets(date.today(), overdue=False),
                           saved=store().list_filters(), filter_url=url_for("boards.logbook"))


@bp.get("/metrics")
def metrics():
    date_from, date_to = _filter_from_query()
    q = request.args.get("q", "").strip()
    tags = parse_tags(request.args.get("tags", ""))
    priorities = request.args.getlist("priority")
    board_slugs = request.args.getlist("board")
    events = store().logbook(limit=None, date_from=date_from, date_to=date_to)
    events = M.filter_events(events, q=q, tags=tags, priorities=priorities, boards=board_slugs)
    filtered = bool(q or tags or priorities or board_slugs)
    export_qs = urlencode([("from", date_from or ""), ("to", date_to or ""), ("q", q),
                          ("tags", request.args.get("tags", "")), *[("priority", p) for p in priorities],
                          *[("board", b) for b in board_slugs]])
    return render_template("metrics.html", total=len(events), by_board=M.by_board(events),
                           by_weekday=M.by_weekday(events), date_from=date_from, date_to=date_to,
                           presets=_presets(date.today(), overdue=False), saved=store().list_filters(),
                           filter_url=url_for("boards.metrics"), filtered=filtered, q=q,
                           tags_raw=request.args.get("tags", ""), priorities=priorities,
                           board_slugs=board_slugs, metrics_boards=_card_boards(),
                           export_url=f"{url_for('boards.export_dialog')}?{export_qs}")


@bp.get("/export/dialog")
def export_dialog():
    """A pop-out with granular export options (date range, title text, tags, priority, board) --
    opened from the download icon next to the date filter on Logbook/Metrics, not a direct
    download link, so a bulk export can be narrowed the same way any other filter in the app is.
    Pre-fills from whatever's in the query string, so opening it from an already-filtered Metrics
    view (its own "Export" link carries its current filters along) starts matching, not blank."""
    date_from, date_to = _filter_from_query()
    return render_template("_export_dialog.html", date_from=date_from, date_to=date_to,
                           boards=_card_boards(), q=request.args.get("q", ""),
                           tags_raw=request.args.get("tags", ""), priorities=request.args.getlist("priority"),
                           board_slugs=request.args.getlist("board"))


@bp.get("/export/activity.csv")
def export_activity():
    date_from, date_to = _filter_from_query()
    events = store().logbook(limit=None, date_from=date_from, date_to=date_to)
    events = M.filter_events(events, q=request.args.get("q", ""),
                             tags=parse_tags(request.args.get("tags", "")),
                             priorities=request.args.getlist("priority"),
                             boards=request.args.getlist("board"))
    name = "activity.csv" if not (date_from or date_to) else f"activity_{date_from or 'start'}_{date_to or 'end'}.csv"
    resp = make_response(M.to_csv(events))
    resp.headers["Content-Type"] = "text/csv; charset=utf-8"
    resp.headers["Content-Disposition"] = f'attachment; filename="{name}"'
    return resp


@bp.post("/b/<slug>/cards/<card_id>/completed-at")
def edit_completed_at(slug, card_id):
    raw = request.form.get("at", "").strip()
    try:
        at = datetime.fromisoformat(raw.replace(" ", "T")).isoformat(timespec="minutes")
    except ValueError:
        abort(400)
    try:
        card = store().edit_completion(slug, card_id, at)
    except KeyError:
        abort(404)
    except ValueError:
        abort(400)
    return render_template("_card.html", board=store().get_board(slug), card=card)


@bp.post("/filters/<filter_id>/delete")
def delete_filter(filter_id):
    try:
        index, entry = store().delete_filter(filter_id)
    except KeyError:
        abort(404)
    undo = {"url": url_for("boards.restore_filter"),
            "body": {"index": index, "entry": json.dumps(entry)}}
    return jsonify(_toast(f"Deleted filter “{_short(entry['name'])}”", undo))


@bp.post("/filters/restore")
def restore_filter():
    try:
        entry = json.loads(request.form.get("entry", ""))
        store().restore_filter(entry, int(request.form.get("index") or 0))
    except (ValueError, TypeError, KeyError):
        abort(400)
    return "", 204


@bp.get("/trash")
def trash():
    return render_template("trash.html", trash=store().list_trash())


@bp.post("/trash/empty")
def empty_trash():
    store().empty_trash()
    return jsonify(_toast("Trash emptied", later=True))


@bp.get("/manifest.webmanifest")
def manifest():
    """Lets the site be installed to a phone's home screen."""
    icon = lambda name, size, purpose="any": {
        "src": url_for("static", filename=f"icons/{name}"), "sizes": f"{size}x{size}",
        "type": "image/png", "purpose": purpose}
    return jsonify(
        name="Kanban", short_name="Kanban", start_url="/", scope="/", display="standalone",
        background_color="#16181d", theme_color="#3b82f6",
        icons=[icon("icon-192.png", 192), icon("icon-512.png", 512),
               icon("icon-maskable-512.png", 512, "maskable")],
    ), 200, {"Content-Type": "application/manifest+json"}


def _rule_rows(scope):
    return [{"rule": rule, "text": R.describe(rule)} for rule in store().list_rules(scope)]


def _recipes(lists):
    """One-click rules. `lists` are the board's list names (None for global rules)."""
    names = lists or S.DEFAULT_COLUMNS
    done = next((n for n in names if n.lower() == "done"), names[-1])
    first = names[0]
    recipes = [
        {"title": f"Checking a card moves it to {done}",
         "vals": {"when": "completed", "do": "move", "list": done}},
        {"title": f"Moving a card into {done} marks it complete",
         "vals": {"when": "moved", "in": done, "do": "complete"}},
    ]
    if first != done:
        recipes.append({"title": f"Un-checking a card in {done} moves it back to {first}",
                        "vals": {"when": "uncompleted", "in": done, "do": "move", "list": first}})
    return recipes


def _rules_context(scope, lists):
    every_list = sorted({c for b in store().list_boards() if b.kind == "kanban" for c in b.columns})
    return {"scope": scope or "global", "rules": _rule_rows(scope), "recipes": _recipes(lists),
            "lists": lists, "all_lists": every_list, "triggers": R.TRIGGERS, "actions": R.ACTIONS}


@bp.get("/settings")
def settings():
    gs = store().global_settings()
    searches = [{**s, "url": _search_run_url(s)} for s in store().list_searches()]
    return render_template("settings.html", themes=theme_cards(), text_sizes=TEXT_SIZES, gs=gs,
                           resolved=S.resolve(gs), searches=searches, hidden_cards=store().all_hidden_cards(),
                           **_rules_context(None, None))


@bp.post("/settings")
def save_settings():
    try:
        store().save_global_settings(request.form.to_dict())
    except ValueError as exc:
        return str(exc), 422
    return "Saved"


def _configurable_or_404(slug):
    """A board with its own settings page: kanban or tasks (canvas never existed with settings)."""
    try:
        board = store().get_board(slug)
    except KeyError:
        abort(404)
    if board.kind not in ("kanban", "tasks"):
        abort(404)
    return board


@bp.get("/b/<slug>/settings")
def board_settings(slug):
    board = _configurable_or_404(slug)
    gs = store().global_settings()
    ctx = _rules_context(slug, board.columns) if board.kind == "kanban" else {}
    return render_template(
        "board_settings.html", board=board, parent=None, raw=store().board_settings(slug),
        resolved=S.resolve(gs), inherits=S.resolve(gs, board.settings)["inherit_global_rules"],
        global_rules=_rule_rows(None) if board.kind == "kanban" else [], colors=list(L.COLORS), **ctx)


@bp.post("/b/<slug>/settings")
def save_board_settings(slug):
    _configurable_or_404(slug)
    form = request.form.to_dict()
    form["inherit_global_rules"] = request.form.getlist("inherit_global_rules")[-1] \
        if request.form.getlist("inherit_global_rules") else ""
    try:
        store().save_board_settings(slug, form)
    except ValueError as exc:
        return str(exc), 422
    return "Saved"


def _scope_of(form):
    scope = form.get("scope", "global")
    return None if scope == "global" else scope


@bp.post("/rules/add")
def add_rule():
    form = request.form
    raw = {"when": form.get("when"), "in": form.get("in"), "tag": form.get("tag"), "do": form.get("do"),
           "arg": form.get("list") if form.get("do") == "move" else form.get("tagarg")}
    try:
        store().add_rule(_scope_of(form), raw)
    except KeyError:
        abort(404)
    except ValueError as exc:
        return str(exc), 422
    return _refresh()


@bp.post("/rules/<rule_id>/toggle")
def toggle_rule(rule_id):
    enabled = (request.form.getlist("enabled") or ["0"])[-1] == "1"
    try:
        store().toggle_rule(_scope_of(request.form), rule_id, enabled)
    except KeyError:
        abort(404)
    return "", 204


@bp.post("/rules/<rule_id>/delete")
def delete_rule(rule_id):
    scope = _scope_of(request.form)
    try:
        index, rule = store().delete_rule(scope, rule_id)
    except KeyError:
        abort(404)
    undo = {"url": url_for("boards.restore_rule"),
            "body": {"scope": request.form.get("scope", "global"), "index": index,
                     "rule": json.dumps(rule)}}
    return jsonify(_toast(f"Deleted rule: {R.describe(rule)}", undo, later=True))


@bp.post("/rules/restore")
def restore_rule():
    try:
        rule = json.loads(request.form.get("rule", ""))
        store().add_rule(_scope_of(request.form), rule, int(request.form.get("index") or 0))
    except (ValueError, TypeError, KeyError):
        abort(400)
    return "", 204


# -- labels: a board's own small, named, coloured set -----------------------------------------


@bp.post("/b/<slug>/labels")
def add_label(slug):
    try:
        store().add_label(slug, request.form.get("name", ""), request.form.get("color", ""))
    except KeyError:
        abort(404)
    except ValueError as exc:
        return str(exc), 422
    return _refresh()


@bp.post("/b/<slug>/labels/<label_id>")
def update_label(slug, label_id):
    try:
        store().update_label(slug, label_id, request.form.get("name", ""), request.form.get("color", ""))
    except KeyError:
        abort(404)
    except ValueError as exc:
        return str(exc), 422
    return _refresh()


@bp.post("/b/<slug>/labels/<label_id>/delete")
def delete_label(slug, label_id):
    try:
        store().delete_label(slug, label_id)
    except KeyError:
        abort(404)
    return _refresh()
