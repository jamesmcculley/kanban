from datetime import date

from flask import (
    Blueprint,
    abort,
    current_app,
    make_response,
    redirect,
    render_template,
    request,
    url_for,
)

from .dates import first_due, parse_due, parse_repeat, split_due, split_repeat
from .store import parse_tags, split_tags

bp = Blueprint("boards", __name__)


def store():
    return current_app.config["STORE"]


@bp.app_context_processor
def nav():
    today = date.today().isoformat()
    due_now = sum(1 for _, c in store().dated_cards() if c.due <= today)
    current = (request.view_args or {}).get("slug") if request.endpoint == "boards.board" else None
    return {"sidebar": store().sidebar(), "tags": store().tag_counts(), "today": today,
            "today_count": due_now, "current_board": current}


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


@bp.get("/b/<slug>")
def board(slug):
    try:
        b = store().get_board(slug)
    except KeyError:
        abort(404)
    parent = store().get_board(b.parent) if b.parent else None
    if b.kind == "canvas":
        return render_template("canvas.html", board=b, parent=parent, items=store().list_items(slug))
    return render_template("board.html", board=b, parent=parent, columns=store().cards_by_column(slug))


@bp.post("/b/<slug>/cards")
def add_card(slug):
    title, tags = split_tags(request.form.get("title", ""))
    title, rule = split_repeat(title)
    title, due = split_due(title)
    if rule and not due:
        due = first_due(rule)
    if not title:
        abort(400)
    try:
        card = store().add_card(slug, title, request.form.get("column", ""),
                                due.isoformat() if due else None, rule, tags)
    except (KeyError, ValueError):
        abort(400)
    return render_template("_card.html", board=store().get_board(slug), card=card)


@bp.get("/b/<slug>/cards/<card_id>")
def edit_card(slug, card_id):
    try:
        return render_template("_edit.html", board=store().get_board(slug),
                               card=store().get_card(slug, card_id))
    except KeyError:
        abort(404)


@bp.post("/b/<slug>/cards/<card_id>")
def update_card(slug, card_id):
    title = request.form.get("title", "").strip()
    raw_due = request.form.get("due", "").strip()
    due = parse_due(raw_due) if raw_due else None
    raw_repeat = request.form.get("repeat", "").strip()
    rule = parse_repeat(raw_repeat) if raw_repeat else None
    if not title or (raw_due and due is None) or (raw_repeat and rule is None):
        abort(400)
    try:
        card = store().update_card(slug, card_id, title, request.form.get("body", ""),
                                   due.isoformat() if due else None, rule,
                                   parse_tags(request.form.get("tags", "")))
    except KeyError:
        abort(404)
    return render_template("_card.html", board=store().get_board(slug), card=card)


@bp.post("/b/<slug>/cards/<card_id>/complete")
def complete(slug, card_id):
    try:
        card = store().complete_card(slug, card_id)
    except KeyError:
        abort(404)
    if request.args.get("refresh"):  # agenda/search rows: re-render the whole list
        resp = make_response("")
        resp.headers["HX-Refresh"] = "true"
        return resp
    return render_template("_card.html", board=store().get_board(slug), card=card)


@bp.get("/search")
def search():
    q = request.args.get("q", "").strip()
    return render_template("results.html", q=q, heading=f"Search: {q}" if q else "Search",
                           results=store().search(q),
                           empty="No cards match." if q else
                           "Type something to search cards, notes, tags and board names.")


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
        store().move_card(slug, card_id, request.form["column"], int(request.form["index"]))
    except (KeyError, ValueError):
        abort(400)
    return "", 204


@bp.delete("/b/<slug>/cards/<card_id>")
def delete_card(slug, card_id):
    try:
        store().delete_card(slug, card_id)
    except KeyError:
        abort(404)
    return ""


def _agenda(title, keep):
    items = [(b, c) for b, c in store().dated_cards() if keep(c.due)]
    groups: dict[str, list] = {}
    for b, c in items:
        groups.setdefault(c.due, []).append((b, c))
    return render_template("agenda.html", title=title, groups=groups)


@bp.get("/today")
def today_view():
    today = date.today().isoformat()
    return _agenda("Today", lambda d: d <= today)


@bp.get("/upcoming")
def upcoming_view():
    today = date.today().isoformat()
    return _agenda("Upcoming", lambda d: d > today)


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
    return _store_action(store().delete_area, request.form.get("name", ""))


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
