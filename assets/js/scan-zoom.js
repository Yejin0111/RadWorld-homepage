// Phones: the scans of a Translation or Treatment slide are a third of the screen wide. A tap on one
// opens the slide's scans one at a time at full width, a tab or a swipe apart, so the generated and
// the real scan can be flipped at one size. The panes keep stepping through the slices with the slide
// (assets/js/scan-sweeps.js), and the carousel holds the slide while the view is open. The source pane
// of the T1CE slide opens as its three sequences.

const PHONE = '(max-width: 760px)';
const SWIPE_PX = 40;
// short names for the tabs; the full caption shows under the scan
const TAB = { input: 'Source', radworld: 'RadWorld', real: 'Target', pre: 'Pre-treatment', virtual: 'Virtual', post: 'Acquired' };

const text = (el) => (el ? el.textContent.trim() : '');

function entries(slide) {
  const out = [];
  for (const fig of slide.querySelectorAll('.scan-comparison .tr-frame')) {
    const sweep = fig.querySelector('.tr-sweep');
    const img = fig.querySelector('img');
    const title = text(fig.querySelector('figcaption h3'));
    const sequences = [...fig.querySelectorAll('[data-sequence]')];
    if (sequences.length) {
      for (const b of sequences) {
        out.push({ fig, tab: text(b), title, sub: text(b), still: b.dataset.src, alt: `Input ${text(b)} MRI`,
          slide: sweep?.dataset.sweepSlide, pane: b.dataset.sequence, current: b.getAttribute('aria-pressed') === 'true' });
      }
    } else {
      out.push({ fig, tab: TAB[sweep?.dataset.sweepPane] || title, title, sub: text(fig.querySelector('figcaption p')),
        still: img.getAttribute('src'), alt: img.alt, slide: sweep?.dataset.sweepSlide, pane: sweep?.dataset.sweepPane, current: true });
    }
  }
  return out;
}

// "Setting: CBCT → CT" from the slide head, whose arrow is an element
const setting = (slide) => [...(slide.querySelector('.slide-head h3')?.childNodes || [])]
  .map((n) => (n.nodeName === 'I' ? '→' : n.textContent.trim())).filter(Boolean).join(' ');

export function initScanZoom(root = document) {
  const phone = matchMedia(PHONE);
  if (!root.querySelector('.scan-comparison') || typeof HTMLDialogElement !== 'function') return;

  const dialog = document.createElement('dialog');
  dialog.className = 'scan-zoom';
  dialog.tabIndex = -1;  // focus lands on the view, not on its close button (Safari would ring it)
  dialog.innerHTML = `
    <div class="scan-zoom-head"><p class="scan-zoom-setting"></p><button type="button" class="scan-zoom-close" aria-label="Close enlarged view"><span aria-hidden="true">×</span></button></div>
    <div class="scan-zoom-stage"></div>
    <p class="scan-zoom-caption"><strong></strong><span></span></p>
    <div class="scan-zoom-tabs" role="group" aria-label="Choose a scan"></div>`;
  document.body.appendChild(dialog);
  const stage = dialog.querySelector('.scan-zoom-stage');
  const tabs = dialog.querySelector('.scan-zoom-tabs');
  let items = [], index = 0, carousel = null;

  const show = (i) => {
    index = (i + items.length) % items.length;
    [...stage.children].forEach((pane, k) => { pane.hidden = k !== index; });
    [...tabs.children].forEach((b, k) => b.setAttribute('aria-pressed', String(k === index)));
    dialog.querySelector('.scan-zoom-caption strong').textContent = items[index].title;
    dialog.querySelector('.scan-zoom-caption span').textContent = items[index].sub;
  };

  const open = (slide, fig) => {
    items = entries(slide);
    if (!items.length) return;
    dialog.dataset.slide = items[0].slide || '';
    dialog.setAttribute('aria-label', `Enlarged scans, ${setting(slide)}`);
    dialog.querySelector('.scan-zoom-setting').textContent = setting(slide);
    stage.innerHTML = items.map((e) => `<div class="scan-zoom-pane" hidden><img src="${e.still}" alt="${e.alt.replace(/"/g, '&quot;')}" width="320" height="320">${e.slide ? `<div class="tr-sweep" data-sweep-slide="${e.slide}" data-sweep-pane="${e.pane}" aria-hidden="true"></div>` : ''}</div>`).join('');
    tabs.innerHTML = items.map((e, k) => `<button type="button" data-zoom-index="${k}">${e.tab}</button>`).join('');
    carousel = slide.closest('[data-carousel]');
    if (carousel) carousel.dataset.hold = 'zoom';
    dialog.showModal();
    dialog.focus();
    show(Math.max(0, items.findIndex((e) => e.fig === fig && e.current)));
    stage.querySelectorAll('.tr-sweep').forEach((el) => el.dispatchEvent(new CustomEvent('sweep-pane', { bubbles: true })));
  };

  dialog.addEventListener('close', () => {
    if (carousel) delete carousel.dataset.hold;
    stage.innerHTML = '';
    delete dialog.dataset.slide;
  });
  dialog.querySelector('.scan-zoom-close').addEventListener('click', () => dialog.close());
  dialog.addEventListener('click', (e) => { if (e.target === dialog) dialog.close(); });  // the empty area around
  tabs.addEventListener('click', (e) => {
    const b = e.target.closest('[data-zoom-index]');
    if (b) show(Number(b.dataset.zoomIndex));
  });
  dialog.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') { e.preventDefault(); show(index + (e.key === 'ArrowLeft' ? -1 : 1)); }
  });
  let start = null;
  stage.addEventListener('pointerdown', (e) => { start = { x: e.clientX, y: e.clientY }; });
  stage.addEventListener('pointerup', (e) => {
    if (!start) return;
    const dx = e.clientX - start.x, dy = e.clientY - start.y;
    start = null;
    if (Math.abs(dx) > SWIPE_PX && Math.abs(dx) > 1.5 * Math.abs(dy)) show(index + (dx < 0 ? 1 : -1));
  });
  stage.addEventListener('pointercancel', () => { start = null; });

  root.addEventListener('click', (e) => {
    if (!phone.matches || e.target.closest('button')) return;
    const image = e.target.closest('.scan-comparison .gen-reel-image');
    if (image) open(image.closest('.slide'), image.closest('.tr-frame'));
  });
}
