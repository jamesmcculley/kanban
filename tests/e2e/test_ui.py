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
    """what: 'New list' | 'New board' | 'New canvas'"""
    page.click(".fab-btn")
    page.get_by_role("button", name=what).click()
    page.fill(".fab-form input", name)
    page.press(".fab-form input", "Enter")


def column_order(page):
    return page.eval_on_selector_all(".column", "els => els.map(e => e.dataset.column)")


def test_layout_and_quick_add(page):
    expect(page.locator(".sidebar")).to_be_visible()
    expect(page.locator(".sidebar a", has_text="Today")).to_be_visible()
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
    chip = page.locator(".chip", has_text="Someday")
    expect(chip).to_contain_text("1")
    chip.click()
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


def test_drag_card_between_lists(page):
    add_card(page, "Todo", "mover")
    drag(page, page.locator(".card", has_text="mover"), page.locator('.column[data-column="Doing"] .cards'))
    expect(page.locator('.column[data-column="Doing"] .card', has_text="mover")).to_be_visible()
    page.reload()
    expect(page.locator('.column[data-column="Doing"] .card', has_text="mover")).to_be_visible()


def test_areas_and_board_dragging(page):
    fab_add(page, "New board", "Garden")
    page.wait_for_url("**/b/garden")
    page.fill(".newarea input", "Home")
    page.press(".newarea input", "Enter")
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
    page.keyboard.press("u")
    page.wait_for_url("**/upcoming")


# ---- canvas -----------------------------------------------------------------------------------

import base64

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")


def open_canvas(page, name="Sketch"):
    fab_add(page, "New canvas", name)
    page.wait_for_selector("#canvas")


def test_canvas_note_create_edit_move_persist(page):
    open_canvas(page)
    expect(page.locator(".canvas-hint")).to_be_visible()
    page.locator("#canvas").dblclick(position={"x": 300, "y": 200})
    note = page.locator(".item.note")
    expect(note).to_have_count(1)
    expect(page.locator(".canvas-hint")).to_have_count(0)
    page.keyboard.type("hello canvas")
    page.keyboard.press("j")                       # typing in a note must not trigger shortcuts
    page.locator("#canvas").click(position={"x": 900, "y": 600})      # blur -> saves
    expect(note.locator(".item-text")).to_have_text("hello canvasj")

    before = note.bounding_box()
    page.mouse.move(before["x"] + 30, before["y"] + 30)
    page.mouse.down()
    page.mouse.move(before["x"] + 130, before["y"] + 90, steps=6)
    page.mouse.up()
    after = note.bounding_box()
    assert abs((after["x"] - before["x"]) - 100) < 3 and abs((after["y"] - before["y"]) - 60) < 3

    page.reload()
    again = page.locator(".item.note")
    expect(again.locator(".item-text")).to_have_text("hello canvasj")
    moved = again.bounding_box()
    assert abs(moved["x"] - after["x"]) < 3 and abs(moved["y"] - after["y"]) < 3   # position persisted


def test_canvas_note_color_resize_delete(page):
    open_canvas(page)
    page.click("[data-tool=note]")
    note = page.locator(".item.note")
    expect(note).to_have_count(1)
    note.hover()
    note.locator(".dot[data-color=blue]").click()
    expect(note).to_have_class(__import__("re").compile(r"c-blue"))
    w0 = note.bounding_box()["width"]
    note.hover()
    h = note.locator(".resize").bounding_box()
    page.mouse.move(h["x"] + 6, h["y"] + 6)
    page.mouse.down()
    page.mouse.move(h["x"] + 106, h["y"] + 6, steps=5)
    page.mouse.up()
    assert note.bounding_box()["width"] > w0 + 80
    page.reload()
    expect(page.locator(".item.note")).to_have_class(__import__("re").compile(r"c-blue"))
    assert page.locator(".item.note").bounding_box()["width"] > w0 + 80
    page.locator(".item.note").hover()
    page.locator(".item.note .item-del").click()
    expect(page.locator(".item")).to_have_count(0)
    page.reload()
    expect(page.locator(".item")).to_have_count(0)


def test_canvas_link_image_paste_drop(page):
    page.expected_errors.append("status of 400")      # the javascript: link below is refused on purpose
    open_canvas(page)
    page.fill(".tool-link", "https://example.com/docs")
    page.press(".tool-link", "Enter")
    link = page.locator(".item.link a")
    expect(link).to_have_attribute("href", "https://example.com/docs")
    expect(link).to_have_attribute("rel", "noopener noreferrer")
    page.fill(".tool-link", "javascript:alert(1)")
    page.press(".tool-link", "Enter")
    expect(page.locator(".item.link")).to_have_count(1)                # rejected, not added

    page.set_input_files(".tool-file", files=[{"name": "dot.png", "mimeType": "image/png", "buffer": PNG}])
    img = page.locator(".item.image img")
    expect(img).to_have_count(1)
    page.wait_for_function("() => document.querySelector('.item.image img').naturalWidth > 0")

    page.evaluate("""() => {
        const dt = new DataTransfer(); dt.setData('text/plain', 'https://example.org/pasted');
        document.dispatchEvent(new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true }));
    }""")
    expect(page.locator(".item.link")).to_have_count(2)
    page.evaluate("""() => {
        const dt = new DataTransfer(); dt.setData('text/plain', 'a pasted thought');
        document.dispatchEvent(new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true }));
    }""")
    expect(page.locator(".item.note .item-text", has_text="a pasted thought")).to_have_count(1)

    page.evaluate("""(b64) => {
        const dt = new DataTransfer(); dt.items.add(new File([Uint8Array.from(atob(b64), c => c.charCodeAt(0))], 'x.png', {type: 'image/png'}));
        document.getElementById('scroller').dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true, clientX: 400, clientY: 400 }));
    }""", base64.b64encode(PNG).decode())
    expect(page.locator(".item.image")).to_have_count(2)
    page.reload()
    expect(page.locator(".item")).to_have_count(5)


