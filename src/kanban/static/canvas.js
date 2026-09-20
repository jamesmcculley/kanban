// Canvas board: drag, resize and edit notes; add links, images and nested boards.
(() => {
  const canvas = document.getElementById('canvas');
  const scroller = document.getElementById('scroller');
  if (!canvas) return;
  const api = canvas.dataset.api;               // POST here to add; PATCH/DELETE api/<id>
  const JSON_HEADERS = { 'Content-Type': 'application/json' };
  const send = (method, url, body) => fetch(url, { method, headers: JSON_HEADERS, body: JSON.stringify(body) });
  let maxZ = Math.max(0, ...[...canvas.children].map(el => +el.style.zIndex || 0));

  function insert(html) {
    const t = document.createElement('template');
    t.innerHTML = html.trim();
    const el = t.content.firstElementChild;
    canvas.append(el);
    maxZ = Math.max(maxZ, +el.style.zIndex || 0);
    document.querySelector('.canvas-hint')?.remove();
    return el;
  }
  async function create(body) {
    const r = await send('POST', api, body);
    return r.ok ? insert(await r.text()) : null;
  }
  async function upload(file, x, y) {
    const fd = new FormData();
    fd.append('file', file, file.name || 'pasted.png');
    fd.append('x', Math.round(x));
    fd.append('y', Math.round(y));
    const r = await fetch(canvas.dataset.upload, { method: 'POST', body: fd });
    return r.ok ? insert(await r.text()) : null;
  }

  // Where new things land: near the middle of what you can see, nudged so they don't stack.
  let nudge = 0;
  function spot() {
    nudge = (nudge + 28) % 140;
    return { x: scroller.scrollLeft + scroller.clientWidth / 2 - 100 + nudge,
             y: scroller.scrollTop + scroller.clientHeight / 2 - 80 + nudge };
  }
  const pointOnCanvas = e => {
    const r = canvas.getBoundingClientRect();
    return { x: e.clientX - r.left, y: e.clientY - r.top };
  };
  function focusEnd(el) {
    el.focus();
    const range = document.createRange();
    range.selectNodeContents(el);
    range.collapse(false);
    const sel = getSelection();
    sel.removeAllRanges();
    sel.addRange(range);
  }

  // -- drag / resize -----------------------------------------------------------------------
  let drag = null;
  let suppressClick = false;

  canvas.addEventListener('pointerdown', e => {
    const item = e.target.closest('.item');
    if (!item || e.button !== 0 || e.target.closest('.item-del, .dot')) return;
    if (e.target.classList.contains('resize')) return startResize(e, item);
    const text = item.querySelector('.item-text');
    if (text && document.activeElement === text) return;      // editing: leave the caret alone
    drag = { item, sx: e.clientX, sy: e.clientY, ox: item.offsetLeft, oy: item.offsetTop, moved: false };
    item.setPointerCapture(e.pointerId);
    e.preventDefault();                                        // no text selection / native image drag
  });
  canvas.addEventListener('pointermove', e => {
    if (!drag) return;
    const dx = e.clientX - drag.sx, dy = e.clientY - drag.sy;
    if (!drag.moved && Math.hypot(dx, dy) < 4) return;
    drag.moved = true;
    drag.item.style.left = Math.max(0, drag.ox + dx) + 'px';
    drag.item.style.top = Math.max(0, drag.oy + dy) + 'px';
  });
  function endDrag(e) {
    if (!drag) return;
    const { item, moved } = drag;
    drag = null;
    if (moved) {
      suppressClick = true;                                    // the click that follows a drag isn't a click
      setTimeout(() => { suppressClick = false; }, 0);
      item.style.zIndex = ++maxZ;
      send('PATCH', `${api}/${item.dataset.id}`, { x: item.offsetLeft, y: item.offsetTop });
    } else if (e.type === 'pointerup') {
      const text = item.querySelector('.item-text');
      if (text) focusEnd(text);                                // plain click on a note = edit it
      // Pointer capture retargets the click onto the wrapper, so follow links ourselves.
      else item.querySelector('a')?.click();
    }
  }
  canvas.addEventListener('pointerup', endDrag);
  canvas.addEventListener('pointercancel', endDrag);
  canvas.addEventListener('click', e => {
    if (suppressClick) { e.preventDefault(); e.stopPropagation(); }
  }, true);

  function startResize(e, item) {
    e.preventDefault();
    e.stopPropagation();
    const sx = e.clientX, w0 = item.offsetWidth;
    item.setPointerCapture(e.pointerId);
    const move = ev => { item.style.width = Math.max(100, w0 + ev.clientX - sx) + 'px'; };
    const up = () => {
      item.removeEventListener('pointermove', move);
      item.removeEventListener('pointerup', up);
      send('PATCH', `${api}/${item.dataset.id}`, { w: item.offsetWidth });
    };
    item.addEventListener('pointermove', move);
    item.addEventListener('pointerup', up);
  }

  // -- delete, colour, text ----------------------------------------------------------------
  canvas.addEventListener('click', async e => {
    const item = e.target.closest('.item');
    if (!item) return;
    if (e.target.closest('.item-del')) {
      const r = await fetch(`${api}/${item.dataset.id}`, { method: 'DELETE' });
      if (r.ok) item.remove();
    } else if (e.target.closest('.dot')) {
      const color = e.target.closest('.dot').dataset.color;
      item.className = item.className.replace(/\bc-\w+/, `c-${color}`);
      send('PATCH', `${api}/${item.dataset.id}`, { color });
    }
  });

  const timers = new Map();
  const saveText = el => {
    const item = el.closest('.item');
    clearTimeout(timers.get(item));
    timers.delete(item);
    send('PATCH', `${api}/${item.dataset.id}`, { text: el.innerText.replace(/\n$/, '') });
  };
  canvas.addEventListener('input', e => {
    const el = e.target.closest('.item-text');
    if (!el) return;
    const item = el.closest('.item');
    clearTimeout(timers.get(item));
    timers.set(item, setTimeout(() => saveText(el), 600));    // debounce; blur flushes immediately
  });
  canvas.addEventListener('focusout', e => {
    const el = e.target.closest?.('.item-text');
    if (el && timers.has(el.closest('.item'))) saveText(el);
  });

  // -- creating things ---------------------------------------------------------------------
  canvas.addEventListener('dblclick', async e => {
    if (e.target !== canvas) return;
    const p = pointOnCanvas(e);
    const el = await create({ kind: 'note', x: p.x, y: p.y });
    if (el) focusEnd(el.querySelector('.item-text'));
  });

  const tools = document.querySelector('.canvas-tools');
  tools.querySelector('[data-tool=note]').addEventListener('click', async () => {
    const s = spot();
    const el = await create({ kind: 'note', x: s.x, y: s.y });
    if (el) focusEnd(el.querySelector('.item-text'));
  });
  const linkBox = tools.querySelector('.tool-link');
  linkBox.addEventListener('keydown', async e => {
    if (e.key !== 'Enter') return;
    e.preventDefault();
    const s = spot();
    const el = await create({ kind: 'link', url: linkBox.value.trim(), x: s.x, y: s.y });
    if (el) { linkBox.value = ''; linkBox.setCustomValidity(''); }
    else { linkBox.setCustomValidity('Enter a full http(s) link'); linkBox.reportValidity(); }
  });
  linkBox.addEventListener('input', () => linkBox.setCustomValidity(''));
  const fileBox = tools.querySelector('.tool-file');
  tools.querySelector('[data-tool=image]').addEventListener('click', () => fileBox.click());
  fileBox.addEventListener('change', async () => {
    for (const f of fileBox.files) { const s = spot(); await upload(f, s.x, s.y); }
    fileBox.value = '';
  });
  const boardForm = tools.querySelector('.tool-board');
  boardForm.addEventListener('submit', async e => {
    e.preventDefault();
    const s = spot();
    const fd = new FormData(boardForm);
    const el = await create({ kind: 'board', title: fd.get('title'), board_kind: fd.get('board_kind'), x: s.x, y: s.y });
    if (el) boardForm.reset();
  });

  // Paste: an image becomes an image, a URL a link, other text a note.
  document.addEventListener('paste', async e => {
    if (e.target.closest?.('input, textarea, [contenteditable]')) return;
    const s = spot();
    const files = [...(e.clipboardData?.files ?? [])].filter(f => f.type.startsWith('image/'));
    if (files.length) {
      e.preventDefault();
      for (const f of files) await upload(f, s.x, s.y);
      return;
    }
    const text = e.clipboardData?.getData('text/plain')?.trim();
    if (!text) return;
    e.preventDefault();
    if (/^https?:\/\/\S+$/.test(text)) create({ kind: 'link', url: text, x: s.x, y: s.y });
    else create({ kind: 'note', text, x: s.x, y: s.y });
  });

  // Drop files (or a dragged link) straight onto the canvas.
  scroller.addEventListener('dragover', e => e.preventDefault());
  scroller.addEventListener('drop', async e => {
    e.preventDefault();
    let { x, y } = pointOnCanvas(e);
    const images = [...e.dataTransfer.files].filter(f => f.type.startsWith('image/'));
    for (const f of images) { await upload(f, x, y); x += 24; y += 24; }
    if (!images.length) {
      const url = (e.dataTransfer.getData('text/uri-list') || e.dataTransfer.getData('text/plain')).trim();
      if (/^https?:\/\/\S+$/.test(url)) create({ kind: 'link', url, x, y });
    }
  });
})();
