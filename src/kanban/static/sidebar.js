// Sidebar: open or hidden, nothing in between (there used to be a "skinny" icon-rail middle
// state -- removed as unnecessary complexity; a plain on/off toggle was the actual ask). One
// button, living outside <aside> in the markup (see base.html) so it's clickable in both states;
// its own icon flips between a left- and right-pointing chevron via CSS, keyed off data-sidebar.
window.SidebarMode = (() => {
  const root = document.documentElement;
  const MODES = ['regular', 'hidden'];
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

// Hiding individual boards from the sidebar (decluttering, not deleting or archiving): a personal
// per-device preference like sort order and section visibility, so it's localStorage, not a board
// property -- two people sharing this instance can keep a different sidebar. Applied via a
// <style> tag (#hidden-boards-css, created pre-paint by _theme_boot.html) with one rule per
// hidden slug: unlike section visibility's fixed small set of keys, there's no way to write a
// static CSS rule ahead of time for an arbitrary board slug, so the rule text itself is generated.
window.HiddenBoards = (() => {
  const get = () => { try { return JSON.parse(localStorage.getItem('hidden-boards') || '[]'); } catch { return []; } };
  function render(slugs) {
    let style = document.getElementById('hidden-boards-css');
    if (!style) { style = document.createElement('style'); style.id = 'hidden-boards-css'; document.head.appendChild(style); }
    style.textContent = slugs.filter(s => /^[a-z0-9-]+$/.test(s))
      .map(s => `.board-row[data-slug="${s}"]{display:none}`).join('');
    const badge = document.querySelector('[data-hidden-boards-badge]');
    if (badge) { badge.textContent = String(slugs.length); badge.hidden = !slugs.length; }
  }
  function set(slug, hide) {
    const list = get();
    const i = list.indexOf(slug);
    if (hide && i === -1) list.push(slug);
    else if (!hide && i !== -1) list.splice(i, 1);
    try { localStorage.setItem('hidden-boards', JSON.stringify(list)); } catch { /* ignore */ }
    render(list);
  }
  document.addEventListener('DOMContentLoaded', () => render(get()));
  return { get, set };
})();

// Hiding a board directly from its own row (hover-revealed, same pattern as the pin button) --
// the quicker, more discoverable path for the common case of "hide the one I'm looking at."
// The eye-menu checklist next to "Boards" stays as the way to review or restore whatever's hidden.
document.addEventListener('click', e => {
  const btn = e.target.closest('[data-hide-board]');
  if (!btn) return;
  const slug = btn.dataset.hideBoard;
  window.HiddenBoards.set(slug, true);
  const cb = document.querySelector(`.board-eye-check[data-slug="${slug}"]`);
  if (cb) cb.checked = false;
});

document.addEventListener('DOMContentLoaded', () => {
  const hidden = window.HiddenBoards.get();
  document.querySelectorAll('.board-eye-check').forEach(cb => {
    cb.checked = !hidden.includes(cb.dataset.slug);
    cb.addEventListener('change', () => window.HiddenBoards.set(cb.dataset.slug, !cb.checked));
  });
});

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

// Whether each page's own big <h1> shows (Settings > Page titles): same mechanism as
// SidebarSections just above, a different fixed small key set (today/scheduled/logbook) and a
// different attribute, since it's about main-page content rather than the sidebar itself.
window.PageTitles = (() => {
  const get = () => { try { return JSON.parse(localStorage.getItem('page-title-hide') || '{}'); } catch { return {}; } };
  function set(key, hidden) {
    const hide = get();
    if (hidden) hide[key] = true; else delete hide[key];
    try { localStorage.setItem('page-title-hide', JSON.stringify(hide)); } catch { /* ignore */ }
    document.documentElement.setAttribute('data-page-title-hide', Object.keys(hide).join(' '));
  }
  return { get, set };
})();

// Today's three sections (due/overdue, completed today, created today): same idea again, but a
// per-page popover on Today itself rather than a Settings checkbox list, since it's about what
// you want to see on Today right now, not a standing device preference you'd set once and forget.
window.TodaySections = (() => {
  const get = () => { try { return JSON.parse(localStorage.getItem('today-hide') || '{}'); } catch { return {}; } };
  function set(key, hidden) {
    const hide = get();
    if (hidden) hide[key] = true; else delete hide[key];
    try { localStorage.setItem('today-hide', JSON.stringify(hide)); } catch { /* ignore */ }
    document.documentElement.setAttribute('data-today-hide', Object.keys(hide).join(' '));
  }
  return { get, set };
})();

// Review's two sections (Completed, Upcoming): same idea as TodaySections above, and for the same
// reason -- it lives in Review's own filter popover, not Settings, because it's "what do I want to
// see in this report right now" rather than a standing device preference.
window.ReviewSections = (() => {
  const get = () => { try { return JSON.parse(localStorage.getItem('review-hide') || '{}'); } catch { return {}; } };
  function set(key, hidden) {
    const hide = get();
    if (hidden) hide[key] = true; else delete hide[key];
    try { localStorage.setItem('review-hide', JSON.stringify(hide)); } catch { /* ignore */ }
    document.documentElement.setAttribute('data-review-hide', Object.keys(hide).join(' '));
  }
  return { get, set };
})();

// Today's filter icon: reveal/hide its section-checklist panel, and close on an outside click --
// its own class (.today-filter-wrap), not .filter-wrap or .date-filter-wrap, so it can never be
// picked up by filter.js's or the date-filter's own lookups (see AGENTS.md trap 9).
document.addEventListener('click', e => {
  const toggle = e.target.closest('[data-today-filter-toggle]');
  if (toggle) { toggle.nextElementSibling.hidden = !toggle.nextElementSibling.hidden; return; }
  if (!e.target.closest('.today-filter-wrap')) document.querySelectorAll('.today-filter-panel').forEach(m => (m.hidden = true));
});

// Settings page: the sort <select>, "show in sidebar" and "page titles" checkboxes mirror current
// state and apply on change, same pattern as the Appearance section's theme/text-size radios
// (theme.js). Today's own section checkboxes mirror/apply the same way, just on Today itself.
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
  const hiddenTitles = window.PageTitles.get();
  document.querySelectorAll('input[name="page-title-show"]').forEach(cb => {
    cb.checked = !hiddenTitles[cb.value];
    cb.addEventListener('change', () => window.PageTitles.set(cb.value, !cb.checked));
  });
  const hiddenToday = window.TodaySections.get();
  document.querySelectorAll('.today-section-check').forEach(cb => {
    cb.checked = !hiddenToday[cb.dataset.section];
    cb.addEventListener('change', () => window.TodaySections.set(cb.dataset.section, !cb.checked));
  });
  const hiddenReview = window.ReviewSections.get();
  document.querySelectorAll('.review-section-check').forEach(cb => {
    cb.checked = !hiddenReview[cb.dataset.section];
    cb.addEventListener('change', () => window.ReviewSections.set(cb.dataset.section, !cb.checked));
  });
});
