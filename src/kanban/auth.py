"""Optional single-password login, for LAN deployments only (see README's install modes). Not a
"pure domain module" like rules.py/settings.py/dates.py/notes.py/tags.py/labels.py -- it inherently
needs Flask's session and request, so it doesn't join that list in AGENTS.md.

Disabled entirely when KANBAN_PASSWORD is unset (the default): every route stays open, exactly as
before this existed. A genuinely localhost-only deployment (bound to 127.0.0.1, or Docker with the
port published to 127.0.0.1 only) never needs this and should leave KANBAN_PASSWORD unset -- see
docs/decisions/0005-lan-only-login.md for the reasoning.
"""

from __future__ import annotations

import hashlib
import hmac
import time

from flask import Blueprint, current_app, redirect, render_template, request, session, url_for

bp = Blueprint("auth", __name__)

MAX_FAILURES = 5
WINDOW_SECONDS = 300  # 5 minutes
# A single gunicorn worker (see Dockerfile: "cards are plain files with no cross-process locking")
# makes this in-memory list safe without a lock -- there is only ever one process holding it. If
# that assumption ever changes, this throttle needs real shared state (or gunicorn's --preload
# won't save it either, since workers still don't share memory).
_recent_failures: list[float] = []


def secret_key_for(password: str) -> str:
    """Derive a stable session-signing key from the password itself: no extra secret to generate,
    store or rotate, and changing the password invalidates every existing session for free. Trades
    session-signing strength for password strength -- pick a real passphrase, not a PIN."""
    return hashlib.sha256(f"trellis-session-key:{password}".encode()).hexdigest()


def _throttled(now: float) -> bool:
    while _recent_failures and _recent_failures[0] < now - WINDOW_SECONDS:
        _recent_failures.pop(0)
    return len(_recent_failures) >= MAX_FAILURES


def _safe_next(candidate: str | None) -> str:
    """Only ever redirect to a path on this app: an absolute or protocol-relative `next` would be
    an open redirect (e.g. `next=//evil.example`)."""
    if candidate and candidate.startswith("/") and not candidate.startswith("//"):
        return candidate
    return url_for("boards.index")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        if session.get("authed"):
            return redirect(_safe_next(request.args.get("next")))
        return render_template("login.html", next=request.args.get("next", ""), error=None)

    now = time.time()
    dest = _safe_next(request.form.get("next"))
    if _throttled(now):
        return render_template(
            "login.html", next=dest, error="Too many attempts. Wait a few minutes and try again."
        ), 429

    password = current_app.config["PASSWORD"]
    if password and hmac.compare_digest(request.form.get("password", "").encode(), password.encode()):
        _recent_failures.clear()
        session.clear()
        session["authed"] = True
        session.permanent = True
        return redirect(dest)

    _recent_failures.append(now)
    return render_template("login.html", next=dest, error="Wrong password."), 401


@bp.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
