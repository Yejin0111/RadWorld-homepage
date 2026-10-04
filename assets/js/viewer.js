// Slice viewer for the RadWorld project page.
//
// A group (for example "report" or "translation") has tabs, one per case. A case shows
// panes: either the three planes of one volume ("triplanar") or the same plane of several
// volumes on a shared grid ("compare"). Panes start as static posters and switch to
// canvases when the visitor loads the volumes. All drawing is 2D canvas, no WebGL.

import { loadVolume, decodeTable, greyTable } from './nifti.js';

const PLANES = ['axial', 'coronal', 'sagittal'];
const PLANE_LABEL = { axial: 'Axial', coronal: 'Coronal', sagittal: 'Sagittal' };
const OUTLINE = 'rgba(255, 196, 61, 0.95)';
const CROSS = 'rgba(255, 214, 120, 0.45)';

// ---------------------------------------------------------------- geometry
// Volumes are RAS (i to patient right, j anterior, k superior). Screens show radiological
// convention: patient right on the left, anterior or superior at the top.
function sliceSize([nx, ny, nz], plane) {
  return plane === 'axial' ? [nx, ny] : plane === 'coronal' ? [nx, nz] : [ny, nz];
}
function physAspect(dims, [dx, dy, dz], plane) {
  const [nx, ny, nz] = dims;
  return plane === 'axial' ? (nx * dx) / (ny * dy) : plane === 'coronal' ? (nx * dx) / (nz * dz) : (ny * dy) / (nz * dz);
}
function normalAxis(plane) { return plane === 'axial' ? 2 : plane === 'coronal' ? 1 : 0; }
function screenXY([nx, ny, nz], plane, [i, j, k]) {
  if (plane === 'axial') return [nx - 1 - i, ny - 1 - j];
  if (plane === 'coronal') return [nx - 1 - i, nz - 1 - k];
  return [ny - 1 - j, nz - 1 - k];
}
function voxelAt([nx, ny, nz], plane, c, r, cross) {
  const v = cross.slice();
  if (plane === 'axial') { v[0] = nx - 1 - c; v[1] = ny - 1 - r; }
  else if (plane === 'coronal') { v[0] = nx - 1 - c; v[2] = nz - 1 - r; }
  else { v[1] = ny - 1 - c; v[2] = nz - 1 - r; }
  return v;
}
/** Linear index = base + c * stepC + r * stepR for a slice through `cross`. */
function sliceIndexer([nx, ny, nz], plane, cross) {
  const nxy = nx * ny;
  if (plane === 'axial') return { base: nx - 1 + (ny - 1) * nx + cross[2] * nxy, stepC: -1, stepR: -nx };
  if (plane === 'coronal') return { base: nx - 1 + cross[1] * nx + (nz - 1) * nxy, stepC: -1, stepR: -nxy };
  return { base: cross[0] + (ny - 1) * nx + (nz - 1) * nxy, stepC: -nx, stepR: -nxy };
}
const clamp = (v, lo, hi) => (v < lo ? lo : v > hi ? hi : v);
const NO_ASPECT_RATIO = !(window.CSS && CSS.supports && CSS.supports('aspect-ratio', '1'));
const fmtMB = (b) => (b / 1e6).toFixed(b < 1e7 ? 1 : 0) + ' MB';

// ---------------------------------------------------------------- one pane
class Pane {
  constructor(el, view, spec, plane) {
    this.el = el;
    this.view = view;       // CaseView
    this.spec = spec;       // pane definition from the manifest
    this.plane = plane;
    this.vol = null;
    this.canvas = document.createElement('canvas');
    this.canvas.hidden = true;
    this.canvas.setAttribute('role', 'img');
    this.canvas.setAttribute('aria-label', `${(el.querySelector('.pane-title') || {}).textContent || 'Slice'} view`);
    this.off = document.createElement('canvas');
    this.info = el.querySelector('.pane-info');
    el.appendChild(this.canvas);
    this.bindPointer();
    this.ro = new ResizeObserver(() => { this.fitHeight(); this.view.requestDraw(); });
    this.ro.observe(el);
  }

  fitHeight() {
    if (NO_ASPECT_RATIO) this.el.style.height = `${this.el.clientWidth / physAspect(this.view.dims, this.view.spacing, this.plane)}px`;
  }

