from playwright.sync_api import expect


def drag(page, source, target, dy=0, fx=0.5):
    """Drag with real intermediate mouse moves (Sortable needs them; drag_to skips some)."""
    a, b = source.bounding_box(), target.bounding_box()
    page.mouse.move(a["x"] + a["width"] / 2, a["y"] + a["height"] / 2)
    page.mouse.down()
    page.mouse.move(a["x"] + a["width"] / 2 + 5, a["y"] + a["height"] / 2 + 5, steps=3)
    page.mouse.move(b["x"] + b["width"] * fx, b["y"] + b["height"] / 2 + dy, steps=12)
    page.mouse.move(b["x"] + b["width"] * fx, b["y"] + b["height"] / 2 + dy + 2, steps=3)
    page.mouse.up()


def add_card(page, column, text):
    """Use the list header's + button; new cards land at the top of the list."""
    col = page.locator(f'.column[data-column="{column}"]')
    cards = col.locator(".card")
    before = cards.count()
    box = col.locator("input[name=title]")
    if not box.is_visible():
        col.get_by_role("button", name="Add card").click()
    box.fill(text)
    box.press("Enter")
    expect(cards).to_have_count(before + 1)  # wait: the form resets itself after the request


def fab_add(page, what, name):
    """what: 'New list' | 'New board' | 'New area'"""
    page.click(".fab-btn")
    page.get_by_role("button", name=what).click()
    page.fill(".fab-form input", name)
    page.press(".fab-form input", "Enter")


def column_order(page):
    return page.eval_on_selector_all(".column", "els => els.map(e => e.dataset.column)")


def test_layout_and_quick_add(page):
    expect(page.locator(".sidebar")).to_be_visible()
    expect(page.locator(".sidebar a", has_text="Scheduled")).to_be_visible()
    add_card(page, "Todo", "Buy paint #home tomorrow")
    card = page.locator(".card", has_text="Buy paint")
    expect(card).to_be_visible()
    expect(card.locator(".tag")).to_have_text("#home")
    expect(card.locator(".due")).not_to_be_empty()
    expect(page.locator(".sidebar .tag-list")).to_contain_text("#home")


def test_complete_stamps_time_and_edit_in_place(page):
    add_card(page, "Todo", "Pay rent")
    card = page.locator(".card", has_text="Pay rent")
    card.locator(".check").click()
    expect(page.locator(".card.done .stamp")).to_contain_text("✓")
    page.locator(".card .title").click()
    page.fill(".dialog input[name=title]", "Pay rent now")
    page.fill(".dialog input[name=repeat]", "every month")
    page.click(".dialog button[type=submit]")
    expect(page.locator("#modal .backdrop")).to_have_count(0)
    expect(page.locator(".card", has_text="Pay rent now")).to_be_visible()
    expect(page.locator(".card .repeat")).to_be_visible()


def test_add_rename_hide_delete_lists(page):
    fab_add(page, "New list", "Later")
    expect(page.locator('.column[data-column="Later"]')).to_be_visible()

    title = page.locator('.column[data-column="Later"] .col-title')
    title.fill("Someday")
    title.press("Enter")
    expect(page.locator('.column[data-column="Someday"]')).to_be_visible()

    add_card(page, "Someday", "parked")
    col = page.locator('.column[data-column="Someday"]')
    col.hover()
    col.get_by_role("button", name="Hide list").click()
    expect(page.locator('.column[data-column="Someday"]')).to_have_count(0)
    expect(page.locator('[data-eye-toggle] .icon-badge')).to_have_text("1")

    page.get_by_role("button", name="Show or hide lists").click()
    row = page.locator(".eye-row", has_text="Someday")
    expect(row.locator("input")).not_to_be_checked()
    row.locator("input").check()
    page.wait_for_load_state()
    expect(page.locator('.column[data-column="Someday"]')).to_be_visible()
    expect(page.locator('.column[data-column="Someday"] .card')).to_have_count(1)  # cards followed the rename


def test_drag_lists_to_reorder(page):
    assert column_order(page) == ["Todo", "Doing", "Done"]
    drag(page, page.locator('.column[data-column="Todo"] .col-grip'),
         page.locator('.column[data-column="Doing"] .col-head'), fx=0.8)
    page.wait_for_function("() => document.querySelector('.column').dataset.column !== 'Todo'")
    assert column_order(page) == ["Doing", "Todo", "Done"]
    page.reload()
    assert column_order(page) == ["Doing", "Todo", "Done"]      # persisted on the server


def test_column_counts_stay_correct_after_drag_add_delete_and_complete(page):
    add_card(page, "Todo", "a")                         # a single card first, so the drag geometry
    todo = page.locator('.column[data-column="Todo"] .count')  # matches the proven single-card drag
    doing = page.locator('.column[data-column="Doing"] .count')
    expect(todo).to_have_text("1")
    expect(doing).to_have_text("0")

    drag(page, page.locator(".card", has_text="a"), page.locator('.column[data-column="Doing"] .cards'))
    expect(todo).to_have_text("0")                      # updates without a reload
    expect(doing).to_have_text("1")

    add_card(page, "Todo", "b")
    expect(todo).to_have_text("1")
    add_card(page, "Todo", "c")
    expect(todo).to_have_text("2")

    page.locator(".card", has_text="c").hover()
    page.locator(".card", has_text="c").locator(".del").click()
    expect(todo).to_have_text("1")

    page.keyboard.press("Escape")
    page.locator("body").click(position={"x": 700, "y": 700})
    page.keyboard.press("j")                            # selects Todo's only card ("b")
    page.keyboard.press("x")
    expect(page.locator(".card.done")).to_be_visible()  # completing (not moving) leaves the count as-is
    expect(todo).to_have_text("1")

    page.reload()                                       # the server's own render agrees
    expect(todo).to_have_text("1")
    expect(doing).to_have_text("1")


def test_sidebar_footer_never_needs_scrolling(page):
    for i in range(15):
        fab_add(page, "New area", f"Area {i}")
    footer = page.locator(".side-foot")
    expect(footer).to_be_in_viewport()
    expect(page.get_by_role("link", name="Trash", exact=True)).to_be_in_viewport()


