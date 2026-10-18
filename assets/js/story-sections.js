// Each task opens its own existing benchmark table and chart, after a concise overview.
export function initStorySections(root = document) {
  const buttons = [...root.querySelectorAll('#synthetic [data-story-result]')];
  const panels = [...root.querySelectorAll('#synthetic [data-story-panel]')];

  function show(key) {
    panels.forEach((panel) => { panel.hidden = panel.dataset.storyPanel !== key; });
    buttons.forEach((button) => button.setAttribute('aria-expanded', String(button.dataset.storyResult === key)));
    const panel = panels.find((panel) => panel.dataset.storyPanel === key);
    if (!panel) return;
    requestAnimationFrame(() => {
      window.dispatchEvent(new Event('resize'));
      panel.scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start' });
    });
  }

  buttons.forEach((button) => button.addEventListener('click', () => {
    show(button.getAttribute('aria-expanded') === 'true' ? null : button.dataset.storyResult);
  }));
  panels.forEach((panel) => panel.querySelector('[data-story-close]').addEventListener('click', () => {
    show(null);
    buttons.find((button) => button.dataset.storyResult === panel.dataset.storyPanel)?.focus();
  }));
  root.querySelectorAll('.treatment-story-details').forEach((details) => {
    details.addEventListener('toggle', () => window.dispatchEvent(new Event('resize')));
  });
}
