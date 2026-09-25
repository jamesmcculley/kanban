// Shared behaviour: one-click actions ([data-post]) with optional two-step confirm, dropping a
// card onto a board in the sidebar, and the notes editor in the card dialog.
(() => {
  // -- [data-post]: POST from a button, then react to the JSON reply ------------------------
  // data-vals='{"k": "v"}'  form fields    data-confirm="text"  needs a second click
  // data-after="reload|home|clear-done"    what to do on success
  const timers = new WeakMap();
  function arm(btn) {
    btn.classList.add('armed');
    const label = document.createElement('span');
    label.className = 'confirm-label';
    label.textContent = btn.dataset.confirm;
    btn.append(label);
    timers.set(btn, setTimeout(() => disarm(btn), 3500));
  }
  function disarm(btn) {
    clearTimeout(timers.get(btn));
    btn.classList.remove('armed');
    btn.querySelector('.confirm-label')?.remove();
  }

  function after(btn, data) {
    const undoable = data.message ? [data.message, data.undo] : null;
    switch (btn.dataset.after) {
      case 'reload':
        if (undoable) window.toast.later(...undoable);
        location.reload();
        break;
      case 'home':
        if (undoable) window.toast.later(...undoable);
        location.href = '/';
        break;
      case 'clear-done': {
        const col = btn.closest('.column');
        col.querySelectorAll('.card.done').forEach(c => c.remove());
        col.querySelector('.count').textContent = col.querySelectorAll('.card').length;
        if (undoable) window.toast(...undoable);
        break;
      }
      default:
        if (undoable) window.toast(...undoable);
    }
  }

  document.addEventListener('click', async e => {
    const btn = e.target.closest('[data-post]');
    if (!btn) return;
    e.preventDefault();
    if (btn.dataset.confirm && !btn.classList.contains('armed')) return arm(btn);
    disarm(btn);
    const r = await fetch(btn.dataset.post, {
      method: 'POST', body: new URLSearchParams(JSON.parse(btn.dataset.vals || '{}')),
    });
    if (!r.ok) return window.toast('That did not work. Reload and try again.');
    let data = {};
    try { data = await r.json(); } catch { /* 204 / empty */ }
    after(btn, data);
  });

  // -- drop a card on a sidebar board (or the Inbox) to move it there -------------------------
  // The sidebar isn't a Sortable-managed list, so Sortable's own onEnd (board.html) still fires
  // on dragend regardless of where the drop actually landed -- it only knows the dragged card's
  // index *within its own list* may have drifted during the drag (the cursor passing near a
  // sibling card en route to the sidebar is enough), and fires a same-board reorder POST for that
  // drift even though the real drop target was a different board entirely. That spurious reorder
  // then races this handler's own cross-board move against the same card file (see AGENTS.md trap
  // 22). window.__sidebarDropHandled, set synchronously here before the async fetch even starts --
  // and so guaranteed to be set before the native dragend that drives onEnd, which always fires
  // strictly after drop -- tells board.html's onEnd this drop is already spoken for.
  const draggedCard = () => (window.Sortable?.dragged?.classList.contains('card') ? Sortable.dragged : null);
  document.querySelectorAll('[data-drop-board]').forEach(target => {
    const here = () => document.querySelector('.board')?.dataset.slug === target.dataset.dropBoard;
    target.addEventListener('dragover', e => {
      if (!draggedCard() || here()) return;
      e.preventDefault();
      target.classList.add('drop-hover');
    });
    target.addEventListener('dragleave', () => target.classList.remove('drop-hover'));
    target.addEventListener('drop', async e => {
      target.classList.remove('drop-hover');
      const card = draggedCard();
      const board = document.querySelector('.board');
      if (!card || !board || here()) return;
      e.preventDefault();
      window.__sidebarDropHandled = true;
      const url = board.dataset.moveboardUrl.replace('ID', card.dataset.id);
      const r = await fetch(url, { method: 'POST', body: new URLSearchParams({ to: target.dataset.dropBoard }) });
      if (!r.ok) return window.toast('Could not move that card');
      const data = await r.json();
      const col = card.closest('.column');
      card.remove();                       // after Sortable has finished with it
      if (col) col.querySelector('.count').textContent = col.querySelectorAll('.card').length;
      window.toast(data.message, data.undo);
      window.refreshStats?.();
    });
  });

  // -- board settings: a label stays a plain chip until "Edit" is clicked ----------------------
  window.editLabel = btn => {
    const row = btn.closest('.label-manage-row');
    row.classList.add('editing');
    row.querySelector('.label-edit-form input[name=name]').focus();
  };
  window.cancelLabelEdit = btn => btn.closest('.label-manage-row').classList.remove('editing');

  // -- card dialog: rendered notes with live checklist ------------------------------------------
  window.editNotes = btn => {
    const box = btn.closest('.notes');
    box.querySelector('.notes-view').hidden = true;
    btn.hidden = true;
    const area = box.querySelector('textarea');
    area.hidden = false;
    area.focus();
  };
  // Ticking a box saves on the server; keep the (hidden) textarea in step so Save can't undo it.
  document.addEventListener('htmx:afterRequest', async e => {
    const view = e.target.closest?.('.notes-view');
    if (!view || !e.target.matches('.task') || !e.detail.successful) return;
    const r = await fetch(view.dataset.bodyUrl);
    if (r.ok) view.closest('.notes').querySelector('textarea').value = await r.text();
  });

  // -- rule builder: show only the fields the chosen trigger/action needs ----------------------
  document.querySelectorAll('.rule-form').forEach(form => {
    const sync = () => {
      const when = form.elements.when.value, action = form.elements.do.value;
      form.querySelector('.rb-in-label').textContent = when === 'moved' ? 'into list' : 'in list';
      form.querySelector('.rb-move').hidden = action !== 'move';
      form.querySelector('.rb-tag').hidden = !['add_tag', 'remove_tag'].includes(action);
    };
    form.addEventListener('change', sync);
    sync();
  });

  // -- hidden-lists panel: the eye icon next to Settings ---------------------------------------
  document.addEventListener('click', e => {
    const toggle = e.target.closest('[data-eye-toggle]');
    if (toggle) { toggle.nextElementSibling.hidden = !toggle.nextElementSibling.hidden; return; }
    if (!e.target.closest('.eye-menu-wrap')) document.querySelectorAll('.eye-menu').forEach(m => (m.hidden = true));
  });
  document.addEventListener('change', e => {
    const cb = e.target.closest('.eye-check');
    if (!cb) return;
    fetch(cb.dataset.url, { method: 'POST', body: new URLSearchParams({ name: cb.dataset.name, hidden: cb.checked ? '0' : '1' }) })
      .then(() => location.reload());
  });
  document.querySelectorAll('[data-eye-all]').forEach(btn => btn.addEventListener('click', async () => {
    const wantVisible = btn.dataset.eyeAll === 'show';
    const boxes = [...document.querySelectorAll('.eye-check')].filter(cb => cb.checked !== wantVisible);
    if (!boxes.length) return;
    // One at a time, not Promise.all: each hide/show is a read-modify-write of the same board.md,
    // so concurrent requests race and the last writer silently clobbers the others' changes.
    for (const cb of boxes) {
      await fetch(cb.dataset.url, { method: 'POST', body: new URLSearchParams({ name: cb.dataset.name, hidden: wantVisible ? '0' : '1' }) });
    }
    location.reload();
  }));

  // -- Scheduled/Logbook: custom date range behind a filter icon, same reveal-a-sibling-panel
  // pattern as the eye menu above (kept separate from it, and from filter.js's per-board filter,
  // so the three popovers never share a selector by accident).
  document.addEventListener('click', e => {
    const toggle = e.target.closest('[data-date-filter-toggle]');
    if (toggle) { toggle.nextElementSibling.hidden = !toggle.nextElementSibling.hidden; return; }
    if (!e.target.closest('.date-filter-wrap')) document.querySelectorAll('.date-filter-panel').forEach(m => (m.hidden = true));
  });

  // -- Search: the Advanced search panel, same reveal-a-sibling-panel pattern again, its own
  // classes for the same reason (see above) -- a Search page result can itself be on a board with
  // its own .filter-wrap, so nothing here can risk being mistaken for that one either.
  document.addEventListener('click', e => {
    const toggle = e.target.closest('[data-search-filter-toggle]');
    if (toggle) { toggle.nextElementSibling.hidden = !toggle.nextElementSibling.hidden; return; }
    if (!e.target.closest('.search-filter-wrap')) document.querySelectorAll('.search-filter-panel').forEach(m => (m.hidden = true));
  });

  // -- "Move to": any card, to any list on any board, from the edit dialog --------------------
  document.addEventListener('click', async e => {
    const btn = e.target.closest('.move-btn');
    if (!btn) return;
    const select = btn.closest('.move-row').querySelector('.move-to');
    const val = select.value;
    if (!val) return;
    const [destSlug, destCol] = val.split('|');
    btn.disabled = true;
    let r, data = null;
    if (destSlug === btn.dataset.current) {
      r = await fetch(btn.dataset.moveUrl, { method: 'POST', body: new URLSearchParams({ column: destCol, index: '0' }) });
      if (r.ok && r.status === 200) data = await r.json();
    } else {
      r = await fetch(btn.dataset.moveboardUrl, { method: 'POST', body: new URLSearchParams({ to: destSlug, column: destCol }) });
      if (r.ok) data = await r.json();
    }
    btn.disabled = false;
    if (!r.ok) return window.toast('Could not move that card');
    document.getElementById('modal').innerHTML = '';
    window.toast.later(data?.message || 'Moved', data?.undo);
    location.reload();
  });

  // -- editing when a completed card was actually completed (forgot to check it off yesterday?) --
  // Only markup in the shared card-edit dialog (_edit.html) now -- opened either on a board (a
  // `.card[data-id]` exists to patch in place) or standalone from Scheduled/Logbook (it doesn't,
  // so this falls through to a plain reload, same as the rest of that dialog in standalone mode).
  document.addEventListener('click', async e => {
    const btn = e.target.closest('[data-completed-at-save]');
    if (!btn) return;
    const input = btn.closest('.completed-at-row').querySelector('.completed-at-input');
    const r = await fetch(btn.dataset.url, { method: 'POST', body: new URLSearchParams({ at: input.value }) });
    if (!r.ok) return window.toast('Could not update the completion date');
    const card = document.querySelector(`.card[data-id="${btn.dataset.card}"]`);
    if (card) {
      card.outerHTML = await r.text();
      document.getElementById('modal').innerHTML = '';
      window.toast('Completion date updated');
    } else {
      window.toast.later('Completion date updated');
      location.reload();
    }
  });
})();