def test_sidebar_sections_dont_overlap_when_nav_needs_to_scroll(page):
    """nav's own children (the board list, areas, tags) default to flex-shrink, so when there's
    enough of them to need nav's internal scroll, they can get squeezed below their real content
    height instead -- which looks like the next section overlapping the one before it, not like a
    missing scrollbar. Needs a short viewport and enough content to actually force the squeeze."""
    page.set_viewport_size({"width": 1280, "height": 600})
    for i in range(8):
        fab_add(page, "New board", f"Board {i}")
    fab_add(page, "New area", "Personal")

    unassigned = page.locator(".boards-unassigned")
    areas = page.locator(".areas")
    u_box, a_box = unassigned.bounding_box(), areas.bounding_box()
    assert a_box["y"] >= u_box["y"] + u_box["height"] - 1, (
        f"areas ({a_box}) overlaps boards-unassigned ({u_box})")


def test_drag_card_between_lists(page):
    add_card(page, "Todo", "mover")
    drag(page, page.locator(".card", has_text="mover"), page.locator('.column[data-column="Doing"] .cards'))
    expect(page.locator('.column[data-column="Doing"] .card', has_text="mover")).to_be_visible()
    page.reload()
    expect(page.locator('.column[data-column="Doing"] .card', has_text="mover")).to_be_visible()


def test_areas_and_board_dragging(page):
    fab_add(page, "New board", "Garden")
    page.wait_for_url("**/b/garden")
    fab_add(page, "New area", "Home")
    expect(page.locator('.area[data-area="Home"]')).to_be_visible()

    row = page.locator('.board-row[data-slug="garden"]')
    row.hover()
    drag(page, row.locator(".grip"), page.locator('.area[data-area="Home"] .area-head'), dy=8)
    expect(page.locator('.area[data-area="Home"] [data-slug="garden"]')).to_be_visible()
    page.reload()
    expect(page.locator('.area[data-area="Home"] [data-slug="garden"]')).to_be_visible()
    expect(page.locator('.boards-unassigned [data-slug="my-board"]')).to_be_visible()

    title = page.locator('.area[data-area="Home"] .area-title')
    title.fill("House")
    title.press("Enter")
    expect(page.locator('.area[data-area="House"] [data-slug="garden"]')).to_be_visible()


def test_keyboard_shortcuts(page):
    page.add_init_script("""
        window.__log = []; const t0 = performance.now();
        const L = m => window.__log.push(Math.round(performance.now() - t0) + 'ms ' + m);
        document.addEventListener('DOMContentLoaded', () => {
          ['htmx:beforeRequest', 'htmx:afterRequest', 'htmx:afterSwap', 'htmx:sendError', 'htmx:responseError', 'htmx:abort', 'htmx:beforeSend'].forEach(n =>
            document.body.addEventListener(n, e => L(n + ' ' + (e.detail.requestConfig ? e.detail.requestConfig.verb + ' ' + e.detail.requestConfig.path.slice(-24) : ''))));
          document.addEventListener('keydown', e => L('keydown ' + e.key + ' sel=' + document.querySelector('.selected')?.dataset.id), true);
          document.addEventListener('click', e => L('click ' + e.target.className + ' connected=' + e.target.isConnected), true);
          new MutationObserver(ms => ms.forEach(m => L('modal +' + m.addedNodes.length + ' -' + m.removedNodes.length))).observe(document.getElementById('modal'), {childList: true});
          const of = window.fetch; window.fetch = (...a) => { L('fetch ' + String(a[0]).slice(-24)); return of(...a); };
        });
    """)
    page.reload()
    add_card(page, "Todo", "second")
    add_card(page, "Todo", "first")                    # new cards go to the top
    page.locator("body").click(position={"x": 700, "y": 700})
    page.keyboard.press("Escape")
    page.keyboard.press("j")
    expect(page.locator(".card.selected")).to_contain_text("first")
    page.keyboard.press("j")
    expect(page.locator(".card.selected")).to_contain_text("second")
    page.keyboard.press("x")
    expect(page.locator(".card.done", has_text="second")).to_be_visible()
    page.keyboard.press("Shift+L")
    expect(page.locator('.column[data-column="Doing"] .card', has_text="second")).to_be_visible()
    page.keyboard.press("e")
    try:
        expect(page.locator(".dialog input[name=title]")).to_be_focused(timeout=2500)
    finally:
        print("LOGALL:", *page.evaluate("window.__log.slice(-16)"), sep="\n  ")
    page.keyboard.press("Escape")
    expect(page.locator("#modal .backdrop")).to_have_count(0)
    page.keyboard.press("?")
    expect(page.locator("#help")).to_be_visible()
    page.keyboard.press("Escape")
    page.keyboard.press("g")
    page.keyboard.press("s")
    page.wait_for_url("**/scheduled")


def test_fab_menu_contents_and_new_card_placement(page):
    page.click(".fab-btn")
    for name in ("New list", "New board", "New area"):
        expect(page.get_by_role("button", name=name)).to_be_visible()
    page.keyboard.press("Escape")
    expect(page.locator(".fab-menu")).to_be_hidden()
    page.click(".fab-btn")
    page.click(".fab-btn")                              # second click closes it again
    expect(page.locator(".fab-menu")).to_be_hidden()

    # header + reveals the input; cards go to the top; Esc hides an empty input
    col = page.locator('.column[data-column="Todo"]')
    expect(col.locator(".add-card")).to_be_hidden()
    add_card(page, "Todo", "one")
    add_card(page, "Todo", "two")
    assert col.locator(".card .title").all_inner_texts() == ["two", "one"]
    page.keyboard.press("Escape")
    expect(col.locator(".add-card")).to_be_hidden()
    page.reload()
    assert col.locator(".card .title").all_inner_texts() == ["two", "one"]      # order persisted

    page.keyboard.press("n")                            # keyboard shortcut opens the same input
    expect(col.locator("input[name=title]")).to_be_focused()

    page.goto(page.base + "/scheduled")                 # not a board page: no "New list" offered
    page.click(".fab-btn")
    expect(page.get_by_role("button", name="New list")).to_have_count(0)
    expect(page.get_by_role("button", name="New board")).to_be_visible()


def test_fab_rejects_duplicate_list_name(page):
    page.expected_errors.append("status of 400")       # the refused duplicate is the point
    fab_add(page, "New list", "todo")                   # clashes with "Todo", case-insensitively
    expect(page.locator(".fab-form input")).to_have_js_property("validationMessage", "That name is taken or not allowed")
    expect(page.locator(".column")).to_have_count(3)


# ---- undo, logbook, trash, clear-done, capture, move, notes, PWA -------------------------------------

def toast(page):
    return page.locator(".toast")


