// Toast bar with Undo. Sources: window.toast(...) from scripts, and the server, which sends
// `HX-Trigger: {"toast": {message, undo?, later?}}` with an htmx response or returns the same
// shape as JSON. `undo` = {url, method?, body?}; pressing Undo calls it and reloads the page.
(() => {
  const PENDING = 'trellis-toast';
  const SHOW_MS = 10000;

  function show(message, undo) {
    const host = document.getElementById('toasts');
    if (!host) return;
    const el = document.createElement('div');
    el.className = 'toast';
    el.setAttribute('role', 'status');
    const text = document.createElement('span');
    text.textContent = message;
    el.append(text);
    if (undo) {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.textContent = 'Undo';
      btn.addEventListener('click', async () => {
        btn.disabled = true;
        const r = await fetch(undo.url, {
          method: undo.method || 'POST',
          body: undo.body ? new URLSearchParams(undo.body) : undefined,
        });
        if (r.ok) return location.reload();
        text.textContent = 'Could not undo that';
        btn.remove();
      });
      el.append(btn);
    }
    const close = document.createElement('button');
    close.type = 'button';
    close.className = 'toast-x';
    close.setAttribute('aria-label', 'Dismiss');
    close.textContent = '×';
    close.addEventListener('click', () => el.remove());
    el.append(close);
    host.append(el);
    setTimeout(() => el.remove(), SHOW_MS);
  }

  // For actions that navigate or reload right after: show the toast on the next page.
  show.later = (message, undo) => {
    try { sessionStorage.setItem(PENDING, JSON.stringify({ message, undo })); } catch { /* private mode */ }
  };
  window.toast = show;

  document.addEventListener('DOMContentLoaded', () => {
    try {
      const pending = sessionStorage.getItem(PENDING);
      if (!pending) return;
      sessionStorage.removeItem(PENDING);
      const { message, undo } = JSON.parse(pending);
      show(message, undo);
    } catch { /* ignore a corrupt entry */ }
  });

  document.addEventListener('toast', e => {
    const t = e.detail || {};
    if (!t.message) return;
    if (t.later) show.later(t.message, t.undo);
    else show(t.message, t.undo);
  });
})();
