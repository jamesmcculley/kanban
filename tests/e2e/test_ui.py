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
    cards = page.locator(f'.column[data-column="{column}"] .card')
    before = cards.count()
    box = page.locator(f'.column[data-column="{column}"] input[name=title]')
    box.fill(text)
    box.press("Enter")
    expect(cards).to_have_count(before + 1)  # wait: the form resets itself after the request


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
    page.fill(".add-column input", "Later")
    page.press(".add-column input", "Enter")
    expect(page.locator('.column[data-column="Later"]')).to_be_visible()

    title = page.locator('.column[data-column="Later"] .col-title')
    title.fill("Someday")
    title.press("Enter")
    expect(page.locator('.column[data-column="Someday"]')).to_be_visible()

    add_card(page, "Someday", "parked")
    col = page.locator('.column[data-column="Someday"]')
    col.hover()
    col.get_by_role("button", name="Hide").click()
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
    page.fill(".newboard input", "Garden")
    page.press(".newboard input", "Enter")
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
    add_card(page, "Todo", "first")
    add_card(page, "Todo", "second")
    page.locator("body").click(position={"x": 700, "y": 700})
    page.keyboard.press("j")
    expect(page.locator(".card.selected")).to_contain_text("first")
    page.keyboard.press("j")
    expect(page.locator(".card.selected")).to_contain_text("second")
    page.keyboard.press("x")
    expect(page.locator(".card.done", has_text="second")).to_be_visible()
    page.keyboard.press("Shift+L")
    expect(page.locator('.column[data-column="Doing"] .card', has_text="second")).to_be_visible()
    page.keyboard.press("e")
    expect(page.locator(".dialog input[name=title]")).to_be_focused()
    page.keyboard.press("Escape")
    expect(page.locator("#modal .backdrop")).to_have_count(0)
    page.keyboard.press("?")
    expect(page.locator("#help")).to_be_visible()
    page.keyboard.press("Escape")
    page.keyboard.press("g")
    page.keyboard.press("u")
    page.wait_for_url("**/upcoming")
