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

from .dates import parse_due, split_due

bp = Blueprint("boards", __name__)


def store():
    return current_app.config["STORE"]


@bp.app_context_processor
def nav():
    return {"boards": store().list_boards(), "today": date.today().isoformat()}


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
    title, due = split_due(request.form.get("title", ""))
    if not title:
        abort(400)
    try:
        card = store().add_card(slug, title, request.form.get("column", ""),
                                due.isoformat() if due else None)
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
    if not title or (raw_due and due is None):
        abort(400)
    try:
        store().update_card(slug, card_id, title, request.form.get("body", ""),
                            due.isoformat() if due else None)
    except KeyError:
        abort(404)
    resp = make_response("")
    resp.headers["HX-Refresh"] = "true"
    return resp


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