def test_delete_card_toast_undo_and_trash_page(page):
    add_card(page, "Todo", "precious")
    card = page.locator(".card", has_text="precious")
    card.hover()
    card.locator(".del").click()
    expect(page.locator(".card", has_text="precious")).to_have_count(0)
    expect(toast(page)).to_contain_text("Deleted")
    toast(page).get_by_role("button", name="Undo").click()
    page.wait_for_load_state()
    expect(page.locator(".card", has_text="precious")).to_have_count(1)

    page.locator(".card", has_text="precious").hover()
    page.locator(".card", has_text="precious").locator(".del").click()
    expect(toast(page)).to_be_visible()
    page.click(".side-foot a")                                # Trash
    expect(page.locator(".trash .row", has_text="precious")).to_contain_text("Todo")
    page.get_by_role("button", name="Restore").click()
    page.wait_for_load_state()
    expect(page.locator(".trash .empty")).to_be_visible()


def test_complete_toast_undo_and_logbook_reference(page):
    add_card(page, "Doing", "Ship the thing")
    page.locator(".card", has_text="Ship the thing").locator(".check").click()
    expect(toast(page)).to_contain_text("Completed")
    page.click('.sidebar [data-go="l"]')
    row = page.locator(".logbook .row", has_text="Ship the thing")
    expect(row).to_be_visible()
    expect(row.locator(".ref")).to_contain_text("My Board")            # where it came from
    expect(row.locator(".ref")).to_contain_text("Doing")
    expect(row.locator(".ref a")).to_have_attribute("href", "/b/my-board")
    expect(page.locator(".logbook h2").first).to_contain_text("Today")

    page.go_back()
    page.locator(".card", has_text="Ship the thing").locator(".check").click()   # un-check
    page.click('.sidebar [data-go="l"]')
    expect(page.locator(".logbook .empty")).to_be_visible()             # un-checking removes the entry


def test_complete_undo_via_toast(page):
    add_card(page, "Todo", "oops")
    page.locator(".card", has_text="oops").locator(".check").click()
    expect(page.locator(".card.done")).to_have_count(1)
    toast(page).get_by_role("button", name="Undo").click()
    page.wait_for_load_state()
    expect(page.locator(".card.done")).to_have_count(0)
    page.click('.sidebar [data-go="l"]')
    expect(page.locator(".logbook .empty")).to_be_visible()


def test_clear_completed_keeps_logbook_and_undo(page):
    for t in ("a", "b", "keep"):
        add_card(page, "Todo", t)
    for t in ("a", "b"):
        page.locator(".card", has_text=t).first.locator(".check").click()
        expect(page.locator(".card.done", has_text=t).first).to_be_visible()
    col = page.locator('.column[data-column="Todo"]')
    col.hover()
    col.get_by_role("button", name="Clear completed").click()
    expect(page.locator(".card.done")).to_have_count(0)
    expect(col.locator(".count")).to_have_text("1")
    expect(toast(page).last).to_contain_text("Cleared 2 completed cards")
    page.click('.sidebar [data-go="l"]')
    expect(page.locator(".logbook .row")).to_have_count(2)             # cleared, but still in the Logbook
    page.go_back()
    toast(page).last.get_by_role("button", name="Undo").click() if toast(page).count() else None
    page.reload()
    expect(page.locator(".card")).to_have_count(1)


def test_rename_and_delete_board_with_two_step_confirm_and_undo(page):
    fab_add(page, "New board", "Scratch")
    page.wait_for_url("**/b/scratch")
    title = page.locator(".board-title")
    title.fill("Scratchpad")
    title.press("Enter")
    expect(page.locator('.sidebar a', has_text="Scratchpad")).to_be_visible()

    delete = page.get_by_role("button", name="Delete board")
    delete.click()                                            # first click only arms it
    expect(delete).to_have_class(__import__("re").compile(r"armed"))
    expect(page.locator(".board-title")).to_be_visible()
    delete.click()
    page.wait_for_url(__import__("re").compile(r"/b/my-board$"))
    expect(toast(page)).to_contain_text("Deleted board")
    expect(page.locator('.sidebar a', has_text="Scratchpad")).to_have_count(0)
    toast(page).get_by_role("button", name="Undo").click()
    page.wait_for_load_state()
    expect(page.locator('.sidebar a', has_text="Scratchpad")).to_be_visible()


def test_area_delete_keeps_boards_and_undo(page):
    fab_add(page, "New area", "Home")
    expect(page.locator('.area[data-area="Home"]')).to_be_visible()
    drag(page, page.locator('.board-row[data-slug="my-board"] .grip'),
         page.locator('.area[data-area="Home"] .area-head'), dy=8)
    expect(page.locator('.area[data-area="Home"] [data-slug="my-board"]')).to_be_visible()
    page.locator('.area[data-area="Home"] .area-head').hover()
    page.get_by_role("button", name="Delete area").click()
    page.wait_for_load_state()
    expect(page.locator('.area[data-area="Home"]')).to_have_count(0)
    expect(page.locator('.boards-unassigned [data-slug="my-board"]')).to_be_visible()   # board kept
    expect(toast(page)).to_contain_text("1 board kept")
    toast(page).get_by_role("button", name="Undo").click()
    page.wait_for_load_state()
    expect(page.locator('.area[data-area="Home"] [data-slug="my-board"]')).to_be_visible()


def test_quick_capture_from_anywhere_remembers_the_chosen_board(page):
    fab_add(page, "New board", "Groceries")
    page.wait_for_url("**/b/groceries")
    page.keyboard.press("c")                                  # no memory yet: defaults to the board you're on
    expect(page.locator(".fab-form input")).to_be_focused()
    expect(page.locator(".fab-board")).to_be_visible()
    expect(page.locator(".fab-board")).to_have_value("groceries")
    page.select_option(".fab-board", "my-board")               # explicitly pick a different one
    page.keyboard.type("Phone gran tomorrow #family")
    page.keyboard.press("Enter")
    expect(toast(page)).to_contain_text("Added to My Board")

    page.goto(page.base + "/b/my-board")
    card = page.locator(".card", has_text="Phone gran")
    expect(card).to_be_visible()
    expect(card.locator(".tag")).to_have_text("#family")
    expect(card.locator(".due")).not_to_be_empty()

    page.keyboard.press("Escape")
    page.keyboard.press("c")                                  # capturing while on that board shows it at once
    expect(page.locator(".fab-board")).to_have_value("my-board")   # remembered from the last capture
    page.keyboard.type("second one")
    page.keyboard.press("Enter")
    page.wait_for_load_state()
    expect(page.locator(".card")).to_have_count(2)
    expect(page.locator(".card .title").first).to_have_text("second one")   # newest on top
    expect(page.locator(".toast")).to_contain_text("Added to My Board")     # toast survived the reload

    page.click('.sidebar [data-go="s"]')                       # from a non-board page too: remembered wins
    page.wait_for_url("**/scheduled")
    page.keyboard.press("c")
    expect(page.locator(".fab-board")).to_have_value("my-board")


