// Per-board filter (text, labels, priority, tags): hides non-matching .card elements in place.
// Entirely client-side against what's already on the page -- no server round-trip, no persistence.
(() => {
  const wrap = document.querySelector('.filter-wrap');
  if (!wrap) return;
  const toggle = wrap.querySelector('[data-filter-toggle]');
  const panel = wrap.querySelector('.filter-panel');
  const textInput = panel.querySelector('.filter-text');
  const clearBtn = panel.querySelector('.filter-clear');
  const status = panel.querySelector('.filter-status');
  const tagsGroup = panel.querySelector('.filter-tags-group');
  const tagsBox = panel.querySelector('.filter-tags');

  // Offer only the tags that actually appear on this board, not every tag in the app.
  const tags = [...new Set([...document.querySelectorAll('.card')]
    .flatMap(c => (c.dataset.tags || '').split(',').filter(Boolean)))].sort();
  if (tags.length) {
    tagsGroup.hidden = false;
    tagsBox.innerHTML = tags.map(t =>
      `<label class="filter-check"><input type="checkbox" class="filter-tag" value="${t}"> #${t}</label>`).join('');
  }

  toggle.addEventListener('click', () => {
    panel.hidden = !panel.hidden;
    if (!panel.hidden) textInput.focus();
  });
  document.addEventListener('click', e => { if (!wrap.contains(e.target)) panel.hidden = true; });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && !panel.hidden) { panel.hidden = true; toggle.focus(); }
  });

  const selected = cls => [...panel.querySelectorAll(`.${cls}:checked`)].map(i => i.value);

  function apply() {
    const text = textInput.value.trim().toLowerCase();
    const priorities = selected('filter-priority');
    const labels = selected('filter-label');
    const wantedTags = selected('filter-tag');
    const active = !!(text || priorities.length || labels.length || wantedTags.length);
    toggle.classList.toggle('active', active);
    clearBtn.hidden = !active;
    let shown = 0, total = 0;
    document.querySelectorAll('.card').forEach(card => {
      total++;
      const title = card.querySelector('.title')?.textContent.toLowerCase() || '';
      const cardLabels = (card.dataset.labels || '').split(',').filter(Boolean);
      const cardTags = (card.dataset.tags || '').split(',').filter(Boolean);
      const priority = card.dataset.priority || 'none';
      const matches = (!text || title.includes(text))
        && (!priorities.length || priorities.includes(priority))
        && (!labels.length || labels.some(l => cardLabels.includes(l)))
        && (!wantedTags.length || wantedTags.some(t => cardTags.includes(t)));
      card.classList.toggle('filter-hidden', !matches);
      if (matches) shown++;
    });
    status.textContent = active ? `Showing ${shown} of ${total}` : '';
  }

  panel.addEventListener('input', apply);
  panel.addEventListener('change', apply);
  clearBtn.addEventListener('click', () => {
    textInput.value = '';
    panel.querySelectorAll('input[type=checkbox]').forEach(cb => (cb.checked = false));
    apply();
  });
})();
