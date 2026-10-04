// 3D volume rendering in a dialog, using NiiVue (loaded on first use, about 2.3 MB).
// The volume bytes come from the 2D viewer's cache, so nothing is downloaded twice and the
// fflate fallback also covers browsers without DecompressionStream.

import { loadVolume, decodeTable, rawFor } from './nifti.js';
import { openDialog, bindDialog } from './dialog.js';

let libPromise = null;
let nvPromise = null;
let nv = null;
let current = null;
let request = 0; // increments on every open, so a slow earlier load cannot replace a newer one

function loadNiivue() {
  if (!libPromise) {
    libPromise = new Promise((resolve, reject) => {
      const s = document.createElement('script');
      s.src = new URL('../vendor/niivue/niivue.umd.js', import.meta.url).href;
      s.onload = () => (window.niivue ? resolve(window.niivue) : reject(new Error('NiiVue did not initialise')));
      s.onerror = () => reject(new Error('the 3D renderer could not be downloaded'));
      document.head.appendChild(s);
    });
    libPromise.catch(() => { libPromise = null; }); // allow a retry after a network failure
  }
  return libPromise;
}

const hasWebGL2 = () => {
  try { return !!document.createElement('canvas').getContext('webgl2'); } catch { return false; }
};

// Thresholds in physical units: voxels below `lo` are transparent.
const PRESETS = {
  HU: [
    { key: 'surface', label: 'Body surface', lo: -300, hi: 1000 },
    { key: 'soft', label: 'Soft tissue', lo: 20, hi: 400 },
    { key: 'bone', label: 'Bone', lo: 200, hi: 1000 },
  ],
};

function parts() {
  const dlg = document.getElementById('render3d');
  return {
    dlg,
    title: dlg.querySelector('[data-role="title"]'),
    canvas: dlg.querySelector('canvas'),
    status: dlg.querySelector('.render3d-status'),
    presets: dlg.querySelector('[data-role="presets"]'),
  };
}

function applyPreset(p) {
  if (!nv || !nv.volumes.length || !current || !p) return;
  const dec = decodeTable(current.encoding);
  const vol = nv.volumes[0];
  vol.cal_min = rawFor(dec, p.lo);
  vol.cal_max = rawFor(dec, p.hi);
  nv.updateGLVolume();
  parts().presets.querySelectorAll('button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.key === p.key)));
}

function getViewer(lib, canvas) {
  if (!nvPromise) {
    nvPromise = (async () => {
      const v = new lib.Niivue({ backColor: [0, 0, 0, 1], show3Dcrosshair: false, isOrientCube: false, loadingText: '' });
      await v.attachToCanvas(canvas);
      nv = v;
      return v;
    })();
    nvPromise.catch(() => { nvPromise = null; });
  }
  return nvPromise;
}

export async function open3D({ url, encoding, title, presets: only }) {
  const { dlg, title: titleEl, canvas, status, presets } = parts();
  const mine = ++request;
  current = { url, encoding };
  titleEl.textContent = title || '3D rendering';
  const list = (PRESETS[encoding.unit] || []).filter((p) => !only || only.includes(p.key));
  presets.innerHTML = list.map((p) => `<button type="button" class="chip" data-key="${p.key}">${p.label}</button>`).join('');
  presets.onclick = (e) => {
    const b = e.target.closest('button');
    if (b) applyPreset(list.find((p) => p.key === b.dataset.key));
  };
  status.hidden = false;
  status.textContent = 'Loading the 3D renderer…';
  openDialog(dlg);
  if (!hasWebGL2()) {
    status.textContent = 'This browser cannot show the 3D rendering because it does not support WebGL2.';
    return;
  }
  try {
    const [lib, vol] = await Promise.all([loadNiivue(), loadVolume(url)]);
    if (mine !== request) return;
    const viewer = await getViewer(lib, canvas);
    if (mine !== request) return;
    status.textContent = 'Preparing the rendering…';
    const name = `volume-${mine}.nii`; // tags this request's volume
    const b = vol.bytes;
    await viewer.loadFromArrayBuffer(b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength), name);
    const ours = viewer.volumes.filter((v) => v.name === name);
    const others = viewer.volumes.filter((v) => v.name !== name);
    if (mine !== request) { ours.forEach((v) => viewer.removeVolume(v)); return; } // superseded
    others.forEach((v) => viewer.removeVolume(v));
    viewer.setSliceType(viewer.sliceTypeRender);
    viewer.setRenderAzimuthElevation(125, 12);
    applyPreset(list[0]);
    status.hidden = true;
  } catch (err) {
    if (mine !== request) return;
    status.hidden = false;
    status.textContent = `The 3D rendering could not be shown (${err && err.message ? err.message : 'unknown error'}). Close and try again.`;
  }
}

export function initRender3D() {
  const { dlg } = parts();
  if (!dlg) return;
  bindDialog(dlg, () => { request += 1; }); // closing cancels a load that is still running
}
