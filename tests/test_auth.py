from urllib.parse import parse_qs, urlparse

import pytest

from kanban import auth, create_app


@pytest.fixture(autouse=True)
def _reset_throttle():
    auth._recent_failures.clear()
    yield
    auth._recent_failures.clear()


@pytest.fixture
def open_client(tmp_path):
    """No KANBAN_PASSWORD: the gate is a no-op, exactly as before login existed."""
    app = create_app(tmp_path)
    c = app.test_client()
    c.get("/")  # creates the default board
    return c


@pytest.fixture
def locked_client(tmp_path):
    app = create_app(tmp_path, password="right-horse-battery")
    c = app.test_client()
    return c


def _login(client, password="right-horse-battery", next_="/"):
    return client.post("/login", data={"password": password, "next": next_})


def _login_and_create_board(client):
    """The default board is created lazily by GET / (routes.index), which the auth gate blocks
    until you're logged in -- so tests that need "my-board" to exist must log in first."""
    _login(client)
    client.get("/")


# ---- localhost mode: password unset, nothing changes ------------------------------------------

def test_no_password_means_every_route_stays_open(open_client):
    assert open_client.get("/").status_code == 302  # -> /b/my-board, not /login
    assert open_client.get("/b/my-board").status_code == 200
    assert open_client.post("/b/my-board/cards", data={"title": "x", "column": "Todo"}).status_code == 200


def test_no_password_means_no_login_route_and_no_logout_button(open_client):
    assert open_client.get("/login").status_code == 404
    assert "Log out" not in open_client.get("/b/my-board").text


# ---- LAN mode: password set -------------------------------------------------------------------

def test_unauthenticated_get_redirects_to_login(locked_client):
    r = locked_client.get("/b/my-board")
    assert r.status_code == 302 and "/login" in r.headers["Location"]


def test_unauthenticated_write_gets_401_not_a_redirect(locked_client):
    r = locked_client.post("/b/my-board/cards", data={"title": "x", "column": "Todo"})
    assert r.status_code == 401


def test_health_and_static_stay_open_without_login(locked_client):
    assert locked_client.get("/api/health").status_code == 200
    assert locked_client.get("/static/app.css").status_code == 200


def test_wrong_password_is_rejected_and_leaves_you_logged_out(locked_client):
    r = _login(locked_client, password="nope")
    assert r.status_code == 401 and "Wrong password" in r.text
    assert locked_client.get("/b/my-board").status_code == 302  # still not authenticated


def test_correct_password_logs_in_and_session_persists(locked_client):
    r = _login(locked_client)
    assert r.status_code == 302
    locked_client.get("/")  # now authenticated: creates the default board
    assert locked_client.get("/b/my-board").status_code == 200  # cookie carried the session


def test_next_redirects_back_to_the_originally_requested_page(locked_client):
    first = locked_client.get("/b/my-board")
    next_path = parse_qs(urlparse(first.headers["Location"]).query)["next"][0]
    assert next_path == "/b/my-board"
    r = _login(locked_client, next_=next_path)
    assert r.headers["Location"] == next_path


def test_open_redirect_is_rejected(locked_client):
    r = _login(locked_client, next_="//evil.example/steal")
    assert r.headers["Location"] == "/"  # falls back to home (boards.index), not the crafted target


def test_logout_clears_the_session(locked_client):
    _login_and_create_board(locked_client)
    assert locked_client.get("/b/my-board").status_code == 200
    locked_client.post("/logout")
    assert locked_client.get("/b/my-board").status_code == 302


def test_login_is_throttled_after_repeated_failures(locked_client):
    for _ in range(auth.MAX_FAILURES):
        assert _login(locked_client, password="nope").status_code == 401
    r = _login(locked_client)  # correct password, but too many recent failures
    assert r.status_code == 429


def test_logout_button_shown_only_when_a_password_is_set(locked_client):
    _login_and_create_board(locked_client)
    assert "Log out" in locked_client.get("/b/my-board").text