  attach(vol, meta) {
    this.vol = vol;
    this.meta = meta;
    this.decoded = decodeTable(meta.encoding);
    // a label map (for example organ masks) is drawn with one colour per label, not a grey window
    this.colors = null;
    if (meta.encoding && meta.encoding.type === 'labelmap') {
      this.colors = new Uint8Array(256 * 3);
      meta.encoding.colors.forEach((c, i) => { this.colors.set(c, i * 3); });
    }
    this.canvas.hidden = false;
    const poster = this.el.querySelector('img.poster');
    if (poster) poster.hidden = true;
  }

  setPlane(plane) {
    this.plane = plane;
    this.el.style.setProperty('--ar', physAspect(this.vol ? this.vol.dims : this.view.dims, this.view.spacing, plane).toFixed(4));
    this.fitHeight();
    const poster = this.el.querySelector('img.poster');
    if (poster && !this.vol) {
      const src = this.spec.posters && this.spec.posters[plane];
      if (src) poster.src = src;
    }
  }

  viewport(W, H) {
    const z = this.view.zoom;
    const sw = W / z, sh = H / z;
    const [cx, cy] = screenXY(this.vol.dims, this.plane, this.view.focus);
    return {
      sx: clamp(cx + 0.5 - sw / 2, 0, W - sw),
      sy: clamp(cy + 0.5 - sh / 2, 0, H - sh),
      sw, sh,
    };
  }

  draw() {
    if (!this.vol) return;
    const { dims, data } = this.vol;
    const [W, H] = sliceSize(dims, this.plane);
    const cross = this.view.cross;
    const winKey = this.spec.fixedWindow || this.view.windowKey;
    const win = this.view.windows[winKey] || { lo: null, hi: null };
    const colors = this.colors;
    const grey = colors ? null : greyTable(this.decoded, win.lo, win.hi);

    if (this.off.width !== W || this.off.height !== H) { this.off.width = W; this.off.height = H; this.img = null; }
    const octx = this.off.getContext('2d');
    if (!this.img) this.img = octx.createImageData(W, H);
    const out = this.img.data;
    const { base, stepC, stepR } = sliceIndexer(dims, this.plane, cross);
    let p = 0;
    for (let r = 0; r < H; r++) {
      let idx = base + r * stepR;
      for (let c = 0; c < W; c++, idx += stepC, p += 4) {
        if (colors) {
          const k = data[idx] * 3;
          out[p] = colors[k]; out[p + 1] = colors[k + 1]; out[p + 2] = colors[k + 2];
        } else {
          const g = grey[data[idx]];
          out[p] = g; out[p + 1] = g; out[p + 2] = g;
        }
        out[p + 3] = 255;
      }
    }
    octx.putImageData(this.img, 0, 0);

    const dpr = Math.min(window.devicePixelRatio || 1, 2.5);
    const cssW = this.el.clientWidth, cssH = this.el.clientHeight;
    if (!cssW || !cssH) return;
    const cw = Math.round(cssW * dpr), ch = Math.round(cssH * dpr);
    if (this.canvas.width !== cw || this.canvas.height !== ch) { this.canvas.width = cw; this.canvas.height = ch; }
    const ctx = this.canvas.getContext('2d');
    const vp = this.viewport(W, H);
    ctx.imageSmoothingEnabled = !colors;  // label edges stay crisp
    ctx.imageSmoothingQuality = 'high';
    ctx.fillStyle = '#000';
    ctx.fillRect(0, 0, cw, ch);
    ctx.drawImage(this.off, vp.sx, vp.sy, vp.sw, vp.sh, 0, 0, cw, ch);
    const kx = cw / vp.sw, ky = ch / vp.sh;
    const X = (x) => (x - vp.sx) * kx, Y = (y) => (y - vp.sy) * ky;

    // tumor mask outline, drawn as pixel edges so it stays crisp when magnified
    const mask = this.view.maskVol;
    const maskMode = this.spec.mask;
    if (mask && (maskMode === 'always' || (maskMode === 'toggle' && this.view.showMask))) {
      const m = mask.data;
      const inside = (c, r) => c >= 0 && r >= 0 && c < W && r < H && m[base + c * stepC + r * stepR] > 0;
      ctx.beginPath();
      for (let r = 0; r < H; r++) {
        for (let c = 0; c < W; c++) {
          if (!inside(c, r)) continue;
          if (!inside(c - 1, r)) { ctx.moveTo(X(c), Y(r)); ctx.lineTo(X(c), Y(r + 1)); }
          if (!inside(c + 1, r)) { ctx.moveTo(X(c + 1), Y(r)); ctx.lineTo(X(c + 1), Y(r + 1)); }
          if (!inside(c, r - 1)) { ctx.moveTo(X(c), Y(r)); ctx.lineTo(X(c + 1), Y(r)); }
          if (!inside(c, r + 1)) { ctx.moveTo(X(c), Y(r + 1)); ctx.lineTo(X(c + 1), Y(r + 1)); }
        }
      }
      ctx.strokeStyle = OUTLINE;
      ctx.lineWidth = Math.max(1, 1.3 * dpr);
      ctx.stroke();
    }

    if (this.view.showCross) {
      const [c, r] = screenXY(dims, this.plane, cross);
      ctx.strokeStyle = CROSS;
      ctx.lineWidth = Math.max(1, dpr);
      ctx.beginPath();
      ctx.moveTo(X(c + 0.5), 0); ctx.lineTo(X(c + 0.5), ch);
      ctx.moveTo(0, Y(r + 0.5)); ctx.lineTo(cw, Y(r + 0.5));
      ctx.stroke();
    }

    if (this.info) {
      const ax = normalAxis(this.plane);
      this.info.textContent = `${PLANE_LABEL[this.plane]} ${cross[ax] + 1}/${dims[ax]}`;
    }
  }

