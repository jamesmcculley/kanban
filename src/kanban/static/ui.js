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
})();
