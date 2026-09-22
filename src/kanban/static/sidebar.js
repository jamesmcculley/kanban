// Collapse/expand the sidebar. Two buttons drive the same state: one inside the sidebar (visible
// expanded), one a slim rail fixed at the edge (visible collapsed, since the sidebar itself is
// hidden then and can't hold its own re-expand control).
(() => {
  const root = document.documentElement;
  document.querySelectorAll('[data-sidebar-toggle]').forEach(btn => btn.addEventListener('click', () => {
    const collapsed = root.getAttribute('data-sidebar') !== 'collapsed';
    root.setAttribute('data-sidebar', collapsed ? 'collapsed' : 'expanded');
    try { localStorage.setItem('sidebar-collapsed', collapsed ? '1' : '0'); } catch { /* ignore */ }
  }));
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

  side.querySelectorAll('.boards-unassigned, .area-boards').forEach(el => new Sortable(el, {
    group: 'boards', animation: 150, handle: '.grip', draggable: '[data-slug]', onEnd: save,
  }));
  const areas = side.querySelector('.areas');
  if (areas) new Sortable(areas, { animation: 150, handle: '.area-grip', draggable: '.area', onEnd: save });
})();
