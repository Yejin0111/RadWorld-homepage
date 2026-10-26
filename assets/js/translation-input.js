// Keep each source MRI sequence readable inside the shared square scan card.
export function initTranslationInputs(root = document) {
  root.querySelectorAll('[data-source-sequences]').forEach((card) => {
    const image = card.querySelector('img');
    const buttons = [...card.querySelectorAll('[data-sequence]')];
    buttons.forEach((button) => button.addEventListener('click', () => {
      image.src = button.dataset.src;
      image.alt = `Input ${button.textContent.trim()} MRI`;
      const sweep = card.querySelector('.tr-sweep');  // the moving pane follows, on the same slice
      if (sweep) {
        sweep.dataset.sweepPane = button.dataset.sequence;
        sweep.dispatchEvent(new CustomEvent('sweep-pane', { bubbles: true }));
      }
      buttons.forEach((other) => other.setAttribute('aria-pressed', String(other === button)));
    }));
  });
}
