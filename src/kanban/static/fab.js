// Floating "+" button (bottom right): new list, new board, new canvas.
(() => {
  const fab = document.getElementById('fab');
  if (!fab) return;
  const btn = fab.querySelector('.fab-btn');
  const menu = fab.querySelector('.fab-menu');
  const form = fab.querySelector('.fab-form');
  const input = form.querySelector('input');
  const PLACEHOLDER = { list: 'List name', board: 'Board name', canvas: 'Canvas name',
                        capture: 'Quick add… (dates and #tags work)' };
  let action = null;

  function close() {
    fab.classList.remove('open');
    menu.hidden = form.hidden = true;
    input.value = '';
    input.setCustomValidity('');
    action = null;
  }
  btn.addEventListener('click', () => {
    if (fab.classList.contains('open')) return close();
    fab.classList.add('open');
    menu.hidden = false;
  });
  menu.addEventListener('click', e => {
    const choice = e.target.closest('[data-action]');
    if (!choice) return;
    action = choice.dataset.action;
    input.placeholder = PLACEHOLDER[action];
    menu.hidden = true;
    form.hidden = false;
    input.focus();
  });
  // The "c" shortcut: skip the menu and go straight to the capture box.
  window.openCapture = () => {
    fab.classList.add('open');
    menu.hidden = true;
    action = 'capture';
    input.placeholder = PLACEHOLDER.capture;
    form.hidden = false;
    input.focus();
  };
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && fab.classList.contains('open')) close(); });
  document.addEventListener('click', e => { if (!fab.contains(e.target)) close(); });
  input.addEventListener('input', () => input.setCustomValidity(''));

  form.addEventListener('submit', async e => {
    e.preventDefault();
    const name = input.value.trim();
    if (!name) return;
    if (action === 'capture') {
      const r = await fetch(fab.dataset.captureUrl, { method: 'POST', body: new URLSearchParams({ title: name }) });
      if (!r.ok) {
        input.setCustomValidity('Type something to add');
        input.reportValidity();
        return;
      }
      const data = await r.json();
      close();
      window.refreshStats?.();                          // Inbox count and Today badge
      if (location.pathname === '/b/inbox') {           // already looking at it: show the new card
        window.toast.later(data.message, data.undo);
        location.reload();
      } else {
        window.toast(data.message, data.undo);
      }
      return;
    }
    const r = action === 'list'
      ? await fetch(fab.dataset.listUrl, { method: 'POST', body: new URLSearchParams({ name }) })
      : await fetch(fab.dataset.boardUrl, {
          method: 'POST', body: new URLSearchParams({ title: name, kind: action === 'canvas' ? 'canvas' : 'kanban' }),
        });
    if (!r.ok) {
      input.setCustomValidity('That name is taken or not allowed');
      input.reportValidity();
      return;
    }
    if (action === 'list') location.reload();
    else location.href = r.url;                     // the server redirected to the new board
  });
})();
