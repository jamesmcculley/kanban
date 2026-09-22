// Theme controls (part 2 of engineering-standards/templates/theme.js). The saved theme is applied
// earlier by the inline boot script in <head>; this only changes and reports it.
window.Theme = (() => {
  const THEMES = window.__THEMES || [];
  const root = document.documentElement;

  function syncBrowserChrome() {           // tint the phone status bar / installed-app title bar
    const meta = document.querySelector('meta[name=theme-color]');
    if (meta) meta.setAttribute('content', getComputedStyle(document.body).backgroundColor);
  }
  function set(name) {                     // a theme name, or 'default' (follow the device)
    if (THEMES.includes(name)) root.setAttribute('data-theme', name);
    else { root.removeAttribute('data-theme'); name = 'default'; }
    try { localStorage.setItem('theme', name); } catch { /* ignore */ }
    syncBrowserChrome();
  }
  const get = () => root.getAttribute('data-theme') || 'default';
  function cycle() {                       // Default, then the 12 named themes, then back to Default
    const order = ['default', ...THEMES];
    set(order[(order.indexOf(get()) + 1) % order.length]);
    return get();
  }
  function setSize(size) {
    root.setAttribute('data-font-size', size);
    try { localStorage.setItem('font-size', size); } catch { /* ignore */ }
  }
  const getSize = () => root.getAttribute('data-font-size') || 'medium';

  document.addEventListener('DOMContentLoaded', syncBrowserChrome);
  return { list: THEMES, get, set, cycle, setSize, getSize };
})();

// The sidebar's quick theme toggle: shows the current theme, cycles on click.
document.addEventListener('DOMContentLoaded', () => {
  const btn = document.getElementById('theme-toggle');
  const label = document.getElementById('theme-label');
  const paint = () => { if (label) label.textContent = Theme.get() === 'default' ? 'Default' : Theme.get()[0].toUpperCase() + Theme.get().slice(1); };
  paint();
  btn?.addEventListener('click', () => { Theme.cycle(); paint(); });
});

// Appearance settings: radios that mirror the current theme / text size and apply on change.
document.addEventListener('DOMContentLoaded', () => {
  for (const [name, current, apply] of [['theme', Theme.get, Theme.set], ['text-size', Theme.getSize, Theme.setSize]]) {
    const radios = document.querySelectorAll(`input[name="${name}"]`);
    radios.forEach(r => { r.checked = r.value === current(); r.addEventListener('change', () => apply(r.value)); });
  }
});
