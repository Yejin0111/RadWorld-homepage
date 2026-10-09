// The world-model figure under the title. The RadWorld band shows the learned distribution of 3D scans
// as ridgelines, as in Figure 1b of the paper: each kind of input picks out one peak (a pink point),
// and the scan next to it is generated from there. Dashed arrows join each input to the band and the
// band to each generated scan. On wide screens the band runs across the page, with the inputs above it
// and the scans below. On phones it runs down the middle, with the inputs on its left and the scans on
// its right, and the ridgelines turn with it. Everything is redrawn when the figure resizes.

const NS = 'http://www.w3.org/2000/svg';
const RIDGES = 9;
const PEAKS = [0.95, 0.75, 1, 0.82, 0.9];  // relative height of the peak next to each scan

function svg(tag, attrs) {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  return e;
}

// ridge k (0 = back) of a band of length L and depth D, at distance u along it: a gentle swell plus
// one peak at each scan. The ridges rise from the side of the scans and stay clear of RadWorld's name.
function ridge(k, u, L, D, cols) {
  const t = k / (RIDGES - 1);
  const base = D * (0.66 + 0.3 * t);
  const amp = D * (0.05 + 0.24 * t);
  const sigma = L * 0.055;
  let f = 0.12 * (1 + Math.sin(u / L * 9 + k * 1.7)) / 2;
  cols.forEach((c, j) => { f += PEAKS[j % PEAKS.length] * Math.exp(-(((u - c) / sigma) ** 2)); });
  return base - amp * f;
}

function drawBand(el, W, H, cols, down) {
  el.setAttribute('viewBox', `0 0 ${W.toFixed(1)} ${H.toFixed(1)}`);
  el.textContent = '';
  // drawn as if the band ran across, then turned when it runs down
  const L = down ? H : W, D = down ? W : H;
  const at = down ? (u, v) => [v, u] : (u, v) => [u, v];
  const defs = svg('defs', {});
  const grad = svg('linearGradient', { id: 'wm-band', x1: '0', y1: '0', x2: down ? String(W) : '0', y2: down ? '0' : String(H), gradientUnits: 'userSpaceOnUse' });
  grad.append(svg('stop', { offset: '0', 'stop-color': '#2c2c52' }), svg('stop', { offset: '1', 'stop-color': '#4a4a80' }));
  const glow = svg('radialGradient', { id: 'wm-glow' });
  glow.append(svg('stop', { offset: '0', 'stop-color': '#f0c0cc', 'stop-opacity': '0.55' }), svg('stop', { offset: '1', 'stop-color': '#f0c0cc', 'stop-opacity': '0' }));
  defs.append(grad, glow);
  el.append(defs, svg('rect', { x: 0, y: 0, width: W, height: H, fill: 'url(#wm-band)' }));
  const step = Math.max(3, L / 240);
  const xy = ([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`;
  for (let k = 0; k < RIDGES; k++) {  // back to front, each ridge hides the ones behind it
    const pts = [];
    for (let u = 0; u <= L + step; u += step) pts.push(at(Math.min(u, L), ridge(k, Math.min(u, L), L, D, cols)));
    const line = pts.map(xy).join(' ');
    el.append(
      svg('polygon', { points: `${xy(at(0, D))} ${line} ${xy(at(L, D))}`, fill: 'url(#wm-band)' }),
      svg('polyline', { points: line, class: 'ridge', 'stroke-opacity': (0.22 + 0.6 * (k / (RIDGES - 1))).toFixed(2) }),
    );
  }
  for (const c of cols) {  // the point each input picks out, on the front ridge
    const [cx, cy] = at(c, ridge(RIDGES - 1, c, L, D, cols));
    el.append(svg('circle', { cx, cy, r: 14, fill: 'url(#wm-glow)' }), svg('circle', { cx, cy, r: 4.5, class: 'pick' }));
  }
}

function arrowDown(x, y0, y1) {
  return [svg('line', { x1: x, y1: y0, x2: x, y2: y1 - 6, class: 'wire' }),
    svg('path', { d: `M${x - 4.5} ${y1 - 8} L${x + 4.5} ${y1 - 8} L${x} ${y1} Z`, class: 'head' })];
}

function arrowRight(y, x0, x1) {
  return [svg('line', { x1: x0, y1: y, x2: x1 - 6, y2: y, class: 'wire' }),
    svg('path', { d: `M${x1 - 8} ${y - 4.5} L${x1 - 8} ${y + 4.5} L${x1} ${y} Z`, class: 'head' })];
}

export function initConcept(root = document) {
  const fig = root.querySelector('figure.wm');
  if (!fig) return;
  const band = fig.querySelector('.wm-model');
  const ridges = fig.querySelector('.wm-ridges');
  const wires = fig.querySelector('.wm-wires');
  const ins = [...fig.querySelectorAll('.wm-inputs .wm-in')];
  const outs = [...fig.querySelectorAll('.wm-outputs .wm-out')];

  const draw = () => {
    const b = band.getBoundingClientRect();
    if (!b.width) return;
    const down = b.height > b.width;  // phones: the band runs down the middle
    const f = fig.getBoundingClientRect();
    const box = (el) => el.getBoundingClientRect();
    const cols = outs.map((o) => { const r = box(o); return down ? r.top + r.height / 2 - b.top : r.left + r.width / 2 - b.left; });
    drawBand(ridges, b.width, b.height, cols, down);
    wires.setAttribute('viewBox', `0 0 ${f.width.toFixed(1)} ${f.height.toFixed(1)}`);
    wires.textContent = '';
    if (down) {
      ins.forEach((el) => {
        const r = box(el.querySelector('img') || el);
        wires.append(...arrowRight(r.top + r.height / 2 - f.top, r.right - f.left + 6, b.left - f.left - 2));
      });
      outs.forEach((el) => {
        const r = box(el);
        wires.append(...arrowRight(r.top + r.height / 2 - f.top, b.right - f.left + 2, r.left - f.left - 6));
      });
      return;
    }
    ins.forEach((el, i) => {
      const r = box(el);
      const x = (outs[i] ? box(outs[i]).left + box(outs[i]).width / 2 : r.left + r.width / 2) - f.left;
      wires.append(...arrowDown(x, r.bottom - f.top + 8, b.top - f.top - 2));
    });
    outs.forEach((el) => {
      const r = box(el);
      wires.append(...arrowDown(r.left + r.width / 2 - f.left, b.bottom - f.top + 2, r.top - f.top - 22));
    });
  };
  draw();
  if ('ResizeObserver' in window) new ResizeObserver(draw).observe(fig);
  else window.addEventListener('resize', draw);
}
