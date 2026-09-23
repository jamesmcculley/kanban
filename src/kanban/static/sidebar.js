// Sidebar size: Regular -> Skinny -> Hidden -> Regular. Two buttons drive the same cycle: one
// inside the sidebar (visible at Regular/Skinny), one a slim rail fixed at the edge (visible only
// at Hidden, since the sidebar itself is gone then) -- clicking the rail lands on Regular directly
// because Hidden -> Regular is the wrap-around step, not a detour through Skinny.
window.SidebarMode = (() => {
  const root = document.documentElement;
  const MODES = ['regular', 'skinny', 'hidden'];
  const get = () => { try { return localStorage.getItem('sidebar-mode') || 'regular'; } catch { return 'regular'; } };
  function set(mode) {
    if (mode === 'regular') root.removeAttribute('data-sidebar'); else root.setAttribute('data-sidebar', mode);
    try { localStorage.setItem('sidebar-mode', mode); } catch { /* ignore */ }
  }
  document.querySelectorAll('[data-sidebar-toggle]').forEach(btn => btn.addEventListener('click', () => {
    set(MODES[(MODES.indexOf(get()) + 1) % MODES.length]);
  }));
  return { get, set };
})();

// Sidebar width: drag the handle on its right edge, or type a number in Settings -- either way
// writes the same 'sidebar-width' localStorage key (read pre-paint by _theme_boot.html), so
// dragging on any page is what Settings' number field shows next time it's opened.
window.SidebarWidth = (() => {
  const root = document.documentElement;
  const DEFAULT = 230, MIN = 180, MAX = 420;
  const clamp = n => Math.min(MAX, Math.max(MIN, n));
  const get = () => {
    try {
      const saved = parseInt(localStorage.getItem('sidebar-width'), 10);
      return saved >= MIN && saved <= MAX ? saved : DEFAULT;
    } catch { return DEFAULT; }
  };
  function set(px) {
    px = clamp(Math.round(px));
    root.style.setProperty('--sidebar-width', px + 'px');
    try { localStorage.setItem('sidebar-width', String(px)); } catch { /* ignore */ }
    return px;
  }
  function reset() {
    root.style.removeProperty('--sidebar-width');
    try { localStorage.removeItem('sidebar-width'); } catch { /* ignore */ }
    return DEFAULT;
  }
  return { get, set, reset, DEFAULT, MIN, MAX };
})();

(() => {
  const handle = document.querySelector('[data-sidebar-resize]');
  const sidebar = document.querySelector('.sidebar');
  if (!handle || !sidebar) return;
  let startX = 0, startWidth = 0;
  const onMove = e => {
    const x = e.touches ? e.touches[0].clientX : e.clientX;
    window.SidebarWidth.set(startWidth + (x - startX));
  };
  const onUp = () => {
    handle.classList.remove('active');
    document.removeEventListener('mousemove', onMove);
    document.removeEventListener('mouseup', onUp);
    document.removeEventListener('touchmove', onMove);
    document.removeEventListener('touchend', onUp);
  };
  const onDown = e => {
    if (window.SidebarMode.get() !== 'regular') return;  // only Regular has a variable width
    startX = e.touches ? e.touches[0].clientX : e.clientX;
    startWidth = sidebar.getBoundingClientRect().width;
    handle.classList.add('active');
    e.preventDefault();
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
    document.addEventListener('touchmove', onMove);
    document.addEventListener('touchend', onUp);
  };
  handle.addEventListener('mousedown', onDown);
  handle.addEventListener('touchstart', onDown);
})();

// Settings page: the width number field mirrors the current width and applies live as you type --
// but the field's own displayed value is only snapped to the clamped result on blur, not on every
// keystroke, or typing "200" would get clamped mid-entry (e.g. "1" -> 180) and never reach it.
// Dragging the handle (above) keeps this field in sync the other direction, next time it loads.
document.addEventListener('DOMContentLoaded', () => {
  const widthInput = document.getElementById('sidebar-width');
  const widthReset = document.getElementById('sidebar-width-reset');
  if (widthInput) {
    widthInput.value = window.SidebarWidth.get();
    widthInput.addEventListener('input', () => {
      const n = parseInt(widthInput.value, 10);
      if (!Number.isNaN(n)) window.SidebarWidth.set(n);
    });
    widthInput.addEventListener('blur', () => { widthInput.value = window.SidebarWidth.get(); });
  }
  if (widthReset) {
    widthReset.addEventListener('click', () => {
      const px = window.SidebarWidth.reset();
      if (widthInput) widthInput.value = px;
    });
  }
});