  eventToVoxel(e) {
    const rect = this.canvas.getBoundingClientRect();
    const [W, H] = sliceSize(this.vol.dims, this.plane);
    const vp = this.viewport(W, H);
    const x = vp.sx + ((e.clientX - rect.left) / rect.width) * vp.sw;
    const y = vp.sy + ((e.clientY - rect.top) / rect.height) * vp.sh;
    const c = clamp(Math.floor(x), 0, W - 1), r = clamp(Math.floor(y), 0, H - 1);
    return voxelAt(this.vol.dims, this.plane, c, r, this.view.cross);
  }

  bindPointer() {
    let dragging = false;
    this.canvas.addEventListener('pointerdown', (e) => {
      if (!this.vol || e.button !== 0) return;
      dragging = true;
      this.canvas.setPointerCapture(e.pointerId);
      this.view.setCross(this.eventToVoxel(e));
    });
    this.canvas.addEventListener('pointermove', (e) => {
      if (dragging && this.vol) this.view.setCross(this.eventToVoxel(e));
    });
    const stop = () => { dragging = false; };
    this.canvas.addEventListener('pointerup', stop);
    this.canvas.addEventListener('pointercancel', stop);
    let acc = 0;
    this.canvas.addEventListener('wheel', (e) => {
      if (!this.vol) return;
      const dy = e.deltaY * (e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? 400 : 1);
      if (!dy || Math.abs(e.deltaX) > Math.abs(dy)) return; // horizontal scrolling is left to the page
      e.preventDefault();
      let steps;
      if (Math.abs(dy) >= 50) { steps = 1; acc = 0; } // mouse wheel: one slice per notch
      else { acc += dy; steps = Math.trunc(Math.abs(acc) / 40); if (!steps) return; acc = 0; } // trackpad
      const dir = dy > 0 ? -1 : 1;
      const ax = normalAxis(this.plane);
      const v = this.view.cross.slice();
      v[ax] = clamp(v[ax] + dir * Math.min(steps, 3), 0, this.vol.dims[ax] - 1);
      this.view.setCross(v);
    }, { passive: false });
  }

  destroy() { this.ro.disconnect(); }
}

// ---------------------------------------------------------------- one case
class CaseView {
  constructor(host, def, gallery, group, opts) {
    this.def = def;
    this.gallery = gallery;
    this.group = group;
    this.opts = opts;
    this.layout = group.layout;
    this.windows = gallery.windows;
    this.windowKey = def.window || 'auto';
    this.plane = def.plane || 'axial';
    this.zoom = def.zoom || 1;
    this.showMask = !!opts.showMask;
    // linked panes show the shared position unless the case turns it off (it can cross a lesion)
    this.showCross = def.crosshair ?? (this.layout === 'triplanar' || def.panes.length > 1);
    const first = gallery.volumes[def.panes[0].vol];
    this.dims = first.dims;
    this.spacing = first.spacing;
    this.cross = def.cross.slice();
    this.focus = def.cross.slice();
    this.loaded = false;
    this.drawQueued = false;
    this.el = this.build(host);
  }

