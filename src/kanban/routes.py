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

bp = Blueprint("boards", __name__)


def store():
    return current_app.config["STORE"]


@bp.app_context_processor
def nav():
    today = date.today().isoformat()
    due_now = sum(1 for _, c in store().dated_cards() if c.due <= today)
    return {"boards": store().list_boards(), "today": today, "today_count": due_now}


@bp.get("/")
def index():
    boards = store().list_boards()
    if not boards:
        boards = [store().create_board("My Board")]
    return redirect(url_for("boards.board", slug=boards[0].slug))


@bp.post("/boards")
def create_board():
    title = request.form.get("title", "").strip()
    if not title:
        abort(400)
    return redirect(url_for("boards.board", slug=store().create_board(title).slug))


@bp.get("/b/<slug>")
def board(slug):
    try:
        b = store().get_board(slug)
    except KeyError:
        abort(404)
    return render_template("board.html", board=b, columns=store().cards_by_column(slug))


@bp.post("/b/<slug>/cards")
def add_card(slug):
    title, rule = split_repeat(request.form.get("title", ""))
    title, due = split_due(title)
    if rule and not due:
        due = first_due(rule)
    if not title:
        abort(400)
    try:
        card = store().add_card(slug, title, request.form.get("column", ""),
                                due.isoformat() if due else None, rule)
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
                                   due.isoformat() if due else None, rule)
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
    return render_template("search.html", q=q, results=store().search(q))


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
