// Visual Turing test: ten cases drawn from the scans used in the reader study of the paper.
// Nothing is sent anywhere. Answers stay in the page.

import { CaseView, escapeHTML } from './viewer.js';
import { loadVolume } from './nifti.js';
import { renderCharts } from './charts.js';

const ROUNDS = 10;
const MIN_VIEW_MS = 400; // a case must be on screen this long before it can be answered

function shuffle(a) {
  const r = new Uint32Array(a.length);
  (window.crypto || window.msCrypto).getRandomValues(r);
  for (let i = a.length - 1; i > 0; i--) {
    const j = r[i] % (i + 1);
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}
const truthOf = (c) => atob(c.k).split(':')[1];      // 'real' | 'synthetic'
const pct = (x) => `${x.toFixed(1)}%`;

export function mountTuring(root, data, windows) {
  const intro = root.innerHTML; // static intro from index.html
  const ref = data.reference;
  let order = [], n = 0, answers = [], view = null, busy = false;

  const bindStart = () => {
    const b = root.querySelector('[data-role="start"]');
    if (b) b.addEventListener('click', start);
  };
  bindStart();

  function start() {
    order = shuffle(data.cases.slice()).slice(0, ROUNDS);
    n = 0;
    answers = [];
    showCase();
  }

  function preload(c) {
    if (!c) return;
    loadVolume(c.vol);
    loadVolume(c.mask);
  }

  function showCase() {
    const c = order[n];
    busy = true; // until the case has been drawn and shown for MIN_VIEW_MS
    if (view) { view.destroy(); view = null; }
    root.innerHTML = `
      <div class="turing-card">
        <div class="turing-head">
          <div><div class="title">Case ${n + 1} of ${order.length}</div>
          <div class="meta">${escapeHTML(c.type)} · ${escapeHTML(c.modality)}</div></div>
          <div class="dots">${order.map((_, m) => `<i class="${m < n ? 'done' : m === n ? 'now' : ''}"></i>`).join('')}</div>
        </div>
        <div class="turing-body">
          <div class="viewer" data-role="stage"></div>
          <div class="answer">
            <p>Real or synthetic? Scroll through the slices, then decide.</p>
            <button type="button" class="real" data-answer="real" disabled>Real <span class="kbd">R</span></button>
            <button type="button" class="syn" data-answer="synthetic" disabled>Synthetic <span class="kbd">S</span></button>
            <p class="fineprint">The outline marks the tumor, as it did for the radiologists.</p>
          </div>
        </div>
      </div>`;
    const gallery = {
      windows,
      volumes: {
        v: { url: c.vol, dims: c.dims, spacing: c.spacing, encoding: c.encoding, bytes: c.bytes },
        m: { url: c.mask, dims: c.dims, spacing: c.spacing, encoding: { type: 'label' }, bytes: 0 },
      },
    };
    const def = {
      id: c.id, label: c.type, mask: 'm', cross: c.cross, plane: 'axial',
      window: c.windows[0], windows: c.windows, zoom: 1,
      panes: [{ vol: 'v', title: '', mask: 'toggle' }],
    };
    let thisView = null;
    const enable = () => {
      // wait for two frames (the case is painted), then a short dwell, before accepting answers
      requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(() => {
        if (view !== thisView) return;
        busy = false;
        root.querySelectorAll('[data-answer]').forEach((b) => { b.disabled = false; });
      }, MIN_VIEW_MS)));
    };
    view = new CaseView(root.querySelector('[data-role="stage"]'), def, gallery, { layout: 'compare' }, { showMask: true, onLoaded: enable });
    thisView = view;
    view.load();
    preload(order[n + 1]);
    root.querySelectorAll('[data-answer]').forEach((b) => b.addEventListener('click', () => answer(b.dataset.answer)));
  }

  function answer(guess) {
    if (busy || !order.length || n >= order.length || !(view && view.loaded)) return;
    busy = true;
    root.querySelectorAll('[data-answer]').forEach((b) => { b.disabled = true; });
    let thumb = '';
    try {
      const cv = root.querySelector('.pane canvas');
      if (cv && !cv.hidden) thumb = cv.toDataURL('image/jpeg', 0.8);
    } catch { /* ignore */ }
    answers.push({ c: order[n], guess, thumb });
    n += 1;
    if (n < order.length) showCase();
    else finish();
  }

  function finish() {
    if (view) { view.destroy(); view = null; }
    const correct = answers.filter((a) => a.guess === truthOf(a.c)).length;
    const you = (100 * correct) / answers.length;
    const synth = answers.filter((a) => truthOf(a.c) === 'synthetic');
    const synthAsReal = synth.filter((a) => a.guess === 'real').length;
    root.innerHTML = `
      <div class="turing-card">
        <p class="result-score">You classified ${correct} of ${answers.length} cases correctly.</p>
        <p>${synth.length ? `You judged ${synthAsReal} of ${synth.length} synthetic scans to be real. ` : ''}The radiologists did so in ${pct(ref.synthetic_called_real)} of assessments.</p>
        <div class="result-grid">
          <figure class="chart" data-scale="100">
            <figcaption>
              <h3>You and the radiologists</h3>
              <p>Accuracy (%), 50% is chance</p>
            </figcaption>
            <table>
              <thead><tr><th scope="col">Reader</th><th scope="col">Accuracy (%)</th></tr></thead>
              <tbody>
                <tr data-ours><td>You</td><td>${Math.round(you)}</td></tr>
                <tr data-tone="1"><td>Junior radiologists</td><td>${ref.junior.toFixed(1)}</td></tr>
                <tr data-tone="2"><td>All radiologists</td><td>${ref.overall.toFixed(1)}</td></tr>
                <tr data-tone="3"><td>Senior radiologists</td><td>${ref.senior.toFixed(1)}</td></tr>
              </tbody>
            </table>
          </figure>
          <div class="review">${answers.map((a) => {
            const t = truthOf(a.c);
            const ok = a.guess === t;
            return `<figure>${a.thumb ? `<img src="${a.thumb}" alt="">` : ''}<figcaption>
              <span class="tag ${t}">${t === 'real' ? 'Real' : 'Synthetic'}</span> <span class="${ok ? 'ok' : 'bad'}">${ok ? '✓' : '✗'}</span><br>
              ${escapeHTML(a.c.type)}</figcaption></figure>`;
          }).join('')}</div>
        </div>
        <p class="fineprint">With ${answers.length} cropped cases, your score is an informal comparison.</p>
        <p><button type="button" class="turing-start" data-role="again">Try another ten</button></p>
      </div>`;
    renderCharts(root);
    root.querySelector('[data-role="again"]').addEventListener('click', start);
    order = [];
  }

  document.addEventListener('keydown', (e) => {
    if (e.repeat || !order.length || n >= order.length || busy) return;
    const t = e.target;
    if (t && t.closest && t.closest('input, textarea, select, button[data-role="start"]')) return;
    if (e.metaKey || e.ctrlKey || e.altKey || document.querySelector('dialog[open]')) return;
    const r = root.getBoundingClientRect();
    if (r.bottom < 0 || r.top > window.innerHeight) return; // only while the test is on screen
    const k = e.key.toLowerCase();
    if (k === 'r') answer('real');
    else if (k === 's') answer('synthetic');
  });

  return { reset: () => { root.innerHTML = intro; bindStart(); } };
}