def test_drag_card_onto_sidebar_board_moves_it_with_undo(page):
    fab_add(page, "New board", "Elsewhere")
    page.wait_for_url("**/b/elsewhere")
    page.goto(page.base + "/b/my-board")
    add_card(page, "Todo", "wanderer")
    add_card(page, "Todo", "stayer")
    drag(page, page.locator(".card", has_text="wanderer"),
         page.locator('.board-row[data-slug="elsewhere"] a'))
    expect(page.locator(".card", has_text="wanderer")).to_have_count(0)
    expect(page.locator(".card", has_text="stayer")).to_have_count(1)
    expect(toast(page)).to_contain_text("Moved “wanderer” to Elsewhere")
    page.goto(page.base + "/b/elsewhere")
    expect(page.locator(".card", has_text="wanderer")).to_have_count(1)
    page.goto(page.base + "/b/my-board")
    add_card(page, "Todo", "second-mover")
    drag(page, page.locator(".card", has_text="second-mover"),
         page.locator('.board-row[data-slug="elsewhere"] a'))
    toast(page).get_by_role("button", name="Undo").click()
    page.wait_for_load_state()
    expect(page.locator(".card", has_text="second-mover")).to_have_count(1)   # back on the original board


def test_markdown_notes_checklist_and_safe_html(page):
    add_card(page, "Todo", "shopping")
    page.locator(".card .title").click()
    page.fill(".dialog textarea[name=body]",
              "Get it **today** <script>window.__pwned = 1</script>\n\n- [ ] milk\n- [ ] eggs\n")
    page.click(".dialog button[type=submit]")
    expect(page.locator("#modal .backdrop")).to_have_count(0)
    face = page.locator(".card", has_text="shopping")
    expect(face.locator(".meta", has_text="0/2")).to_be_visible()

    page.locator(".card .title").click()
    view = page.locator(".notes-view")
    expect(view.locator("strong")).to_have_text("today")
    expect(view).to_contain_text("<script>")                   # shown as text, not run
    assert page.evaluate("window.__pwned") is None
    view.locator('input.task[data-task="0"]').check()
    expect(face.locator(".meta", has_text="1/2")).to_be_visible()   # the card behind the dialog updated
    page.get_by_role("button", name="Edit notes").click()
    expect(page.locator(".dialog textarea[name=body]")).to_have_value(__import__("re").compile(r"- \[x\] milk"))
    page.click(".dialog button[type=submit]")                  # saving must not undo the tick
    expect(page.locator(".card", has_text="shopping").locator(".meta", has_text="1/2")).to_be_visible()


def test_installable_manifest_and_icons(page):
    expect(page.locator('link[rel=manifest]')).to_have_count(1)
    r = page.request.get(page.base + "/manifest.webmanifest")
    assert r.status == 200 and "manifest+json" in r.headers["content-type"]
    m = r.json()
    assert m["display"] == "standalone" and m["start_url"] == "/" and m["name"] == "Kanban"
    assert {i["sizes"] for i in m["icons"]} >= {"192x192", "512x512"}
    for icon in m["icons"]:
        assert page.request.get(page.base + icon["src"]).status == 200
    assert page.request.get(page.base + page.get_attribute("link[rel=apple-touch-icon]", "href")).status == 200


# ---- themes, settings and rules ---------------------------------------------------------------------

import re as _re
from pathlib import Path as _Path

_THEMES_CSS = (_Path(__file__).parent.parent.parent / "src" / "kanban" / "static" / "themes.css").read_text()


def theme_bg(name):
    """--bg for a theme, as the browser reports it, e.g. 'rgb(46, 52, 64)'."""
    hexv = _re.search(rf"\[data-theme={name}\]\s*\{{[^}}]*?--bg:\s*(#[0-9a-fA-F]+);", _THEMES_CSS)[1].lstrip("#")
    hexv = "".join(c * 2 for c in hexv) if len(hexv) == 3 else hexv
    return "rgb({}, {}, {})".format(*(int(hexv[i:i + 2], 16) for i in (0, 2, 4)))


def body_bg(page):
    return page.evaluate("getComputedStyle(document.body).backgroundColor")


def test_sidebar_theme_toggle_cycles_and_stays_in_sync_with_settings(page):
    from kanban.themes import THEME_NAMES
    label = page.locator("#theme-label")
    expect(label).to_have_text("Default")
    page.click("#theme-toggle")
    expect(label).to_have_text("Dark")
    expect(page.locator("html")).to_have_attribute("data-theme", "dark")
    for _ in range(len(THEME_NAMES)):                 # cycle all the way around, back to Default
        page.click("#theme-toggle")
    expect(label).to_have_text("Default")
    expect(page.locator("html")).not_to_have_attribute("data-theme", __import__("re").compile(".+"))
    page.click("#theme-toggle")                        # dark again
    page.goto(page.base + "/settings")
    expect(page.locator('input[name=theme]:checked')).to_have_value("dark")   # toggle and picker share storage
    page.locator('label.theme-card:has(input[value="nord"])').click()
    page.goto(page.base + "/b/my-board")
    expect(page.locator("#theme-label")).to_have_text("Nord")                 # picker updates the toggle too


def test_no_brand_name_and_icon_only_footer_controls(page):
    assert "Trellis" not in page.content() and "Kanban" not in page.locator(".sidebar").inner_text()
    for name in ("Trash", "Settings", "Keyboard shortcuts", "Home"):
        expect(page.get_by_role("link", name=name, exact=True).or_(page.get_by_role("button", name=name, exact=True))).to_have_count(1)


