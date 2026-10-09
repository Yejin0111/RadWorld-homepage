// Page bootstrap: applies site-config.js, fills the BibTeX entry, draws the world-model figure, the
// carousels and the charts, fills the Generation slides and mounts the visual Turing test.

import { escapeHTML } from './viewer.js';
import { mountTuring } from './turing.js';
import { renderCharts } from './charts.js';
import { renderKM } from './km.js';
import { initCarousels } from './carousel.js';
import { initConcept } from './concept.js';
import { initShowcase } from './showcase.js';

const cfg = window.RADWORLD_SITE || { status: 'preprint', links: {} };
const links = { ...(cfg.links || {}) };
if (!links.arxiv && cfg.arxivId) links.arxiv = `https://arxiv.org/abs/${cfg.arxivId}`;

const TITLE = 'A World Foundation Model for 3D Tomographic Medical Imaging';
const AUTHORS = [
  'Ye, Jin', 'Ma, Chenglong', 'Zhang, Lu', 'Su, Yanzhou', 'Liu, Jiyao', 'Li, Wei', 'Wu, Yicheng',
  'Chen, Zhihao', 'Shan, Hongming', 'Chen, Zhaolin', 'Zhuang, Bohan', 'Qiao, Yu', 'Zhang, Junjie',
  'He, Junjun', 'Cai, Jianfei', 'Ji, Yuanfeng',
];

// Public datasets whose derived volumes appear on the page (licence check of 2026-09-25).
const DATASETS = {
  'SynthRAD2025': { license: 'CC BY-NC 4.0 (centers A to C)', url: 'https://zenodo.org/records/14918089' },
  'KiTS2023': { license: 'CC BY-NC-SA 4.0', url: 'https://kits-challenge.org/kits23/' },
  'HCC-TACE-Seg (TCIA)': { license: 'CC BY 4.0', url: 'https://www.cancerimagingarchive.net/collection/hcc-tace-seg/' },
  'Colorectal-Liver-Metastases (TCIA)': { license: 'CC BY 4.0', url: 'https://www.cancerimagingarchive.net/collection/colorectal-liver-metastases/' },
  'QIBA-VolCT-1B (TCIA)': { license: 'CC BY 4.0 and CC BY 3.0', url: 'https://www.cancerimagingarchive.net/analysis-result/qiba-volct-1b/' },
  'RIDER-LungCT-Seg (TCIA)': { license: 'CC BY 3.0', url: 'https://www.cancerimagingarchive.net/analysis-result/rider-lungct-seg/' },
  'QIN-LungCT-Seg (TCIA)': { license: 'CC BY 3.0', url: 'https://www.cancerimagingarchive.net/analysis-result/qin-lungct-seg/' },
  'RIDER Lung CT (TCIA)': { license: 'CC BY 4.0', url: 'https://www.cancerimagingarchive.net/collection/rider-lung-ct/' },
  'MSD Lung': { license: 'CC BY-SA 4.0', url: 'http://medicaldecathlon.com/' },
  'MSD Colon': { license: 'CC BY-SA 4.0', url: 'http://medicaldecathlon.com/' },
  'MSD Pancreas': { license: 'CC BY-SA 4.0', url: 'http://medicaldecathlon.com/' },
  'FedBCa': { license: 'CC BY 4.0', url: 'https://zenodo.org/records/13622759' },
  'PANORAMA': { license: 'CC BY-NC 4.0', url: 'https://panorama.grand-challenge.org/' },
  'Coltea-Lung-CT-100W': { license: 'CC BY-SA 4.0', url: 'https://github.com/ristea/cycle-transformer' },
  'WORD': { license: 'GPL-3.0, research use only', url: 'https://github.com/HiLab-git/WORD' },
  'BraTS 2024 post-treatment glioma': { license: 'CC BY-NC 4.0', url: 'https://www.synapse.org/Synapse:syn53708249/wiki/627500' },
};
// Images on the page that come from the paper's figures rather than from data/gallery.json
const FIGURE_SOURCES = ['BraTS 2024 post-treatment glioma'];  // T1CE slide (Extended Data Figure 5a)

function applyConfig() {
  document.documentElement.dataset.status = cfg.status === 'published' ? 'published' : 'preprint';
  document.querySelectorAll('[data-link]').forEach((a) => {
    const url = links[a.dataset.link];
    if (url) {
      a.href = url;
      if (/^https?:/.test(url)) { a.target = '_blank'; a.rel = 'noopener'; }
    } else {
      a.removeAttribute('href');
      a.classList.add('is-disabled');
      a.setAttribute('aria-disabled', 'true');
      a.title = 'Available soon';
      a.insertAdjacentHTML('beforeend', '<span class="soon">soon</span>');
    }
  });
}