  // ---- DOM
  build(host) {
    const d = this.def;
    const wrap = document.createElement('div');
    wrap.className = 'case' + (d.summary || d.textHTML ? ' with-text' : '');

    if (d.summary || d.textHTML) {
      const side = document.createElement('div');
      side.className = 'case-text';
      side.innerHTML = `<div class="label">${escapeHTML(d.inputLabel || 'Input')}</div>` +
        (d.textHTML ? d.textHTML : `<p>${escapeHTML(d.summary)}</p>`) +
        (d.note ? `<p class="case-credit">${escapeHTML(d.note)}</p>` : '');
      wrap.appendChild(side);
    }

    const stage = document.createElement('div');
    stage.className = 'stage';
    const lead = [d.text, this.layout === 'triplanar' ? d.panes[0].title : ''].filter(Boolean).join(' · ');
    if (lead) {
      const p = document.createElement('p');
      p.className = 'case-credit';
      p.style.margin = '0 0 8px';
      p.textContent = lead;
      stage.appendChild(p);
    }
    const panesEl = document.createElement('div');
    panesEl.className = 'panes' + (this.layout === 'compare' ? ' compare' : '');
    panesEl.style.setProperty('--n', d.panes.length);
    stage.appendChild(panesEl);

    this.panes = [];
    const specs = this.layout === 'triplanar'
      ? PLANES.map((pl) => ({ spec: d.panes[0], plane: pl }))
      : d.panes.map((sp) => ({ spec: sp, plane: this.plane }));
    for (const { spec, plane } of specs) {
      const el = document.createElement('div');
      el.className = 'pane';
      el.style.setProperty('--ar', physAspect(this.dims, this.spacing, plane).toFixed(4));
      const poster = spec.posters && spec.posters[plane];
      const title = this.layout === 'triplanar' ? PLANE_LABEL[plane] : spec.title;
      el.innerHTML = (poster ? `<img class="poster" alt="${escapeHTML(title)}" src="${poster}" loading="lazy" decoding="async">` : '') +
        `<div class="pane-title">${escapeHTML(title)}</div><div class="pane-info"></div>`;
      panesEl.appendChild(el);
      this.panes.push(new Pane(el, this, spec, plane));
    }

    // load cover
    const bytes = this.totalBytes();
    this.cover = document.createElement('div');
    this.cover.className = 'load-cover';
    this.cover.innerHTML = `<button class="load-btn" type="button">Explore the 3D volume<small>${fmtMB(bytes)}</small></button>`;
    this.loadBtn = this.cover.querySelector('button');
    this.loadBtn.addEventListener('click', () => this.load());
    stage.appendChild(this.cover);
    stage.appendChild(this.buildControls());

    // d.credit (dataset and case) stays in the manifest for the record; the page credits the
    // datasets once, under Image credits in the footer.
    this.errorEl = document.createElement('div');
    this.errorEl.className = 'error';
    this.errorEl.hidden = true;
    stage.appendChild(this.errorEl);

    wrap.appendChild(stage);
    host.appendChild(wrap);
    this.panesEl = panesEl;
    return wrap;
  }

