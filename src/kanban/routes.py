import json
from datetime import date

from flask import (
    Blueprint,
    abort,
    current_app,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    url_for,
)

from . import notes
from .dates import first_due, parse_due, parse_repeat, split_due, split_repeat
from .store import parse_tags, split_tags

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


@bp.app_context_processor
def nav():
    today = date.today().isoformat()
    due_now = sum(1 for _, c in store().dated_cards() if c.due <= today)
    current = (request.view_args or {}).get("slug") if request.endpoint == "boards.board" else None
    return {"sidebar": store().sidebar(), "tags": store().tag_counts(), "today": today,
            "today_count": due_now, "current_board": current, "inbox_count": store().inbox_count()}


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
    title, due, rule, tags = _parse_quick(request.form.get("title", ""))
    if not title:
        abort(400)
    try:
        card = store().add_card(slug, title, request.form.get("column", ""), due, rule, tags,
                                top=True)
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
        before = store().get_card(slug, card_id)
        card = store().complete_card(slug, card_id)
    except KeyError:
        abort(404)
    refresh = bool(request.args.get("refresh"))  # agenda/search rows: re-render the whole page
    toast = None
    if before.repeat or (card.done and not before.done):  # a completion, not an un-check
        at = card.last_completed if before.repeat else card.completed
        undo = url_for("boards.undo_complete", slug=slug, card_id=card_id, at=at,
                       due=before.due or "", last=before.last_completed or "")
        message = f"Completed “{_short(card.title)}”"
        if before.repeat and card.due:
            message += f" · next {card.due}"
        toast = _toast(message, {"url": undo}, later=refresh)
    resp = _refresh() if refresh else make_response(
        render_template("_card.html", board=store().get_board(slug), card=card))
    return _with_toast(resp, toast)


@bp.post("/b/<slug>/cards/<card_id>/undo-complete")
def undo_complete(slug, card_id):
    at = request.args.get("at", "")
    if not at:
        abort(400)
    try:
        store().undo_complete(slug, card_id, at, request.args.get("due") or None,
                              request.args.get("last") or None)
    except KeyError:
        abort(404)
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
    card = store().update_card(slug, card_id, card.title, body, card.due, card.repeat, card.tags)
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


@bp.get("/inbox")
def inbox():
    return redirect(url_for("boards.board", slug=store().ensure_inbox().slug))


@bp.post("/capture")
def capture():
    """Quick-add from anywhere: lands at the top of the Inbox."""
    title, due, rule, tags = _parse_quick(request.form.get("title", ""))
    if not title:
        abort(400)
    board = store().ensure_inbox()
    if not board.columns:
        store().add_column(board.slug, "Inbox")
        board = store().get_board(board.slug)
    card = store().add_card(board.slug, title, board.columns[0], due, rule, tags, top=True)
    undo = {"url": url_for("boards.delete_card", slug=board.slug, card_id=card.id),
            "method": "DELETE"}
    return jsonify({**_toast(f"Added to Inbox: “{_short(title)}”", undo), "board": board.slug})


@bp.get("/logbook")
def logbook():
    days: dict[str, list] = {}
    for event in store().logbook():
        days.setdefault(event["at"][:10], []).append(event)
    live = {b.slug for b in store().list_boards()}
    return render_template("logbook.html", days=days, live=live)


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
        name="Trellis", short_name="Trellis", start_url="/", scope="/", display="standalone",
        background_color="#16181d", theme_color="#3b82f6",
        icons=[icon("icon-192.png", 192), icon("icon-512.png", 512),
               icon("icon-maskable-512.png", 512, "maskable")],
    ), 200, {"Content-Type": "application/manifest+json"}
