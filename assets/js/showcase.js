// Generation slides: the input, then three views (axial, coronal, sagittal) of the volume RadWorld
// generated from it. data/showcase.json (tools/make_views.py) gives each view as a sprite sheet of
// slices and the slice it opens on. Moving the pointer across a view (dragging on touch screens)
// scrolls through the slices, and leaving it returns to the opening slice. Report cases mark the
// finding with the arrows of Figure 2e on that slice. On the organ-mask slide the mask is blended onto
// the CT while the pointer is on a view (a tap toggles it on touch screens), and the input card shows
// the mask at the same axial slice. Chips switch between cases, with a short fade.

import { escapeHTML } from './viewer.js';

const PLANES = [['axial', 'Axial'], ['coronal', 'Coronal'], ['sagittal', 'Sagittal']];
const touchOnly = () => matchMedia('(hover: none)').matches;
const NS = 'http://www.w3.org/2000/svg';

function setSprite(el, sp) {
  el.style.backgroundImage = `url("${sp.src}")`;
  el.style.backgroundSize = `${sp.cols * 100}% ${sp.rows * 100}%`;
}

function setFrame(el, sp, i) {
  const c = i % sp.cols, r = Math.floor(i / sp.cols);
  el.style.backgroundPosition = `${sp.cols > 1 ? (c / (sp.cols - 1)) * 100 : 0}% ${sp.rows > 1 ? (r / (sp.rows - 1)) * 100 : 0}%`;
}

function preload(src) {
  const img = new Image();
  img.src = src;
  return (img.decode ? img.decode() : Promise.resolve()).catch(() => null);
}

// arrows as in Figure 2e: a shaft and a head pointing at the finding, coordinates in fractions
function drawArrows(svg, arrows) {
  svg.textContent = '';
  for (const [x0, y0, x1, y1] of arrows || []) {
    const ang = Math.atan2(y1 - y0, x1 - x0);
    const L = 4.2, W = 2.6;  // head length and half width, in percent of the view
    const bx = x1 * 100 - L * Math.cos(ang), by = y1 * 100 - L * Math.sin(ang);
    const line = document.createElementNS(NS, 'line');
    Object.entries({ x1: x0 * 100, y1: y0 * 100, x2: bx, y2: by }).forEach(([k, v]) => line.setAttribute(k, v.toFixed(2)));
    const head = document.createElementNS(NS, 'path');
    head.setAttribute('d', `M${(x1 * 100).toFixed(2)} ${(y1 * 100).toFixed(2)} L${(bx + W * Math.sin(ang)).toFixed(2)} ${(by - W * Math.cos(ang)).toFixed(2)} L${(bx - W * Math.sin(ang)).toFixed(2)} ${(by + W * Math.cos(ang)).toFixed(2)} Z`);
    svg.append(line, head);
  }
}

function inputCard(kind, c) {
  if (kind === 'request') {
    return `<p class="show-label">Request</p><ul class="show-tags">${c.input.tags.map((t) => `<li>${escapeHTML(t)}</li>`).join('')}</ul>`;
  }
  if (kind === 'report') {  // the report's sentence with the finding, shown as an excerpt
    return `<p class="show-label">Radiology report</p><blockquote>“…\u00a0${escapeHTML(c.input.text)}\u00a0…”</blockquote>`;
  }
  return '<p class="show-label">Organ mask</p><div class="slice mask"></div>';
}

