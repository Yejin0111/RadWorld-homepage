// Small helpers around <dialog>: close on a backdrop click only when the press also started on
// the backdrop (so ending a drag outside the dialog does not close it), and a fallback for
// browsers without showModal (Safari before 15.4).

const native = typeof HTMLDialogElement === 'function' && 'showModal' in HTMLDialogElement.prototype;

export const isOpen = (dlg) => dlg.hasAttribute('open');

function escClose(e) {
  if (e.key !== 'Escape') return;
  const dlg = document.querySelector('dialog.no-modal[open]');
  if (dlg) closeDialog(dlg);
}

export function openDialog(dlg) {
  if (isOpen(dlg)) return;
  if (native) { dlg.showModal(); return; }
  dlg.setAttribute('open', '');
  dlg.classList.add('no-modal');
  document.addEventListener('keydown', escClose);
}

export function closeDialog(dlg) {
  if (!isOpen(dlg)) return;
  if (native) { dlg.close(); return; }
  dlg.removeAttribute('open');
  dlg.classList.remove('no-modal');
  document.removeEventListener('keydown', escClose);
  dlg.dispatchEvent(new Event('close'));
}

/** Wire the close button and backdrop clicks. `onClose` runs whenever the dialog closes. */
export function bindDialog(dlg, onClose) {
  let pressOnBackdrop = false;
  dlg.addEventListener('pointerdown', (e) => { pressOnBackdrop = e.target === dlg; });
  dlg.addEventListener('click', (e) => {
    if (e.target === dlg && pressOnBackdrop) closeDialog(dlg);
    pressOnBackdrop = false;
  });
  const btn = dlg.querySelector('[data-role="close"]');
  if (btn) btn.addEventListener('click', () => closeDialog(dlg));
  if (onClose) dlg.addEventListener('close', onClose);
}
