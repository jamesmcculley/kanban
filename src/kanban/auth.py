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
# A single gunicorn worker (Dockerfile: "--workers 1 --threads 4") keeps this in one process, so a
# plain list works at all -- multiple workers would each hold their own copy and the throttle would
# undercount. Within that one process, gunicorn's 4 threads can still interleave a check-then-append
# under real concurrency (CPython's GIL keeps each list op atomic, but not the check-then-act pair),
# which can let the count drift a request or two past MAX_FAILURES before it engages. That's an
# acceptable imprecision for a personal app's login throttle -- not a bypass, just not exact -- and
# not worth a lock over. If this ever needs to be exact (or workers > 1), it needs real shared state.
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


# Characters a browser's URL parser treats as, or turns into, a path separator when resolving a
# redirect -- so a naive `startswith("//")` check alone is bypassable. Confirmed in a real browser
# (`new URL(candidate, origin)`): "/\\evil.example" and "/<TAB>/evil.example" both resolve to
# "http://evil.example/", because backslash is normalized to "/" for special schemes, and ASCII
# tab/newline/CR are stripped entirely *before* that -- collapsing "/<TAB>/evil.example" into
# "//evil.example" -- regardless of what the string looks like before the browser gets it.
_UNSAFE_NEXT_CHARS = ("\\", "\t", "\n", "\r")


def _safe_next(candidate: str | None) -> str:
    """Only ever redirect to a path on this app: an absolute or protocol-relative `next` would be
    an open redirect (e.g. `next=//evil.example`, or one of the browser-normalization variants
    above)."""
    if (candidate and candidate.startswith("/") and not candidate.startswith("//")
            and not any(ch in candidate for ch in _UNSAFE_NEXT_CHARS)):
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
