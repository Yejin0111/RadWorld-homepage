// Presentation controls preserve the existing samples, chart tables and viewers.
export function initPresentation(root = document) {
  const fold = (node, label) => {
    if (!node || node.closest('.benchmark-details')) return;
    const details = document.createElement('details');
    details.className = 'benchmark-details';
    const summary = document.createElement('summary');
    const title = document.createElement('span');
    title.textContent = label;
    const icon = document.createElement('span');
    icon.className = 'detail-icon';
    icon.setAttribute('aria-hidden', 'true');
    icon.textContent = '+';
    summary.append(title, icon);
    node.before(details);
    details.append(summary, node);
    details.addEventListener('toggle', () => {
      if (details.open) requestAnimationFrame(() => window.dispatchEvent(new Event('resize')));
    });
  };
  root.querySelectorAll('#synthetic .evidence > figure.chart').forEach((f) => {
    const labels = { 'cls-auc': 'Classification benchmarks', 'tumor-dice': 'Tumor segmentation benchmarks', report: 'Report generation benchmarks' };
    fold(f, labels[f.dataset.src] || 'View benchmarks');
  });
  fold(root.querySelector('#treatment .results-grid'), 'View survival prediction results');

  const images = [...root.querySelectorAll('.hero-scans img[data-still]')];
  const preference = matchMedia('(prefers-reduced-motion: reduce)');
  const update = () => {
    images.forEach((img) => { img.src = preference.matches ? img.dataset.still : img.dataset.motionSrc; });
  };
  preference.addEventListener('change', update);
  update();
}
