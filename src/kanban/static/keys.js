// Keyboard layer: j/k/h/l select, e edit, x complete, n new, H/L move, / search, ? help.
(() => {
  // htmx activates swapped-in content only after a 20ms "settle" delay, during which a fresh
  // card ignores clicks (fast keyboard users hit this: "x" then "e"). Activate immediately.
  if (window.htmx) htmx.config.defaultSettleDelay = 0;

  const typing = t => t.closest('input, textarea, select, [contenteditable]');
  const select_ = { el: null, id: null };
  const boardCols = () => [...document.querySelectorAll('.column')];
  const colOf = el => el?.closest('.column');

  function select(el) {
    select_.el?.classList.remove('selected');
    select_.el = el;
    select_.id = el?.dataset.id ?? null;
    if (el) { el.classList.add('selected'); el.scrollIntoView({ block: 'nearest' }); }
  }

  function vertical(d) {
    const cur = select_.el;
    const list = [...(cur?.parentElement ?? document).querySelectorAll(
      cur?.closest('.cards') ? ':scope > .card' : '.card, .agenda .row')];
    const all = list.length ? list : [...document.querySelectorAll('.card, .agenda .row')];
    if (!all.length) return;
    const i = cur ? all.indexOf(cur) : -1;
    select(all[Math.max(0, Math.min(all.length - 1, i + d))]);
  }

  function sideways(d) {
    const cols = boardCols();
    if (!cols.length) return;
    const cur = colOf(select_.el);
    const from = cur ? [...cur.querySelectorAll('.card')].indexOf(select_.el) : 0;
    for (let i = cur ? cols.indexOf(cur) + d : 0; i >= 0 && i < cols.length; i += d) {
      const cards = cols[i].querySelectorAll('.card');
      if (cards.length) { select(cards[Math.min(Math.max(from, 0), cards.length - 1)]); return; }
    }
  }

  function shift(d) {
    const el = select_.el, cur = colOf(el), cols = boardCols();
    const to = cur && cols[cols.indexOf(cur) + d];
    if (!to) return;
    const list = to.querySelector('.cards');
    list.append(el);
    window.moveCard(el.dataset.id, to.dataset.column, list.children.length - 1);
    el.scrollIntoView({ block: 'nearest' });
  }

  // Plain fetch, not htmx.ajax: an htmx request with no source element counts as coming from
  // <body>, and while it is in flight htmx drops clicks on anything inside (e.g. a card title).
  window.moveCard = (id, column, index) =>
    fetch(document.querySelector('.board').dataset.moveUrl.replace('ID', id), {
      method: 'POST', body: new URLSearchParams({ column, index }),
    }).then(r => { if (!r.ok) location.reload(); });

  // Reveal a list's "new card" input (it lives under the list header) and focus it.
  window.openAddCard = col => {
    const form = col?.querySelector('.add-card');
    if (!form) return;
    form.hidden = false;
    form.querySelector('input[name=title]').focus();
  };

  // Collapse an empty "new card" input once focus leaves it. Deferred on purpose: collapsing on
  // mousedown shifts the list up before mouseup, so the click (or card drag) that caused the blur
  // would land on the wrong element.
  document.addEventListener('focusout', e => {
    const form = e.target.closest?.('.add-card');
    if (!form) return;
    setTimeout(() => {
      if (!form.querySelector('input[name=title]').value && !form.contains(document.activeElement)) form.hidden = true;
    }, 250);
  });

  const closeOverlays = () => {
    document.querySelectorAll('.backdrop').forEach(b => b.id === 'help' ? (b.hidden = true) : b.remove());
    document.activeElement?.blur();
  };

  let pendingG = false;
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') return closeOverlays();
    // A htmx swap may have replaced the selected card with a fresh copy: follow it by id.
    if (select_.el && !select_.el.isConnected && select_.id) {
      const fresh = document.querySelector(`[data-id="${select_.id}"]`);
      if (fresh) select(fresh);
    }
    if (typing(e.target) || e.metaKey || e.ctrlKey || e.altKey) return;
    if (pendingG) {
      pendingG = false;
      const link = document.querySelector(`.sidebar [data-go="${e.key}"]`);
      if (link) { e.preventDefault(); link.click(); }
      return;
    }
    const el = select_.el;
    switch (e.key) {
      case 'j': vertical(1); break;
      case 'k': vertical(-1); break;
      case 'h': sideways(-1); break;
      case 'l': sideways(1); break;
      case 'H': shift(-1); break;
      case 'L': shift(1); break;
      case 'e': el?.querySelector('.title[hx-get]')?.click(); break;
      case 'x': el?.querySelector('.check')?.click(); break;
      case 'n': openAddCard(colOf(el) ?? boardCols()[0]); break;
      case '/': e.preventDefault(); document.querySelector('.search input')?.focus(); break;
      case '?': { const h = document.getElementById('help'); h.hidden = !h.hidden; break; }
      case 'g': pendingG = true; setTimeout(() => (pendingG = false), 1000); break;
      default: return;
    }
    if ('jkhlHLexn/?g'.includes(e.key)) e.preventDefault();
  });

  // Clicking a card selects it; after htmx swaps a card in place, keep the selection on it.
  document.addEventListener('click', e => {
    const c = e.target.closest('.card, .agenda .row');
    if (c) select(c);
  });
  document.body.addEventListener('htmx:afterSwap', () => {
    if (!select_.id) return;
    const el = document.querySelector(`[data-id="${select_.id}"]`);
    if (el) select(el);
  });
})();
