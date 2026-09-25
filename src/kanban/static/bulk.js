// Bulk-select cards (board.html, tasks.html): client-side only, not persisted -- turned off by
// the same "Select cards" button that turned it on. Every action reuses the existing single-card
// endpoints in a sequential loop, not a new bulk server route, one request at a time (never
// Promise.all -- concurrent writes to the same board.md silently clobber each other, AGENTS.md
// trap 6). No-ops on any page without both a .board and a .bulk-bar (everywhere but these two).
(() => {
  const board = document.querySelector('.board');
  const toggle = document.querySelector('[data-select-toggle]');
  const bar = document.querySelector('.bulk-bar');
  if (!board || !toggle || !bar) return;

  const selected = new Set();
  const countEl = bar.querySelector('.bulk-count');
  const moveSelect = bar.querySelector('.bulk-move-to');
  const moveBtn = bar.querySelector('.bulk-move-btn');
  const dupBtn = bar.querySelector('.bulk-dup-btn');
  const deleteBtn = bar.querySelector('.bulk-delete-btn');
  const clearBtn = bar.querySelector('.bulk-clear-btn');

  function updateBar() {
    bar.hidden = selected.size === 0;
    countEl.textContent = `${selected.size} selected`;
  }

  function clearSelection() {
    selected.clear();
    board.querySelectorAll('.select-check:checked').forEach(cb => (cb.checked = false));
    updateBar();
  }

  function selectedCards() {
    return [...selected].map(id => document.querySelector(`.card[data-id="${id}"]`)).filter(Boolean);
  }

  toggle.addEventListener('click', () => {
    board.classList.toggle('select-mode');
    if (!board.classList.contains('select-mode')) clearSelection();
  });

  board.addEventListener('change', e => {
    const cb = e.target.closest('.select-check');
    if (!cb) return;
    const card = cb.closest('.card');
    if (cb.checked) selected.add(card.dataset.id); else selected.delete(card.dataset.id);
    updateBar();
  });

  clearBtn.addEventListener('click', clearSelection);

  // Only rendered when the board has more than one list (_bulk_bar.html) -- moveBtn is null on a
  // tasks board, where there's nowhere else on the same board to move a card to.
  moveBtn?.addEventListener('click', async () => {
    const column = moveSelect.value;
    if (!column) return;
    moveBtn.disabled = true;
    for (const card of selectedCards()) {
      if (card.closest('.column')?.dataset.column === column) continue;
      await fetch(board.dataset.moveUrl.replace('ID', card.dataset.id), {
        method: 'POST', body: new URLSearchParams({ column, index: '0' }),
      });
    }
    location.reload();
  });

  dupBtn.addEventListener('click', async () => {
    dupBtn.disabled = true;
    for (const card of selectedCards()) {
      await fetch(board.dataset.duplicateUrl.replace('ID', card.dataset.id), { method: 'POST' });
    }
    location.reload();
  });

  // Same two-step "click again" confirm as [data-post]'s (ui.js), reimplemented small here rather
  // than shared -- this button isn't a [data-post] button (its action isn't a single fixed POST).
  let armed = false, armTimer = null;
  deleteBtn.addEventListener('click', async () => {
    if (!armed) {
      armed = true;
      deleteBtn.classList.add('armed');
      const label = document.createElement('span');
      label.className = 'confirm-label';
      label.textContent = deleteBtn.dataset.confirm;
      deleteBtn.append(label);
      armTimer = setTimeout(() => { armed = false; deleteBtn.classList.remove('armed'); label.remove(); }, 3500);
      return;
    }
    clearTimeout(armTimer);
    deleteBtn.disabled = true;
    for (const card of selectedCards()) {
      await fetch(board.dataset.deleteUrl.replace('ID', card.dataset.id), { method: 'DELETE' });
    }
    location.reload();
  });
})();