  buildControls() {
    const d = this.def;
    const ctl = document.createElement('div');
    ctl.className = 'controls';
    ctl.setAttribute('aria-disabled', 'true');
    const parts = [];

    if (this.layout === 'compare') {
      parts.push(`<div class="group" data-role="plane"><span class="ctl-label">Plane</span>` +
        PLANES.map((p) => `<button type="button" class="chip" data-plane="${p}" aria-pressed="${p === this.plane}">${PLANE_LABEL[p]}</button>`).join('') + `</div>`);
    }
    const wins = (d.windows || []).filter((w) => this.windows[w]);
    if (wins.length > 1) {
      parts.push(`<div class="group" data-role="window"><span class="ctl-label">Window</span>` +
        wins.map((w) => `<button type="button" class="chip" data-window="${w}" aria-pressed="${w === this.windowKey}">${escapeHTML(this.windows[w].label)}</button>`).join('') + `</div>`);
    }
    parts.push(`<div class="group slice-group"><span class="ctl-label">Slice</span><input type="range" min="0" max="1" value="0" data-role="slice" aria-label="Slice"><span class="slice-count" data-role="slice-label"></span></div>`);
    parts.push(`<div class="group"><span class="ctl-label">Zoom</span><button type="button" class="chip" data-zoom="out" aria-label="Zoom out">−</button><button type="button" class="chip" data-zoom="in" aria-label="Zoom in">+</button><button type="button" class="chip" data-zoom="reset">Reset</button></div>`);
    // options without a label: crosshair, tumor outline and the 3D view share one row
    const opts = [`<label><input type="checkbox" data-role="cross" ${this.showCross ? 'checked' : ''}> Crosshair</label>`];
    if (d.mask && this.def.panes.some((p) => p.mask === 'toggle')) {
      opts.push(`<label><input type="checkbox" data-role="mask" ${this.showMask ? 'checked' : ''}> Tumor outline</label>`);
    }
    const r3 = this.def.panes.find((p) => p.render3d);
    const r3enc = r3 && (this.gallery.volumes[r3.vol] || {}).encoding;
    if (r3 && this.opts.open3D && r3enc && r3enc.type === 'piecewise') {
      opts.push(`<button type="button" class="chip" data-role="3d">3D rendering</button>`);
    }
    parts.push(`<div class="group opts">${opts.join('')}</div>`);
    ctl.innerHTML = parts.join('');

    ctl.addEventListener('click', (e) => {
      const b = e.target.closest('button');
      if (!b) return;
      if (b.dataset.plane) this.setPlane(b.dataset.plane);
      else if (b.dataset.window) this.setWindow(b.dataset.window);
      else if (b.dataset.zoom) this.setZoom(b.dataset.zoom);
      else if (b.dataset.role === '3d') this.open3D();
    });
    ctl.addEventListener('input', (e) => {
      const t = e.target;
      if (t.dataset.role === 'slice') {
        const v = this.cross.slice();
        v[this.sliceAxis()] = Number(t.value);
        this.setCross(v);
      }
    });
    ctl.addEventListener('change', (e) => {
      const t = e.target;
      if (t.dataset.role === 'cross') { this.showCross = t.checked; this.requestDraw(); }
      if (t.dataset.role === 'mask') { this.showMask = t.checked; this.requestDraw(); }
    });
    this.ctl = ctl;
    this.slider = ctl.querySelector('[data-role="slice"]');
    this.sliceLabel = ctl.querySelector('[data-role="slice-label"]');
    return ctl;
  }

  totalBytes() {
    const keys = new Set(this.def.panes.map((p) => p.vol));
    if (this.def.mask) keys.add(this.def.mask);
    let b = 0;
    for (const k of keys) b += (this.gallery.volumes[k] || {}).bytes || 0;
    return b;
  }

  // ---- loading
  async load() {
    if (this.loaded || this.loading) return;
    this.loading = true;
    this.loadBtn.disabled = true;
    const keys = [...new Set(this.def.panes.map((p) => p.vol).concat(this.def.mask ? [this.def.mask] : []))];
    const total = this.totalBytes();
    const got = new Map();
    const progress = () => {
      let s = 0;
      for (const v of got.values()) s += v;
      this.loadBtn.innerHTML = `Loading<small>${fmtMB(s)} of ${fmtMB(total)}</small>`;
    };
    progress();
    try {
      const vols = await Promise.all(keys.map((k) => loadVolume(this.gallery.volumes[k].url, (n) => {
        got.set(k, Math.min(n, this.gallery.volumes[k].bytes || n));
        progress();
      })));
      const byKey = Object.fromEntries(keys.map((k, n) => [k, vols[n]]));
      if (this.destroyed) return;
      for (const pane of this.panes) pane.attach(byKey[pane.spec.vol], this.gallery.volumes[pane.spec.vol]);
      this.maskVol = this.def.mask ? byKey[this.def.mask] : null;
      this.loaded = true;
      this.cover.remove();
      this.ctl.setAttribute('aria-disabled', 'false');
      this.syncControls();
      this.requestDraw();
      if (this.opts.onLoaded) this.opts.onLoaded();
    } catch (err) {
      this.loading = false;
      this.loadBtn.disabled = false;
      this.loadBtn.innerHTML = 'Retry';
      this.errorEl.hidden = false;
      this.errorEl.textContent = location.protocol === 'file:'
        ? 'Volumes cannot be loaded from a file:// URL. Serve the folder over HTTP (see README).'
        : `Could not load the volumes (${err.message}).`;
    }
  }

  // ---- state changes
  sliceAxis() { return this.layout === 'triplanar' ? 2 : normalAxis(this.plane); }

  setCross(v) {
    const [nx, ny, nz] = this.dims;
    this.cross = [clamp(v[0], 0, nx - 1), clamp(v[1], 0, ny - 1), clamp(v[2], 0, nz - 1)];
    this.syncControls();
    this.requestDraw();
  }

