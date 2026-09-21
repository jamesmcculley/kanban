"""JSON/HTML endpoints behind the canvas board's drag, paste and upload behaviour."""

from flask import (
    Blueprint,
    abort,
    current_app,
    jsonify,
    make_response,
    render_template,
    request,
    send_file,
    url_for,
)

from .canvas import MAX_IMAGE_BYTES

cv = Blueprint("canvas", __name__)


def store():
    return current_app.config["STORE"]


def _num(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _render_item(slug, item):
    return render_template("_item.html", board=store().get_board(slug), item=item)


@cv.post("/b/<slug>/items")
def add_item(slug):
    data = request.get_json(silent=True) or {}
    x, y = _num(data.get("x")), _num(data.get("y"))
    try:
        if data.get("kind") == "board":
            item = store().add_child_board(slug, str(data.get("title", "")),
                                           str(data.get("board_kind", "kanban")), x, y)
        else:
            item = store().add_item(slug, str(data.get("kind", "")), x, y,
                                    text=str(data.get("text", "")), url=data.get("url"),
                                    color=str(data.get("color", "yellow")))
    except KeyError:
        abort(404)
    except ValueError:
        abort(400)
    return _render_item(slug, item)


@cv.patch("/b/<slug>/items/<item_id>")
def update_item(slug, item_id):
    data = request.get_json(silent=True) or {}
    fields = {k: data[k] for k in ("x", "y", "w", "color", "text") if k in data}
    try:
        store().update_item(slug, item_id, **fields)
    except KeyError:
        abort(404)
    except ValueError:
        abort(400)
    return "", 204


@cv.delete("/b/<slug>/items/<item_id>")
def delete_item(slug, item_id):
    try:
        store().delete_item(slug, item_id)
    except KeyError:
        abort(404)
    except ValueError:
        abort(400)
    undo = {"url": url_for("canvas.restore_item", slug=slug, item_id=item_id)}
    return jsonify(message="Deleted from the canvas", undo=undo)


@cv.post("/b/<slug>/items/<item_id>/restore")
def restore_item(slug, item_id):
    try:
        store().restore_item(slug, item_id)
    except KeyError:
        abort(404)
    except ValueError:
        abort(400)
    return "", 204


@cv.post("/b/<slug>/upload")
def upload(slug):
    file = request.files.get("file")
    if file is None:
        abort(400)
    data = file.read(MAX_IMAGE_BYTES + 1)
    try:
        item = store().add_image(slug, data, _num(request.form.get("x")), _num(request.form.get("y")))
    except KeyError:
        abort(404)
    except ValueError:
        abort(400)
    return _render_item(slug, item)


@cv.get("/b/<slug>/assets/<filename>")
def asset(slug, filename):
    try:
        path = store().asset_path(slug, filename)
        store().get_board(slug)
    except KeyError:
        abort(404)
    if not path.exists():
        abort(404)
    resp = make_response(send_file(path))
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Content-Security-Policy"] = "default-src 'none'; sandbox"
    resp.headers["Cache-Control"] = "private, max-age=86400"
    return resp
