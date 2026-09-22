import re

from playwright.sync_api import expect

LOGIN_URL = re.compile(r"/login")


def test_visiting_a_board_while_logged_out_redirects_to_login(auth_page):
    auth_page.goto(auth_page.base + "/b/my-board")
    expect(auth_page).to_have_url(LOGIN_URL)
    expect(auth_page.locator(".login-card")).to_be_visible()


def test_wrong_password_shows_an_error_and_stays_logged_out(auth_page):
    auth_page.expected_errors.append("status of 401")      # the refused password is the point
    auth_page.fill('input[name="password"]', "not-it")
    auth_page.click('button:has-text("Log in")')
    expect(auth_page.locator(".login-card .error")).to_contain_text("Wrong password")
    auth_page.goto(auth_page.base + "/b/my-board")
    expect(auth_page).to_have_url(LOGIN_URL)  # still gated


def test_correct_password_logs_in_and_shows_the_board(auth_page):
    auth_page.fill('input[name="password"]', "right-horse-battery")
    auth_page.click('button:has-text("Log in")')
    expect(auth_page.locator(".board, .tasks-board")).to_be_visible()
    expect(auth_page.get_by_role("button", name="Log out")).to_be_visible()


def test_log_out_ends_the_session(auth_page):
    auth_page.fill('input[name="password"]', "right-horse-battery")
    auth_page.click('button:has-text("Log in")')
    expect(auth_page.locator(".board, .tasks-board")).to_be_visible()
    auth_page.get_by_role("button", name="Log out").click()
    expect(auth_page.locator(".login-card")).to_be_visible()
    auth_page.goto(auth_page.base + "/b/my-board")
    expect(auth_page).to_have_url(LOGIN_URL)  # gated again
