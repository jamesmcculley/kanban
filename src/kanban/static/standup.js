// Standup mode: excluding a card from the report is specific to this page (star, shared with the
// card-edit dialog, lives in ui.js instead). POST then remove the row directly -- no reload
// needed, and it matches "exclude" reading as "gone from what I'm looking at right now."
(() => {
  const main = document.querySelector('.standup');
  if (!main) return;
  document.addEventListener('click', async e => {
    const btn = e.target.closest('.exclude-btn');
    if (!btn) return;
    const row = btn.closest('.row');
    const r = await fetch(btn.dataset.url, {
      method: 'POST',
      body: new URLSearchParams({ board: btn.dataset.board, card: btn.dataset.card, scope: btn.dataset.scope }),
    });
    if (!r.ok) return window.toast('Could not exclude that card');
    row?.remove();
  });
})();