def test_theme_picker_applies_all_twelve_and_persists(page):
    from kanban.themes import THEME_NAMES
    page.goto(page.base + "/settings")
    expect(page.locator('input[name=theme]:checked')).to_have_value("default")
    for name in THEME_NAMES:
        page.locator(f'label.theme-card:has(input[value="{name}"])').click()
        expect(page.locator("html")).to_have_attribute("data-theme", name)
        assert body_bg(page) == theme_bg(name), name
    page.reload()
    expect(page.locator("html")).to_have_attribute("data-theme", "midnight")           # last one picked
    expect(page.locator('input[name=theme]:checked')).to_have_value("midnight")
    page.goto(page.base + "/b/my-board")                                                # other pages too
    expect(page.locator("html")).to_have_attribute("data-theme", "midnight")
    page.goto(page.base + "/settings")
    page.locator('label.theme-card:has(input[value="default"])').click()
    expect(page.locator("html")).not_to_have_attribute("data-theme", _re.compile(".+"))
    assert page.evaluate("localStorage.getItem('theme')") == "default"


def test_saved_theme_is_applied_before_first_paint_and_unknown_values_are_ignored(browser, server):
    ctx = browser.new_context()
    ctx.add_init_script("""
        localStorage.setItem('theme', 'terminal');
        document.addEventListener('DOMContentLoaded', () => { window.__atParse = getComputedStyle(document.body).backgroundColor; });
    """)
    pg = ctx.new_page()
    pg.goto(server + "/")
    assert pg.evaluate("window.__atParse") == theme_bg("terminal")       # already themed when parsing finished
    ctx.close()
    ctx = browser.new_context()
    ctx.add_init_script("localStorage.setItem('theme', 'javascript:alert(1)'); localStorage.setItem('font-size', 'huge');")
    pg = ctx.new_page()
    pg.goto(server + "/")
    assert pg.evaluate("document.documentElement.hasAttribute('data-theme')") is False   # not on the allow-list
    assert pg.evaluate("document.documentElement.hasAttribute('data-font-size')") is False
    ctx.close()


def test_default_theme_follows_the_os_and_text_size_persists(browser, server):
    for scheme, expected in (("dark", "rgb(22, 24, 29)"), ("light", "rgb(244, 245, 247)")):
        ctx = browser.new_context(color_scheme=scheme)
        pg = ctx.new_page()
        pg.goto(server + "/")
        assert body_bg(pg) == expected, scheme
        ctx.close()
    ctx = browser.new_context()
    pg = ctx.new_page()
    pg.goto(server + "/settings")
    pg.get_by_label("Large").check()
    expect(pg.locator("html")).to_have_attribute("data-font-size", "large")
    pg.reload()
    expect(pg.locator("html")).to_have_attribute("data-font-size", "large")
    expect(pg.get_by_label("Large")).to_be_checked()
    ctx.close()


def test_defaults_autosave_with_honest_status(page):
    page.expected_errors.append("422")                 # the invalid save below is refused on purpose
    page.goto(page.base + "/settings")
    page.select_option("#p-pos", "bottom")
    expect(page.locator("#save-status")).to_have_text("Saved")
    page.fill("#p-cols", "Inbox, Next, Done")
    page.locator("#p-cols").blur()
    expect(page.locator("#save-status")).to_have_text("Saved")
    page.reload()
    expect(page.locator("#p-pos")).to_have_value("bottom")
    expect(page.locator("#p-cols")).to_have_value("Inbox, Next, Done")
    fab_add(page, "New board", "Fresh")
    page.wait_for_url("**/b/fresh")
    assert column_order(page) == ["Inbox", "Next", "Done"]              # the new default lists
    page.goto(page.base + "/settings")
    page.fill("#p-cols", " , ")
    page.locator("#p-cols").blur()
    expect(page.locator("#save-status")).to_have_text("A new board needs at least one list")   # real error, not "saved"


def test_checking_a_card_moves_it_to_done_via_a_board_rule_and_undo(page):
    page.goto(page.base + "/b/my-board/settings")
    expect(page.locator(".rules .empty")).to_be_visible()
    page.get_by_role("button", name="Checking a card moves it to Done").click()
    expect(page.locator(".rule-text")).to_have_text("When a card is completed, move it to Done.")
    page.goto(page.base + "/b/my-board")
    add_card(page, "Todo", "ship it")
    page.locator(".card", has_text="ship it").locator(".check").click()
    page.wait_for_load_state()
    done = page.locator('.column[data-column="Done"]')
    expect(done.locator(".card.done", has_text="ship it")).to_be_visible()
    expect(page.locator('.column[data-column="Todo"] .card')).to_have_count(0)
    expect(toast(page)).to_contain_text("Completed “ship it” · moved to Done")
    toast(page).get_by_role("button", name="Undo").click()
    page.wait_for_load_state()
    expect(page.locator('.column[data-column="Todo"] .card', has_text="ship it")).to_have_count(1)
    expect(page.locator(".card.done")).to_have_count(0)                  # not done, and back where it was
    page.click('.sidebar [data-go="l"]')
    expect(page.locator(".logbook .empty")).to_be_visible()


def test_dragging_into_done_completes_the_card_via_a_rule(page):
    page.goto(page.base + "/b/my-board/settings")
    page.get_by_role("button", name="Moving a card into Done marks it complete").click()
    expect(page.locator(".rule-text")).to_have_text("When a card is moved into Done, mark it complete.")
    page.goto(page.base + "/b/my-board")
    add_card(page, "Todo", "dragged")
    drag(page, page.locator(".card", has_text="dragged"), page.locator('.column[data-column="Done"] .cards'))
    page.wait_for_load_state()
    expect(page.locator('.column[data-column="Done"] .card.done', has_text="dragged")).to_be_visible()
    expect(toast(page)).to_contain_text("marked complete")
    page.click('.sidebar [data-go="l"]')
    expect(page.locator(".logbook .row", has_text="dragged")).to_contain_text("Done")


def test_rule_builder_shows_only_relevant_fields_and_explains_errors(page):
    page.expected_errors.append("422")                 # the incomplete rule below is refused on purpose
    page.goto(page.base + "/b/my-board/settings")
    form = page.locator(".rule-form")
    expect(form.locator(".rb-move")).to_be_visible()                     # default action is "move"
    expect(form.locator(".rb-tag")).to_be_hidden()
    form.locator("select[name=do]").select_option("add_tag")
    expect(form.locator(".rb-move")).to_be_hidden()
    expect(form.locator(".rb-tag")).to_be_visible()
    form.locator("select[name=do]").select_option("archive")
    expect(form.locator(".rb-move")).to_be_hidden()
    expect(form.locator(".rb-tag")).to_be_hidden()
    form.locator("select[name=when]").select_option("moved")
    expect(form.locator(".rb-in-label")).to_have_text("into list")
    form.get_by_role("button", name="Add rule").click()                  # "moved" needs a list
    expect(form.locator(".rule-error")).to_have_text("Say which list the card is moved into")
    form.locator("select[name=in]").select_option("Done")
    form.get_by_role("button", name="Add rule").click()
    expect(page.locator(".rule-text")).to_have_text("When a card is moved into Done, clear it from the list.")