  setPlane(plane) {
    this.plane = plane;
    for (const p of this.panes) p.setPlane(plane);
    this.ctl.querySelectorAll('[data-plane]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.plane === plane)));
    this.syncControls();
    this.requestDraw();
  }

  setWindow(key) {
    this.windowKey = key;
    this.ctl.querySelectorAll('[data-window]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.window === key)));
    this.requestDraw();
  }

  setZoom(how) {
    if (how === 'reset') { this.zoom = this.def.zoom || 1; this.focus = this.def.cross.slice(); }
    else {
      this.zoom = clamp(how === 'in' ? this.zoom * 1.4 : this.zoom / 1.4, 1, 8);
      this.focus = this.cross.slice();
    }
    this.requestDraw();
  }

  syncControls() {
    const ax = this.sliceAxis();
    this.slider.max = String(this.dims[ax] - 1);
    this.slider.value = String(this.cross[ax]);
    const name = this.layout === 'triplanar' ? 'Axial' : PLANE_LABEL[this.plane];
    this.sliceLabel.textContent = `${name} ${this.cross[ax] + 1}/${this.dims[ax]}`;
  }

  requestDraw() {
    if (this.drawQueued || !this.loaded) return;
    this.drawQueued = true;
    requestAnimationFrame(() => {
      this.drawQueued = false;
      for (const p of this.panes) p.draw();
    });
  }

  open3D() {
    const spec = this.def.panes.find((p) => p.render3d);
    const meta = this.gallery.volumes[spec.vol];
    this.opts.open3D({ url: meta.url, encoding: meta.encoding, title: `${this.def.label}: ${spec.title}`, presets: this.def.render3dPresets });
  }

  destroy() {
    this.destroyed = true;
    for (const p of this.panes) p.destroy();
    this.el.remove();
  }
}

// ---------------------------------------------------------------- group with tabs
/**
 * Mount a gallery group into `root`.
 * @param {HTMLElement} root
 * @param {object} gallery   data/gallery.json
 * @param {string} groupKey  key in gallery.groups (may be absent if only pending items exist)
 * @param {object} opts      { pendingGroups: [...], showPending: bool, open3D: fn }
 */
export function mountGroup(root, gallery, groupKey, opts = {}) {
  const group = gallery.groups[groupKey] || { layout: 'compare', cases: [] };
  const pending = opts.showPending
    ? (gallery.pending || []).filter((p) => (opts.pendingGroups || [groupKey]).includes(p.group))
    : [];
  const items = group.cases.map((c) => ({ kind: 'case', def: c })).concat(pending.map((p) => ({ kind: 'pending', def: p })));
  if (!items.length) { root.hidden = true; return null; }

  root.classList.add('viewer');
  root.innerHTML = '';
  const tabs = document.createElement('div');
  tabs.className = 'tabs';
  tabs.setAttribute('role', 'tablist');
  const body = document.createElement('div');
  root.append(tabs, body);

  let current = null;
  let autoload = !!opts.autoload;   // true once the visitor has loaded any volume
  const select = (n) => {
    tabs.querySelectorAll('.tab').forEach((t, m) => t.setAttribute('aria-selected', String(m === n)));
    if (current) current.destroy();
    current = null;
    body.innerHTML = '';
    const it = items[n];
    if (it.kind === 'pending') {
      body.innerHTML = `<div class="pending-box"><b>${escapeHTML(it.def.label)}</b>Sample pending. ${escapeHTML(it.def.note || '')}. Generate it on the GPU server and add it to <code>tools/prepare_assets.py</code>.</div>`;
      return;
    }
    current = new CaseView(body, it.def, gallery, group, {
      ...opts,
      onLoaded: () => { autoload = true; if (opts.onAnyLoaded) opts.onAnyLoaded(); },
    });
    if (autoload) current.load();
  };
  items.forEach((it, n) => {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'tab' + (it.kind === 'pending' ? ' pending' : '');
    b.setAttribute('role', 'tab');
    b.textContent = it.def.label;
    b.addEventListener('click', () => select(n));
    tabs.appendChild(b);
  });
  if (items.length === 1) tabs.hidden = true;
  select(0);
  return {
    select,
    destroy() {
      if (current) current.destroy();
      current = null;
      root.innerHTML = '';
      root.classList.remove('viewer');
    },
  };
}

export function escapeHTML(s) {
  return String(s ?? '').replace(/[&<>"']/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
}

// Exposed for the Turing test, which reuses the pane machinery with a single volume.
export { CaseView, PLANES, PLANE_LABEL };
