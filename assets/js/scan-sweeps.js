// Synchronised axial sweeps on the Translation and Treatment slides. data/sweeps.json
// (tools/make_sweeps.py) gives, per slide, one sprite sheet per pane over the same slices. Each pane
// first shows its still (the key slice of the paper's figure); once a slide is in view its sprites
// load, and all its panes step through the slices together, back and forth from the key slice. A
// slide out of view, a hidden tab or reduced motion keeps the stills.

const STEP_MS = 90;  // as the hero sweeps

export async function initScanSweeps(root = document) {
  const panes = [...root.querySelectorAll('.tr-sweep[data-sweep-slide]')];
  if (!panes.length) return;
  let data;
  try {
    data = await (await fetch('data/sweeps.json')).json();
  } catch {
    return;
  }
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const groups = new Map();
  for (const el of panes) {
    const slide = el.dataset.sweepSlide;
    if (!data[slide]) continue;
    if (!groups.has(slide)) groups.set(slide, { info: data[slide], panes: [], tick: 0, visible: false, loaded: false });
    groups.get(slide).panes.push(el);
  }

  const frame = (g, el) => {
    const sp = g.info.panes[el.dataset.sweepPane];
    if (!sp) return;
    const n = g.info.n, cycle = 2 * (n - 1);
    const t = (g.tick + g.info.start) % cycle;
    const i = t < n ? t : cycle - t;
    el.style.backgroundImage = `url("${sp.sprite}")`;
    el.style.backgroundSize = `${sp.cols * 100}% ${sp.rows * 100}%`;
    el.style.backgroundPosition = `${sp.cols > 1 ? ((i % sp.cols) / (sp.cols - 1)) * 100 : 0}% ${sp.rows > 1 ? (Math.floor(i / sp.cols) / (sp.rows - 1)) * 100 : 0}%`;
  };

  const load = async (g) => {
    if (g.loaded) return;
    g.loaded = true;
    await Promise.all(Object.values(g.info.panes).map((sp) => {
      const img = new Image();
      img.src = sp.sprite;
      return (img.decode ? img.decode() : Promise.resolve()).catch(() => null);
    }));
    g.panes.forEach((el) => { frame(g, el); el.classList.add('is-ready'); });
  };

  // a source switch (the T1CE slide's T1 / T2 / FLAIR buttons) keeps the pane on the same slice
  root.addEventListener('sweep-pane', (e) => {
    const el = e.target.closest?.('.tr-sweep');
    const g = el && groups.get(el.dataset.sweepSlide);
    if (g && g.loaded) frame(g, el);
  });

  const io = 'IntersectionObserver' in window ? new IntersectionObserver((entries) => {
    for (const e of entries) {
      const g = groups.get(e.target.dataset.sweepSlide);
      if (!g) continue;
      g.visible = e.isIntersecting;
      if (g.visible) load(g);
    }
  }, { threshold: 0.35 }) : null;
  for (const g of groups.values()) {
    if (io) io.observe(g.panes[0]);
    else { g.visible = true; load(g); }
  }

  setInterval(() => {
    if (document.hidden || reduced.matches) return;
    for (const g of groups.values()) {
      if (!g.visible || !g.loaded) continue;
      g.tick += 1;
      g.panes.forEach((el) => frame(g, el));
    }
  }, STEP_MS);
  // with reduced motion the panes hold the key slice
  reduced.addEventListener('change', () => {
    for (const g of groups.values()) { g.tick = 0; if (g.loaded) g.panes.forEach((el) => frame(g, el)); }
  });
}