function mount(root, kind, cases) {
  const hint = kind === 'mask'
    ? (touchOnly() ? 'Tap an image to show the mask and drag across it to scroll through the slices' : 'Point at an image to show the mask and move across it to scroll through the slices')
    : (touchOnly() ? 'Drag across an image to scroll through the slices' : 'Move across an image to scroll through the slices');
  root.innerHTML = `
    <div class="show-cases" role="group" aria-label="Examples">${cases.map((c, n) =>
      `<button type="button" class="chip" aria-pressed="${n === 0}">${escapeHTML(c.label)}</button>`).join('')}</div>
    <div class="show-grid">
      <div class="show-input" data-kind="${kind}"></div>
      ${PLANES.map(([p, label]) => `<figure class="show-view" data-plane="${p}" role="img"><div class="slice"></div>${kind === 'mask' ? '<div class="slice overlay"></div>' : ''}<svg class="arrows" viewBox="0 0 100 100" aria-hidden="true"></svg><figcaption>${label}</figcaption></figure>`).join('')}
    </div>
    <p class="show-hint">${hint}</p>`;
  const grid = root.querySelector('.show-grid');
  const card = root.querySelector('.show-input');
  const chips = [...root.querySelectorAll('.show-cases .chip')];
  const views = Object.fromEntries(PLANES.map(([p]) => [p, root.querySelector(`.show-view[data-plane="${p}"]`)]));
  let current = null;
  let token = 0;

  const show = (plane, i) => {
    const v = current.views[plane];
    const el = views[plane];
    setFrame(el.querySelector('.slice'), v.sprite, i);
    const ov = el.querySelector('.overlay');
    if (ov && v.overlay) setFrame(ov, v.overlay, i);
    if (plane === 'axial' && v.mask) setFrame(card.querySelector('.slice.mask'), v.mask, i);
    el.querySelector('.arrows').classList.toggle('off', i !== v.start);
    el.dataset.index = String(i);
  };
  const reset = (plane) => show(plane, current.views[plane].start);

  const select = async (n) => {
    const c = cases[n];
    const mine = ++token;
    chips.forEach((b, m) => b.setAttribute('aria-pressed', String(m === n)));
    grid.classList.add('is-switching');
    const srcs = PLANES.flatMap(([p]) => [c.views[p].sprite.src, c.views[p].overlay && c.views[p].overlay.src, c.views[p].mask && c.views[p].mask.src]).filter(Boolean);
    await Promise.all(srcs.map(preload));
    if (mine !== token) return;  // a later choice won
    current = c;
    card.innerHTML = inputCard(kind, c);
    for (const [p, label] of PLANES) {
      const v = c.views[p];
      const el = views[p];
      setSprite(el.querySelector('.slice'), v.sprite);
      const ov = el.querySelector('.overlay');
      if (ov && v.overlay) setSprite(ov, v.overlay);
      if (p === 'axial' && v.mask) setSprite(card.querySelector('.slice.mask'), v.mask);
      drawArrows(el.querySelector('.arrows'), p === 'axial' ? v.arrows : null);
      el.setAttribute('aria-label', `${label} view of the ${c.label} RadWorld generated`);
      reset(p);
    }
    requestAnimationFrame(() => grid.classList.remove('is-switching'));
  };

  for (const [p] of PLANES) {
    const el = views[p];
    let down = null;  // touch: where the finger went down
    const at = (e) => {
      const r = el.getBoundingClientRect();
      const f = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width));
      return Math.round(f * (current.views[p].sprite.n - 1));
    };
    el.addEventListener('pointerenter', (e) => { if (current && e.pointerType === 'mouse') el.classList.add('is-active'); });
    el.addEventListener('pointermove', (e) => {
      if (!current || (e.pointerType !== 'mouse' && !down)) return;
      if (down && Math.abs(e.clientX - down.x) > 6) down.moved = true;
      show(p, at(e));
    });
    el.addEventListener('pointerleave', (e) => {
      if (!current || e.pointerType !== 'mouse') return;
      el.classList.remove('is-active');
      reset(p);
    });
    el.addEventListener('pointerdown', (e) => {
      if (!current || e.pointerType === 'mouse') return;
      down = { x: e.clientX, moved: false };
    });
    const up = () => {
      if (!down) return;
      if (!down.moved) el.classList.toggle('is-active');  // a tap shows or hides the mask
      down = null;
    };
    el.addEventListener('pointerup', up);
    el.addEventListener('pointercancel', () => { down = null; });
  }
  chips.forEach((b, n) => b.addEventListener('click', () => select(n)));
  if (chips.length < 2) root.querySelector('.show-cases').hidden = true;

  // the sprites load when the slide first comes into view
  const start = () => { if (!current && !token) select(0); };
  if ('IntersectionObserver' in window) {
    const io = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) { start(); io.disconnect(); }
    });
    io.observe(grid);
  } else start();
}

export async function initShowcase(root = document) {
  const slots = [...root.querySelectorAll('.showcase[data-show]')];
  if (!slots.length) return;
  let data;
  try {
    data = await (await fetch('data/showcase.json')).json();
  } catch {
    return;
  }
  for (const slot of slots) {
    const cases = data[slot.dataset.show] || [];
    if (cases.length) mount(slot, slot.dataset.show === 'generation' ? 'request' : slot.dataset.show, cases);
  }
}