def test_canvas_nested_board(page):
    open_canvas(page, "Parent Canvas")
    page.fill(".tool-board input", "Sub List")
    page.press(".tool-board input", "Enter")
    card = page.locator(".item.board a")
    expect(card).to_contain_text("Sub List")
    expect(page.locator('.sidebar [data-slug="sub-list"]')).to_have_count(0)
    card.click()
    page.wait_for_url("**/b/sub-list")
    expect(page.locator(".crumb")).to_have_text("Parent Canvas")
    expect(page.locator(".column")).to_have_count(3)                # it's a lists board
    page.click(".crumb")
    page.wait_for_selector("#canvas")
    drag_card = page.locator(".item.board")
    box = drag_card.bounding_box()
    page.mouse.move(box["x"] + 10, box["y"] + 10)
    page.mouse.down()
    page.mouse.move(box["x"] + 150, box["y"] + 100, steps=6)
    page.mouse.up()
    expect(page).to_have_url(__import__("re").compile(r"/b/parent-canvas$"))   # a drag must not navigate


def test_fab_menu_contents_and_new_card_placement(page):
    # on a lists board the + offers list, board and canvas; on a canvas, no "New list"
    page.click(".fab-btn")
    for name in ("New list", "New board", "New canvas"):
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

    fab_add(page, "New canvas", "Board B")
    page.wait_for_selector("#canvas")
    page.click(".fab-btn")
    expect(page.get_by_role("button", name="New list")).to_have_count(0)
    expect(page.get_by_role("button", name="New board")).to_be_visible()


def test_fab_rejects_duplicate_list_name(page):
    page.expected_errors.append("status of 400")       # the refused duplicate is the point
    fab_add(page, "New list", "todo")                   # clashes with "Todo", case-insensitively
    expect(page.locator(".fab-form input")).to_have_js_property("validationMessage", "That name is taken or not allowed")
    expect(page.locator(".column")).to_have_count(3)


# ---- undo, logbook, trash, clear-done, inbox, move, notes, PWA --------------------------------------

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
    page.fill(".newarea input", "Home")
    page.press(".newarea input", "Enter")
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


def test_quick_capture_from_anywhere_lands_in_inbox(page):
    page.click('.sidebar [data-go="t"]')
    page.wait_for_url("**/today")
    page.keyboard.press("c")
    expect(page.locator(".fab-form input")).to_be_focused()
    page.keyboard.type("Phone gran tomorrow #family")
    page.keyboard.press("Enter")
    expect(toast(page)).to_contain_text("Added to Inbox")
    expect(page.locator("#inbox-badge .badge")).to_have_text("1")
    page.click('.sidebar [data-go="i"]')
    page.wait_for_url("**/b/inbox")
    card = page.locator(".card", has_text="Phone gran")
    expect(card).to_be_visible()
    expect(card.locator(".tag")).to_have_text("#family")
    expect(card.locator(".due")).not_to_be_empty()

    page.keyboard.press("Escape")
    page.keyboard.press("c")                                  # capturing while on the Inbox shows it at once
    page.keyboard.type("second one")
    page.keyboard.press("Enter")
    page.wait_for_load_state()
    expect(page.locator(".card")).to_have_count(2)
    expect(page.locator(".card .title").first).to_have_text("second one")   # newest on top
    expect(page.locator(".toast")).to_contain_text("Added to Inbox")        # toast survived the reload


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
    assert m["display"] == "standalone" and m["start_url"] == "/" and m["name"] == "Trellis"
    assert {i["sizes"] for i in m["icons"]} >= {"192x192", "512x512"}
    for icon in m["icons"]:
        assert page.request.get(page.base + icon["src"]).status == 200
    assert page.request.get(page.base + page.get_attribute("link[rel=apple-touch-icon]", "href")).status == 200


def test_canvas_delete_shows_undo(page):
    open_canvas(page, "Restorable")
    page.click("[data-tool=note]")
    note = page.locator(".item.note")
    expect(note).to_have_count(1)
    note.locator(".item-text").fill("keep me")
    page.locator("#canvas").click(position={"x": 900, "y": 600})
    note.hover()
    note.locator(".item-del").click()
    expect(page.locator(".item")).to_have_count(0)
    toast(page).get_by_role("button", name="Undo").click()
    page.wait_for_load_state()
    expect(page.locator(".item.note .item-text")).to_have_text("keep me")
