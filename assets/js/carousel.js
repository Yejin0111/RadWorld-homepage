// Carousels: one slide per task or case, with numbered tabs, previous and next buttons, swipe and the
// arrow keys. Markup:
//
//   .carousel[data-carousel]
//     .carousel-bar > .carousel-tabs > button[role=tab] (one per slide), .carousel-pager
//     .carousel-viewport > .carousel-track > .slide (one per tab)
//     .carousel-side (optional large buttons beside the slide)
//
// Any button with data-step="-1" or "1" moves by that many slides. On wide screens the viewport keeps
// the height of the tallest slide, so the page below does not move when the slide changes (data-fit=
// "slide" makes it follow the current slide instead, as it always does on phones). The large side buttons sit level with the .slide-media of
// the current slide, and slides out of view are inert. Each change fires 'slidechange' on the
// carousel, detail { index, slide }.

const SWIPE_PX = 48;
// Gestures that start on these belong to the content (slice viewers, sliders, charts), not the carousel.
const OWN_GESTURE = '.pane, .controls, input, select, textarea, button, a, .chart, .load-cover, .show-view';

export function initCarousels(root = document) {
  root.querySelectorAll('[data-carousel]').forEach(setup);
}

function setup(car) {
  const viewport = car.querySelector('.carousel-viewport');
  const track = car.querySelector('.carousel-track');
  const slides = [...track.children];
  const tabs = [...car.querySelectorAll('.carousel-tabs [role="tab"]')];
  const steps = [...car.querySelectorAll('[data-step]')];
  const count = car.querySelector('.carousel-count');
  const id = car.id || 'carousel';
  let index = 0;

  slides.forEach((s, i) => {
    s.id = s.id || `${id}-slide-${i + 1}`;
    s.setAttribute('aria-roledescription', 'slide');
    const tab = tabs[i];
    if (tab) {
      tab.id = tab.id || `${id}-tab-${i + 1}`;
      tab.setAttribute('aria-controls', s.id);
      s.setAttribute('aria-labelledby', tab.id);
    }
  });

  // one height for all slides on wide screens. On phones the slides differ too much (charts stack), so
  // the viewport follows the current slide there.
  const equal = () => car.dataset.fit !== 'slide' && window.innerWidth > 900;
  const sync = () => car.classList.toggle('is-equal', equal());

  // viewport height: the tallest slide (or the current one), the side buttons level with its media
  const fit = () => {
    const slide = slides[index];
    const border = viewport.offsetHeight - viewport.clientHeight;  // the height set includes the border
    const h = equal() ? Math.max(...slides.map((x) => x.offsetHeight)) : slide.offsetHeight;
    viewport.style.height = `${h + border}px`;
    const media = slide.querySelector('.slide-media') || slide;
    const m = media.getBoundingClientRect();
    const c = car.getBoundingClientRect();
    if (m.height) car.style.setProperty('--side-top', `${(m.top - c.top + m.height / 2).toFixed(1)}px`);
  };

  const go = (i, { focus = false, silent = false } = {}) => {
    index = Math.max(0, Math.min(slides.length - 1, i));
    track.style.transform = `translateX(${-100 * index}%)`;
    slides.forEach((s, k) => {
      const on = k === index;
      s.inert = !on;
      s.setAttribute('aria-hidden', String(!on));
      const tab = tabs[k];
      if (tab) {
        tab.setAttribute('aria-selected', String(on));
        tab.tabIndex = on ? 0 : -1;
      }
    });
    steps.forEach((b) => {
      const to = index + Number(b.dataset.step);
      b.disabled = to < 0 || to > slides.length - 1;
    });
    if (count) count.textContent = `${index + 1} / ${slides.length}`;
    if (focus && tabs[index]) tabs[index].focus();
    revealTab();
    fit();
    if (!silent) car.dispatchEvent(new CustomEvent('slidechange', { detail: { index, slide: slides[index] } }));
  };

  // on phones the tabs scroll in one row: keep the current tab in view and drop the edge fade at the end
  const tablist = car.querySelector('.carousel-tabs');
  function revealTab() {
    const t = tabs[index];
    if (!tablist || !t || tablist.scrollWidth <= tablist.clientWidth) return;
    const tr = t.getBoundingClientRect(), lr = tablist.getBoundingClientRect();
    if (tr.left < lr.left) tablist.scrollLeft -= lr.left - tr.left + 8;
    else if (tr.right > lr.right - 28) tablist.scrollLeft += tr.right - lr.right + 36;
  }
  const atEnd = () => tablist && tablist.classList.toggle('at-end', tablist.scrollLeft + tablist.clientWidth >= tablist.scrollWidth - 2);
  if (tablist) tablist.addEventListener('scroll', atEnd, { passive: true });

  tabs.forEach((t, i) => t.addEventListener('click', () => go(i)));
  steps.forEach((b) => b.addEventListener('click', () => go(index + Number(b.dataset.step))));
  if (tablist) {
    tablist.addEventListener('keydown', (e) => {
      const to = { ArrowLeft: index - 1, ArrowRight: index + 1, Home: 0, End: slides.length - 1 }[e.key];
      if (to === undefined) return;
      e.preventDefault();
      go(to, { focus: true });
    });
  }

  // horizontal swipe on the slide, outside the viewers and charts
  let start = null;
  viewport.addEventListener('pointerdown', (e) => {
    start = e.pointerType === 'mouse' || e.target.closest(OWN_GESTURE) ? null : { x: e.clientX, y: e.clientY };
  });
  viewport.addEventListener('pointerup', (e) => {
    if (!start) return;
    const dx = e.clientX - start.x, dy = e.clientY - start.y;
    start = null;
    if (Math.abs(dx) > SWIPE_PX && Math.abs(dx) > 1.5 * Math.abs(dy)) go(index + (dx < 0 ? 1 : -1));
  });
  viewport.addEventListener('pointercancel', () => { start = null; });

  if ('ResizeObserver' in window) {
    const ro = new ResizeObserver(() => fit());
    slides.forEach((s) => ro.observe(s));
  }
  window.addEventListener('resize', () => { sync(); fit(); atEnd(); });
  sync();
  go(0, { silent: true });
  atEnd();
  car.classList.add('is-ready');
  return { go };
}