function bibtex() {
  const lines = [];
  for (let i = 0; i < AUTHORS.length; i += 4) lines.push(AUTHORS.slice(i, i + 4).join(' and '));
  const authors = lines.join(' and\n             ');
  const j = cfg.journal || {};
  if (cfg.status === 'published' && j.name) {
    return `@article{ye${j.year || '2026'}radworld,
  title   = {${TITLE}},
  author  = {${authors}},
  journal = {${j.name}},${j.volume ? `\n  volume  = {${j.volume}},` : ''}${j.pages ? `\n  pages   = {${j.pages}},` : ''}
  year    = {${j.year || '2026'}},${j.doi ? `\n  doi     = {${j.doi}},` : ''}
}`;
  }
  return `@article{ye2026radworld,
  title   = {${TITLE}},
  author  = {${authors}},
  journal = {arXiv preprint${cfg.arxivId ? ` arXiv:${cfg.arxivId}` : ''}},
  year    = {2026}
}`;
}

function setupBibtex() {
  const pre = document.getElementById('bibtex-text');
  if (!pre) return;
  pre.textContent = bibtex();
  const btn = document.getElementById('bibtex-copy');
  btn.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(pre.textContent);
      btn.textContent = 'Copied';
    } catch {
      const r = document.createRange();
      r.selectNodeContents(pre);
      const sel = getSelection();
      sel.removeAllRanges();
      sel.addRange(r);
      btn.textContent = 'Press Ctrl+C';
    }
    setTimeout(() => { btn.textContent = 'Copy'; }, 1800);
  });
}

function setupMotion() {
  if (!matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  document.querySelectorAll('img[data-still]').forEach((img) => { img.src = img.dataset.still; });
}

// Highlight the section in view in the top bar.
function setupNav() {
  const navLinks = [...document.querySelectorAll('.topnav a[href^="#"]')];
  const byId = new Map(navLinks.map((a) => [a.getAttribute('href').slice(1), a]));
  if (!('IntersectionObserver' in window)) return;
  const io = new IntersectionObserver((entries) => {
    for (const e of entries) {
      if (!e.isIntersecting) continue;
      navLinks.forEach((a) => a.removeAttribute('aria-current'));
      const a = byId.get(e.target.id);
      if (a) a.setAttribute('aria-current', 'true');
    }
  }, { rootMargin: '-45% 0px -50% 0px' });
  byId.forEach((_, id) => { const s = document.getElementById(id); if (s) io.observe(s); });
}

function fillCredits(gallery, turing) {
  const ul = document.getElementById('data-credits');
  if (!ul) return;
  const used = new Set();
  for (const g of Object.values(gallery.groups || {})) for (const c of g.cases) if (c.source) used.add(c.source);
  for (const c of (turing && turing.cases) || []) used.add(c.source);
  FIGURE_SOURCES.forEach((n) => used.add(n));
  const items = [...used].filter((n) => DATASETS[n]).sort((a, b) => a.localeCompare(b));
  ul.innerHTML = items.map((n) => `<li><a href="${DATASETS[n].url}" target="_blank" rel="noopener">${escapeHTML(n)}</a>, ${licenseLinks(DATASETS[n].license)}</li>`).join('');
}

// "CC BY-NC-SA 4.0" and "GPL-3.0" become links to the license text, as the licenses ask.
function licenseLinks(text) {
  const link = (url, label) => `<a href="${url}" target="_blank" rel="noopener">${label}</a>`;
  return escapeHTML(text)
    .replace(/CC (BY(?:-[A-Z]+)*) (\d\.\d)/g, (m, kind, v) => link(`https://creativecommons.org/licenses/${kind.toLowerCase()}/${v}/`, m))
    .replace(/GPL-3\.0/g, (m) => link('https://www.gnu.org/licenses/gpl-3.0.html', m));
}

async function main() {
  applyConfig();
  setupBibtex();
  setupMotion();
  setupNav();
  initConcept();
  initCarousels();
  renderCharts();
  renderKM();
  initShowcase();

  let gallery = { groups: {} };
  try { gallery = await (await fetch('data/gallery.json')).json(); } catch { /* credits only */ }

  let turing = null;
  try { turing = await (await fetch('data/turing.json')).json(); } catch { /* optional */ }
  fillCredits(gallery, turing);
  const app = document.getElementById('turing-app');
  if (app && turing) mountTuring(app, turing, gallery.windows);
}

main();
