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

  const selected = cls => [...panel.querySelectorAll(`.${cls}:checked`)].map(i => i.value);

  // Offer only the tags that actually appear on this board, not every tag in the app. Rebuilt
  // every time the panel opens (not just once at load) so a card added since the page loaded
  // shows its tags here too -- cards arrive via htmx after this script has already run once.
  // Built with DOM calls rather than an innerHTML template string: server-side tag names are
  // restricted to [a-z0-9_-] (tags.py), so this is belt-and-suspenders today, but a tag string
  // ending up in innerHTML unescaped is exactly the kind of thing that turns into a real bug the
  // day that invariant quietly changes -- cheaper to just not depend on it here.
  function refreshTagOptions() {
    const wasChecked = new Set(selected('filter-tag'));
    const tags = [...new Set([...document.querySelectorAll('.card')]
      .flatMap(c => (c.dataset.tags || '').split(',').filter(Boolean)))].sort();
    tagsGroup.hidden = !tags.length;
    tagsBox.replaceChildren(...tags.map(t => {
      const label = document.createElement('label');
      label.className = 'filter-check';
      const input = document.createElement('input');
      input.type = 'checkbox';
      input.className = 'filter-tag';
      input.value = t;
      input.checked = wasChecked.has(t);
      label.append(input, document.createTextNode(` #${t}`));
      return label;
    }));
  }
  refreshTagOptions();

  toggle.addEventListener('click', () => {
    panel.hidden = !panel.hidden;
    if (!panel.hidden) { refreshTagOptions(); textInput.focus(); }
  });
  document.addEventListener('click', e => { if (!wrap.contains(e.target)) panel.hidden = true; });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && !panel.hidden) { panel.hidden = true; toggle.focus(); }
  });

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