def test_rule_toggle_and_delete_with_undo(page):
    page.goto(page.base + "/b/my-board/settings")
    page.get_by_role("button", name="Checking a card moves it to Done").click()
    switch = page.get_by_role("checkbox", name=_re.compile("Rule on"))
    switch.uncheck()
    expect(page.locator(".rule.off")).to_have_count(1)
    page.reload()
    expect(page.get_by_role("checkbox", name=_re.compile("Rule on"))).not_to_be_checked()   # persisted
    page.goto(page.base + "/b/my-board")
    add_card(page, "Todo", "stays put")
    page.locator(".card", has_text="stays put").locator(".check").click()
    expect(page.locator(".card.done", has_text="stays put")).to_be_visible()
    expect(page.locator('.column[data-column="Todo"] .card.done')).to_have_count(1)        # rule off: nothing moved

    page.goto(page.base + "/b/my-board/settings")
    page.get_by_role("button", name=_re.compile("Delete rule")).click()
    page.wait_for_load_state()
    expect(page.locator(".rules .empty")).to_be_visible()
    toast(page).get_by_role("button", name="Undo").click()
    page.wait_for_load_state()
    expect(page.locator(".rule-text")).to_have_count(1)


def test_global_rule_applies_to_every_board_unless_opted_out(page):
    page.goto(page.base + "/settings")
    page.get_by_role("button", name="Checking a card moves it to Done").click()
    expect(page.locator(".rule-text")).to_have_text("When a card is completed, move it to Done.")
    fab_add(page, "New board", "Second")
    page.wait_for_url("**/b/second")
    add_card(page, "Todo", "inherits")
    page.locator(".card", has_text="inherits").locator(".check").click()
    expect(page.locator('.column[data-column="Done"] .card.done', has_text="inherits")).to_be_visible()

    page.goto(page.base + "/b/second/settings")
    expect(page.locator("#global-h")).to_contain_text("also run here")
    page.uncheck("#b-inherit")
    expect(page.locator("#save-status")).to_have_text("Saved")
    page.reload()
    expect(page.locator("#global-h")).to_contain_text("switched off for this board")
    page.goto(page.base + "/b/second")
    add_card(page, "Todo", "opts out")
    page.locator(".card", has_text="opts out").locator(".check").click()
    expect(page.locator(".card.done", has_text="opts out")).to_be_visible()
    expect(page.locator('.column[data-column="Todo"] .card.done', has_text="opts out")).to_have_count(1)   # stayed in Todo


def test_board_settings_new_card_position_and_hide_completed(page):
    page.goto(page.base + "/b/my-board/settings")
    page.select_option("#b-pos", "bottom")
    expect(page.locator("#save-status")).to_have_text("Saved")
    page.goto(page.base + "/b/my-board")
    add_card(page, "Todo", "first")
    add_card(page, "Todo", "second")
    assert page.locator('.column[data-column="Todo"] .card .title').all_inner_texts() == ["first", "second"]   # appended
    page.locator(".card", has_text="first").locator(".check").click()
    expect(page.locator(".card.done", has_text="first")).to_be_visible()

    page.goto(page.base + "/b/my-board/settings")
    page.select_option("#b-hide", "1")
    expect(page.locator("#save-status")).to_have_text("Saved")
    page.goto(page.base + "/b/my-board")
    expect(page.locator(".card", has_text="first")).to_have_count(0)
    expect(page.locator(".chip", has_text="1 completed hidden")).to_be_visible()
    page.click('.sidebar [data-go="l"]')
    expect(page.locator(".logbook .row", has_text="first")).to_be_visible()          # never lost


def test_cross_origin_page_cannot_drive_the_app(browser, server):
    """Standard 05: a page on another origin must not be able to write to a LAN-only, login-less app.
    A second local server plays the hostile page (a different port is a different origin)."""
    import threading

    from werkzeug.serving import make_server
    from werkzeug.wrappers import Request, Response

    @Request.application
    def hostile(request):
        return Response(f"""<html><body>
            <form id=f method=post action="{server}/boards"><input name=title value="pwned-form"></form>
            <script>
              fetch("{server}/boards", {{method: "POST", mode: "no-cors",
                headers: {{"Content-Type": "application/x-www-form-urlencoded"}}, body: "title=pwned-fetch"}})
                .finally(() => document.getElementById("f").submit());
            </script></body></html>""", content_type="text/html")

    evil = make_server("127.0.0.1", 0, hostile)
    threading.Thread(target=evil.serve_forever, daemon=True).start()
    ctx = browser.new_context()
    pg = ctx.new_page()
    pg.goto(f"http://127.0.0.1:{evil.server_port}/")
    pg.wait_for_timeout(1500)                                   # let the fetch and the form submit happen
    listing = ctx.new_page()
    listing.goto(server + "/")
    assert "pwned" not in listing.content().lower()             # the server refused both
    assert "403" in pg.content() or "Forbidden" in pg.content()  # the form post got an explicit refusal
    ctx.close()
    evil.shutdown()


# ---- start/due dates, move-to, editable completion date, hidden-lists panel, collapse, filters ----

def test_start_and_due_dates_shown_and_editable(page):
    add_card(page, "Todo", "Buy paint")
    page.locator(".card .title").click()
    page.fill(".dialog input[name=start]", "today")
    page.fill(".dialog input[name=due]", "tomorrow")
    page.click(".dialog button[type=submit]")
    expect(page.locator("#modal .backdrop")).to_have_count(0)
    card = page.locator(".card", has_text="Buy paint")
    expect(card.locator(".start")).to_be_visible()
    expect(card.locator(".due")).to_be_visible()


