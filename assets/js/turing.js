// Visual Turing test: ten cases drawn from the scans used in the reader study of the paper.
// Nothing is sent anywhere. Answers stay in the page.

import { CaseView, escapeHTML } from './viewer.js';
import { loadVolume } from './nifti.js';

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

export function mountTuring(root, data, windows) {
  const intro = root.innerHTML; // static intro from index.html
  const ref = data.reference;
  let order = [], n = 0, answers = [], view = null, preview = null, busy = false;

  const bindStart = () => {
    const b = root.querySelector('[data-role="start"]');
    if (b) b.addEventListener('click', start);
    root.querySelector('[data-role="experts"]')?.addEventListener('click', showExperts);
  };
  bindStart();

  function createView(host, c, onLoaded) {
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
    return new CaseView(host, def, gallery, { layout: 'compare' }, { showMask: true, onLoaded });
  }

  function showPreview() {
    const host = root.querySelector('[data-role="preview"]');
    const c = data.cases.find((c) => c.modality === 'CT' && c.type === 'Kidney tumor')
      || data.cases.find((c) => c.modality === 'CT');
    if (!host || !c) return;
    preview = createView(host, c);
    preview.load();
  }

  function reset() {
    view?.destroy();
    preview?.destroy();
    view = preview = null;
    order = [];
    busy = false;
    root.innerHTML = intro;
    bindStart();
    showPreview();
  }

  function expertRows() {
    return [
      { label: 'Junior radiologists', value: ref.junior },
      { label: 'Senior radiologists', value: ref.senior },
      { label: 'All radiologists', value: ref.overall, summary: true },
    ];
  }

  function comparisonFigure(rows, title, note) {
    return `<figure class="turing-comparison" aria-labelledby="turing-comparison-title">
      <figcaption><h3 id="turing-comparison-title">${escapeHTML(title)}</h3><p>Accuracy · chance level 50%</p></figcaption>
      <div class="turing-reference-bars">${rows.map((row) => `
        <div class="turing-comparison-row${row.you ? ' is-you' : ''}${row.summary ? ' is-summary' : ''}">
          <span class="turing-comparison-name">${escapeHTML(row.label)}</span>
          <span class="turing-comparison-track" aria-hidden="true"><i style="width:${row.value}%"></i></span>
          <span class="turing-comparison-value">${row.you ? Math.round(row.value) : row.value.toFixed(1)}%</span>
        </div>`).join('')}
      </div>
      <p class="turing-comparison-note">${escapeHTML(note)}</p>
    </figure>`;
  }

  function showExperts() {
    view?.destroy();
    preview?.destroy();
    view = preview = null;
    order = [];
    busy = false;
    root.innerHTML = `<div class="turing-card turing-experts">
      ${comparisonFigure(expertRows(), 'Radiologist reader study', 'Classification of real and generated tumor scans in the full reader study.')}
      <button type="button" class="turing-start" data-role="start">Take the test <span aria-hidden="true">↗</span></button>
      <button type="button" class="turing-score-back" data-role="exit">Back to preview</button>
    </div>`;
    bindStart();
    root.querySelector('[data-role="exit"]').addEventListener('click', reset);
  }

  function compactControls(view) {
    const options = document.createElement('details');
    options.className = 'turing-view-options';
    const summary = document.createElement('summary');
    summary.textContent = 'View options';
    const groups = document.createElement('div');
    groups.className = 'turing-option-groups';
    [...view.ctl.children].filter((group) => !group.classList.contains('slice-group')).forEach((group) => groups.append(group));
    options.append(summary, groups);
    view.ctl.append(options);
  }

  showPreview();

  function start() {
    preview?.destroy();
    preview = null;
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
      <div class="turing-card turing-test">
        <div class="turing-head">
          <p class="turing-case-line"><span class="title">Case ${n + 1} of ${order.length}</span><span class="meta">· ${escapeHTML(c.type)} · ${escapeHTML(c.modality)}</span></p>
        </div>
        <div class="turing-body">
          <div class="viewer" data-role="stage"></div>
          <div class="answer">
            <p>Scroll through the slices, then make your choice.</p>
            <div class="turing-choices">
              <button type="button" class="real" data-answer="real" disabled>Real <span class="kbd">R</span></button>
              <button type="button" class="syn" data-answer="synthetic" disabled>Synthetic <span class="kbd">S</span></button>
            </div>
            <p class="fineprint">The outline marks the tumor.</p>
            <button type="button" class="turing-exit" data-role="exit">Back to preview</button>
          </div>
        </div>
      </div>`;
    let thisView = null;
    const enable = () => {
      // wait for two frames (the case is painted), then a short dwell, before accepting answers
      requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(() => {
        if (view !== thisView) return;
        busy = false;
        root.querySelectorAll('[data-answer]').forEach((b) => { b.disabled = false; });
      }, MIN_VIEW_MS)));
    };
    view = createView(root.querySelector('[data-role="stage"]'), c, enable);
    compactControls(view);
    thisView = view;
    view.load();
    preload(order[n + 1]);
    root.querySelectorAll('[data-answer]').forEach((b) => b.addEventListener('click', () => answer(b.dataset.answer)));
    root.querySelector('[data-role="exit"]').addEventListener('click', reset);
  }

  function answer(guess) {
    if (busy || !order.length || n >= order.length || !(view && view.loaded)) return;
    busy = true;
    root.querySelectorAll('[data-answer]').forEach((b) => { b.disabled = true; });
    answers.push({ c: order[n], guess });
    n += 1;
    if (n < order.length) showCase();
    else finish();
  }

  function finish() {
    if (view) { view.destroy(); view = null; }
    const correct = answers.filter((a) => a.guess === truthOf(a.c)).length;
    const comparison = [
      { label: 'You', value: 100 * correct / answers.length, you: true },
      ...expertRows(),
    ];
    root.innerHTML = `
      <div class="turing-card turing-results">
        <p class="turing-score-label">Your score</p>
        <p class="turing-score" aria-label="${correct} out of ${answers.length} correct"><strong>${correct}</strong><span>/ ${answers.length}</span></p>
        <p class="turing-score-caption">Correct answers</p>
        <button type="button" class="turing-start" data-role="again">Try again <span aria-hidden="true">↗</span></button>
        <button type="button" class="turing-score-back" data-role="exit">Back to preview</button>
        ${comparisonFigure(comparison, 'Your score and the reader study', 'Your score is based on this ten-case demo. Radiologist results come from the full reader study.')}
      </div>`;
    root.querySelector('[data-role="again"]').addEventListener('click', start);
    root.querySelector('[data-role="exit"]').addEventListener('click', reset);
    order = [];
  }

  document.addEventListener('keydown', (e) => {
    if (e.repeat || !order.length || n >= order.length || busy) return;
    const t = e.target;
    if (t && t.closest && t.closest('input, textarea, select, summary, button[data-role="start"], button[data-role="exit"]')) return;
    if (e.metaKey || e.ctrlKey || e.altKey || document.querySelector('dialog[open]')) return;
    const r = root.getBoundingClientRect();
    if (r.bottom < 0 || r.top > window.innerHeight) return; // only while the test is on screen
    const k = e.key.toLowerCase();
    if (k === 'r') answer('real');
    else if (k === 's') answer('synthetic');
  });

  return { reset };
}