// Board sort order: manual (drag, the default) or a client-side re-sort by title/created/updated.
// A personal per-device preference (localStorage), same as theme -- the server's own order (what
// dragging writes) is untouched either way, so switching back to Manual always restores it exactly.
window.BoardSort = (() => {
  const get = () => { try { return localStorage.getItem('board-sort') || 'manual'; } catch { return 'manual'; } };
  function apply(mode) {
    mode = mode || get();
    // Manual mode's pinned-first order is already correct as rendered -- see Store.sidebar().
    if (mode === 'manual') return;
    const keyOf = row => mode === 'alpha' ? row.dataset.title.toLowerCase() : (row.dataset[mode] || '');
    document.querySelectorAll('.boards-unassigned, .area-boards').forEach(container => {
      const rows = [...container.querySelectorAll(':scope > [data-slug]')];
      rows.sort((a, b) => {
        const pa = a.dataset.pinned ? 1 : 0, pb = b.dataset.pinned ? 1 : 0;
        if (pa !== pb) return pb - pa;  // pinned boards float to the top no matter the sort mode
        const ka = keyOf(a), kb = keyOf(b);
        if (ka === kb) return 0;
        const before = ka < kb;
        return (mode === 'alpha') === before ? -1 : 1;  // A-Z, or newest-first for created/updated
      });
      rows.forEach(r => container.appendChild(r));
    });
  }
  function set(mode) {
    try { localStorage.setItem('board-sort', mode); } catch { /* ignore */ }
    location.reload();  // simplest correct way to also re-apply/re-disable the drag handles below
  }
  document.addEventListener('DOMContentLoaded', () => apply());
  return { get, set };
})();

// Sidebar drag-and-drop: reorder boards, move them between areas, reorder areas.
(() => {
  const side = document.querySelector('.sidebar');
  if (!side || !window.Sortable) return;

  const layout = () => {
    const boards = { '': [...side.querySelectorAll('.boards-unassigned > [data-slug]')].map(e => e.dataset.slug) };
    const areas = [];
    side.querySelectorAll('.area').forEach(a => {
      areas.push(a.dataset.area);
      boards[a.dataset.area] = [...a.querySelectorAll('.area-boards > [data-slug]')].map(e => e.dataset.slug);
    });
    return { areas, boards };
  };
  const save = () => fetch(side.dataset.layoutUrl, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(layout()),
  }).then(r => { if (!r.ok) location.reload(); });

  // Keep the Today badge and tag list current after any card change made through htmx.
  // Plain fetch + manual swap: htmx.ajax needs a requester element, and while one is pending
  // htmx silently drops other requests from/into it (this used to swallow "edit card" clicks).
  async function refreshStats() {
    const r = await fetch(side.dataset.statsUrl);
    if (!r.ok) return;
    const t = document.createElement('template');
    t.innerHTML = await r.text();
    t.content.querySelectorAll('[id]').forEach(fresh => {
      const current = document.getElementById(fresh.id);
      if (current) current.replaceWith(fresh);
    });
  }
  window.refreshStats = refreshStats;
  document.body.addEventListener('htmx:afterRequest', e => {
    const verb = e.detail.requestConfig?.verb;
    if (e.detail.successful && verb && verb !== 'get') refreshStats();
  });

  // Dragging a board only makes sense in Manual order -- in any other mode the next reload (or
  // even the next card change's stats refresh) would just re-sort it right back.
  if (window.BoardSort.get() === 'manual') {
    side.querySelectorAll('.boards-unassigned, .area-boards').forEach(el => new Sortable(el, {
      group: 'boards', animation: 150, handle: '.grip', draggable: '[data-slug]', onEnd: save,
    }));
  }
  const areas = side.querySelector('.areas');
  if (areas) new Sortable(areas, { animation: 150, handle: '.area-grip', draggable: '.area', onEnd: save });
})();

// Which sidebar sections show: applied pre-paint by _theme_boot.html (data-sidebar-hide on <html>,
// read from the same 'sidebar-hide' localStorage key); this just keeps that key in sync and gives
// the current page a live preview when you're looking at Settings' own sidebar as you toggle it.
window.SidebarSections = (() => {
  const get = () => { try { return JSON.parse(localStorage.getItem('sidebar-hide') || '{}'); } catch { return {}; } };
  function set(key, hidden) {
    const hide = get();
    if (hidden) hide[key] = true; else delete hide[key];
    try { localStorage.setItem('sidebar-hide', JSON.stringify(hide)); } catch { /* ignore */ }
    document.documentElement.setAttribute('data-sidebar-hide', Object.keys(hide).join(' '));
  }
  return { get, set };
})();

// Settings page: the sort <select> and "show in sidebar" checkboxes mirror current state and
// apply on change, same pattern as the Appearance section's theme/text-size radios (theme.js).
document.addEventListener('DOMContentLoaded', () => {
  const sortSelect = document.getElementById('board-sort');
  if (sortSelect) {
    sortSelect.value = window.BoardSort.get();
    sortSelect.addEventListener('change', () => window.BoardSort.set(sortSelect.value));
  }
  const hidden = window.SidebarSections.get();
  document.querySelectorAll('input[name="sidebar-show"]').forEach(cb => {
    cb.checked = !hidden[cb.value];
    cb.addEventListener('change', () => window.SidebarSections.set(cb.value, !cb.checked));
  });
});