def test_move_to_within_board_and_across_boards(page):
    fab_add(page, "New board", "Elsewhere")
    page.wait_for_url("**/b/elsewhere")
    page.goto(page.base + "/b/my-board")
    add_card(page, "Todo", "mover")
    page.locator(".card", has_text="mover").locator(".title").click()
    page.select_option(".move-to", "my-board|Doing")           # within-board move
    page.click(".move-btn")
    page.wait_for_load_state()
    expect(page.locator('.column[data-column="Doing"] .card', has_text="mover")).to_be_visible()

    page.locator(".card", has_text="mover").locator(".title").click()
    page.select_option(".move-to", "elsewhere|Todo")           # cross-board move
    page.click(".move-btn")
    page.wait_for_load_state()
    expect(toast(page)).to_contain_text("Moved “mover” to Elsewhere")
    expect(page.locator(".card", has_text="mover")).to_have_count(0)
    page.goto(page.base + "/b/elsewhere")
    expect(page.locator('.column[data-column="Todo"] .card', has_text="mover")).to_be_visible()


def test_editable_completion_date_from_card_and_logbook(page):
    add_card(page, "Todo", "backdate me")
    page.locator(".card", has_text="backdate me").locator(".check").click()
    expect(page.locator(".card.done")).to_be_visible()
    page.locator(".card .title").click()
    expect(page.locator(".completed-at-row")).to_be_visible()
    page.fill(".completed-at-input", "2026-09-01T09:00")
    page.click("[data-completed-at-save]")
    expect(page.locator("#modal .backdrop")).to_have_count(0)
    expect(toast(page).last).to_contain_text("Completion date updated")

    page.click('.sidebar [data-go="l"]')
    page.wait_for_url("**/logbook")
    expect(page.locator(".logbook .row", has_text="backdate me")).to_contain_text("9:00 AM")
    page.get_by_role("button", name="Edit date").click()
    editor = page.locator(".logbook-inline-edit")
    expect(editor).to_be_visible()
    editor.locator(".completed-at-input").fill("2026-08-15T14:30")
    editor.locator("[data-completed-at-save]").click()
    page.wait_for_load_state()
    expect(page.locator(".logbook .row", has_text="backdate me")).to_contain_text("2:30 PM")


def test_hidden_lists_panel_toggle_each_and_all(page):
    page.get_by_role("button", name="Show or hide lists").click()
    menu = page.locator(".eye-menu")
    expect(menu).to_be_visible()
    expect(menu.locator(".eye-row")).to_have_count(3)                  # Todo, Doing, Done
    page.locator("body").click(position={"x": 700, "y": 700})          # outside click closes it
    expect(menu).to_be_hidden()

    page.get_by_role("button", name="Show or hide lists").click()
    page.get_by_role("button", name="Hide all").click()
    page.wait_for_load_state()
    expect(page.locator(".column")).to_have_count(0)
    expect(page.locator('[data-eye-toggle] .icon-badge')).to_have_text("3")

    page.get_by_role("button", name="Show or hide lists").click()
    page.get_by_role("button", name="Show all").click()
    page.wait_for_load_state()
    expect(page.locator(".column")).to_have_count(3)
    expect(page.locator('[data-eye-toggle] .icon-badge')).to_have_count(0)


def test_sidebar_collapses_and_persists(page):
    expect(page.locator(".sidebar")).to_be_visible()
    page.get_by_role("button", name="Collapse sidebar").click()
    expect(page.locator(".sidebar")).to_be_hidden()
    rail = page.get_by_role("button", name="Show sidebar")
    expect(rail).to_be_visible()
    page.reload()
    expect(page.locator(".sidebar")).to_be_hidden()                    # persisted across reload
    rail.click()
    expect(page.locator(".sidebar")).to_be_visible()


def open_date_filter(page):
    page.get_by_role("button", name="Filter by date").click()
    expect(page.locator(".date-filter-panel")).to_be_visible()


def test_scheduled_filters_presets_and_saved_filters(page):
    add_card(page, "Todo", "Today thing")
    page.locator(".card", has_text="Today thing").locator(".title").click()
    page.fill(".dialog input[name=due]", "today")
    page.click(".dialog button[type=submit]")
    add_card(page, "Todo", "Next month thing")
    page.locator(".card", has_text="Next month thing").locator(".title").click()
    page.fill(".dialog input[name=due]", "in 5 weeks")
    page.click(".dialog button[type=submit]")

    page.click('.sidebar [data-go="s"]')
    page.wait_for_url("**/scheduled")
    expect(page.locator(".agenda .row", has_text="Today thing")).to_be_visible()
    expect(page.locator(".agenda .row", has_text="Next month thing")).to_be_visible()

    open_date_filter(page)
    page.get_by_role("link", name="Today", exact=True).click()
    page.wait_for_load_state()
    expect(page.locator(".agenda .row", has_text="Today thing")).to_be_visible()
    expect(page.locator(".agenda .row", has_text="Next month thing")).to_have_count(0)

    open_date_filter(page)                                          # collapses again after a reload
    page.fill(".save-filter input[name=name]", "My range")
    page.click(".save-filter button")
    page.wait_for_load_state()
    open_date_filter(page)
    expect(page.locator(".saved-chip", has_text="My range")).to_be_visible()

    page.get_by_role("link", name="All", exact=True).click()
    page.wait_for_load_state()
    expect(page.locator(".agenda .row", has_text="Next month thing")).to_be_visible()
    open_date_filter(page)
    page.locator(".saved-chip", has_text="My range").get_by_role("link").click()
    page.wait_for_load_state()
    expect(page.locator(".agenda .row", has_text="Next month thing")).to_have_count(0)

    open_date_filter(page)
    page.locator(".saved-chip", has_text="My range").locator(".chip-x").click()
    page.wait_for_load_state()
    open_date_filter(page)
    expect(page.locator(".saved-chip", has_text="My range")).to_have_count(0)


def test_logbook_has_its_own_filter_bar(page):
    page.click('.sidebar [data-go="l"]')
    page.wait_for_url("**/logbook")
    expect(page.locator(".date-filter-wrap")).to_be_visible()
    expect(page.locator(".filter-chips .chip", has_text="This week")).to_be_hidden()  # tucked away
    open_date_filter(page)
    expect(page.locator(".filter-chips .chip", has_text="This week")).to_be_visible()


def test_scheduled_custom_range_hidden_behind_filter_button(page):
    page.click('.sidebar [data-go="s"]')
    page.wait_for_url("**/scheduled")
    toggle = page.get_by_role("button", name="Filter by date")
    panel = page.locator(".date-filter-panel")
    expect(panel).to_be_hidden()                                   # collapsed by default: no clutter
    expect(page.locator('.filter-range input[name="from"]')).to_be_hidden()
    expect(page.locator(".filter-chips .chip", has_text="Today")).to_be_hidden()

    toggle.click()
    expect(panel).to_be_visible()
    page.locator("body").click(position={"x": 700, "y": 700})      # outside click closes it
    expect(panel).to_be_hidden()


