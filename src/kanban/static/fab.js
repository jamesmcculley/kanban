// Floating "+" button (bottom right): new list, new board, new area.
(() => {
  const fab = document.getElementById('fab');
  if (!fab) return;
  const btn = fab.querySelector('.fab-btn');
  const menu = fab.querySelector('.fab-menu');
  const form = fab.querySelector('.fab-form');
  const input = form.querySelector('input');
  const boardSelect = form.querySelector('.fab-board');
  const PLACEHOLDER = { list: 'List name', board: 'Board name',
                        area: 'Area name', capture: 'Quick add… (dates and #tags work)' };
  let action = null;

  // Which board a capture should default to: last one you captured into, else the board you're
  // currently looking at, else whatever is first.
  function defaultCaptureBoard() {
    let remembered = null;
    try { remembered = localStorage.getItem('capture-board'); } catch { /* ignore */ }
    const options = [...boardSelect.options].map(o => o.value);
    if (remembered && options.includes(remembered)) return remembered;
    const current = document.querySelector('.board')?.dataset.slug;
    if (current && options.includes(current)) return current;
    return options[0];
  }

  function close() {
    fab.classList.remove('open');
    menu.hidden = form.hidden = boardSelect.hidden = true;
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
    boardSelect.hidden = action !== 'capture';
    if (action === 'capture' && boardSelect.options.length) boardSelect.value = defaultCaptureBoard();
    input.focus();
  });
  // The "c" shortcut: skip the menu and go straight to the capture box.
  window.openCapture = () => {
    fab.classList.add('open');
    menu.hidden = true;
    action = 'capture';
    input.placeholder = PLACEHOLDER.capture;
    form.hidden = false;
    boardSelect.hidden = false;
    if (boardSelect.options.length) boardSelect.value = defaultCaptureBoard();
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
      const board = boardSelect.value;
      if (!board) {
        input.setCustomValidity('Create a board first');
        input.reportValidity();
        return;
      }
      const r = await fetch(fab.dataset.captureUrl, { method: 'POST', body: new URLSearchParams({ title: name, board }) });
      if (!r.ok) {
        input.setCustomValidity('Type something to add');
        input.reportValidity();
        return;
      }
      try { localStorage.setItem('capture-board', board); } catch { /* ignore */ }
      const data = await r.json();
      close();
      window.refreshStats?.();                          // Today badge
      if (document.querySelector('.board')?.dataset.slug === board) {  // already looking at it: show the new card
        window.toast.later(data.message, data.undo);
        location.reload();
      } else {
        window.toast(data.message, data.undo);
      }
      return;
    }
    const r = action === 'list' || action === 'area'
      ? await fetch(action === 'list' ? fab.dataset.listUrl : fab.dataset.areaUrl,
          { method: 'POST', body: new URLSearchParams({ name }) })
      : await fetch(fab.dataset.boardUrl, { method: 'POST', body: new URLSearchParams({ title: name }) });
    if (!r.ok) {
      input.setCustomValidity('That name is taken or not allowed');
      input.reportValidity();
      return;
    }
    if (action === 'list' || action === 'area') location.reload();
    else location.href = r.url;                     // the server redirected to the new board
  });
})();