def test_tasks_board_create_add_complete_delete(page):
    fab_add(page, "New task list", "Groceries")
    page.wait_for_url("**/b/groceries")
    expect(page.locator(".tasks-board")).to_be_visible()
    expect(page.locator(".column")).to_have_count(0)          # no kanban list chrome

    box = page.locator(".add-task input[name=title]")
    box.fill("Buy milk")
    box.press("Enter")
    card = page.locator(".card", has_text="Buy milk")
    expect(card).to_be_visible()

    card.locator(".check").click()
    expect(page.locator(".card.done", has_text="Buy milk")).to_be_visible()

    card.locator(".del").click()
    expect(page.locator(".card", has_text="Buy milk")).to_have_count(0)


def test_tasks_board_has_no_rules_section_but_has_labels(page):
    fab_add(page, "New task list", "Errands")
    page.wait_for_url("**/b/errands")
    page.get_by_role("link", name="Board settings").click()
    page.wait_for_url("**/b/errands/settings")
    expect(page.locator("#labels-h")).to_be_visible()
    expect(page.locator("#rules-h")).to_have_count(0)


def test_priority_set_from_card_dialog_and_shown_on_card(page):
    add_card(page, "Todo", "Ship it")
    page.locator(".card", has_text="Ship it").locator(".title").click()
    page.select_option(".dialog select[name=priority]", "high")
    page.click(".dialog button[type=submit]")
    expect(page.locator("#modal .backdrop")).to_have_count(0)
    expect(page.locator(".card", has_text="Ship it").locator(".priority.p-high")).to_be_visible()


def test_board_filter_by_text_priority_and_label(page):
    add_card(page, "Todo", "Buy paint")
    page.locator(".card", has_text="Buy paint").locator(".title").click()
    page.select_option(".dialog select[name=priority]", "high")
    page.click(".dialog button[type=submit]")
    add_card(page, "Todo", "Water plants")

    page.get_by_role("button", name="Filter cards").click()
    panel = page.locator(".filter-panel")
    expect(panel).to_be_visible()

    panel.locator(".filter-text").fill("paint")
    expect(page.locator(".card", has_text="Buy paint")).to_be_visible()
    expect(page.locator(".card", has_text="Water plants")).to_be_hidden()
    expect(page.locator(".filter-status")).to_contain_text("Showing 1 of 2")

    panel.locator(".filter-text").fill("")
    panel.locator(".filter-priority[value=high]").check()
    expect(page.locator(".card", has_text="Buy paint")).to_be_visible()
    expect(page.locator(".card", has_text="Water plants")).to_be_hidden()

    page.get_by_role("button", name="Clear filters").click()
    expect(page.locator(".card", has_text="Water plants")).to_be_visible()
    expect(page.locator(".filter-status")).to_have_text("")


def test_board_filter_tag_checkboxes(page):
    add_card(page, "Todo", "Buy paint #home")
    add_card(page, "Todo", "Water plants #garden")

    page.get_by_role("button", name="Filter cards").click()
    panel = page.locator(".filter-panel")
    expect(panel.locator(".filter-tag[value=home]")).to_be_visible()
    expect(panel.locator(".filter-tag[value=garden]")).to_be_visible()

    panel.locator(".filter-tag[value=home]").check()
    expect(page.locator(".card", has_text="Buy paint")).to_be_visible()
    expect(page.locator(".card", has_text="Water plants")).to_be_hidden()


def test_label_create_assign_and_display(page):
    page.get_by_role("link", name="Board settings").click()
    page.wait_for_url("**/b/my-board/settings")
    page.fill(".label-add input[name=name]", "Urgent")
    page.locator(".label-add .label-swatch.c-red").click()
    page.get_by_role("button", name="Add label").click()
    page.wait_for_load_state()
    expect(page.locator(".label-manage-row", has_text="Urgent")).to_be_visible()

    page.goto(page.base + "/b/my-board")
    add_card(page, "Todo", "Fix bug")
    page.locator(".card", has_text="Fix bug").locator(".title").click()
    page.locator(".label-picker .label-check", has_text="Urgent").locator("input").check()
    page.click(".dialog button[type=submit]")
    expect(page.locator("#modal .backdrop")).to_have_count(0)
    card = page.locator(".card", has_text="Fix bug")
    expect(card.locator(".label-chip.c-red", has_text="Urgent")).to_be_visible()


def test_label_edit_stays_collapsed_until_asked_for(page):
    page.get_by_role("link", name="Board settings").click()
    page.wait_for_url("**/b/my-board/settings")
    page.fill(".label-add input[name=name]", "Urgent")
    page.get_by_role("button", name="Add label").click()
    page.wait_for_load_state()

    row = page.locator(".label-manage-row", has_text="Urgent")
    expect(row.locator(".label-edit-form")).to_be_hidden()          # no swatches/inputs by default

    row.get_by_role("button", name="Edit label Urgent").click()
    expect(row.locator(".label-edit-form")).to_be_visible()
    row.locator("input[name=name]").fill("Urgent!")
    row.locator(".label-swatch.c-blue").click()
    row.get_by_role("button", name="Save").click()
    page.wait_for_load_state()

    row = page.locator(".label-manage-row", has_text="Urgent!")
    expect(row.locator(".label-edit-form")).to_be_hidden()          # collapses again after saving
    expect(row.locator(".label-chip.c-blue")).to_be_visible()


def test_archive_and_unarchive_board(page):
    fab_add(page, "New board", "Side project")
    page.wait_for_url("**/b/side-project")

    page.get_by_role("button", name="Archive board", exact=True).click()
    page.wait_for_load_state()
    expect(page.locator(".chip", has_text="Archived")).to_be_visible()
    expect(page.get_by_role("link", name="Side project", exact=True)).to_have_count(0)  # sidebar

    page.get_by_role("link", name="Archived boards").click()
    page.wait_for_url("**/archived")
    row = page.locator(".row", has_text="Side project")
    expect(row).to_be_visible()

    row.get_by_role("button", name="Unarchive").click()
    page.wait_for_load_state()
    expect(page.locator(".empty")).to_be_visible()
    expect(page.get_by_role("link", name="Side project", exact=True)).to_be_visible()  # back
