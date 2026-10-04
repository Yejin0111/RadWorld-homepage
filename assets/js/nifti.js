// Minimal NIfTI-1 loader for the uint8 volumes written by tools/prepare_assets.py.
// Handles .nii.gz whether or not the server already removed the gzip layer.

const cache = new Map(); // url -> Promise<volume>
const CACHE_MAX = 14;
const inflight = new Map(); // url -> { got, total, listeners } while downloading

let fflatePromise = null;
function loadFflate() {
  if (!fflatePromise) {
    fflatePromise = new Promise((resolve, reject) => {
      const s = document.createElement('script');
      s.src = new URL('../vendor/fflate/fflate.min.js', import.meta.url).href;
      s.onload = () => resolve(window.fflate);
      s.onerror = () => reject(new Error('Could not load the decompression fallback'));
      document.head.appendChild(s);
    });
    fflatePromise.catch(() => { fflatePromise = null; });
  }
  return fflatePromise;
}

async function gunzip(bytes) {
  if (typeof DecompressionStream === 'function') {
    const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'));
    return new Uint8Array(await new Response(stream).arrayBuffer());
  }
  const fflate = await loadFflate();
  return fflate.gunzipSync(bytes);
}

async function fetchBytes(url, onProgress) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status} for ${url}`);
  const total = Number(res.headers.get('Content-Length')) || 0;
  if (!res.body || !onProgress) return new Uint8Array(await res.arrayBuffer());
  const reader = res.body.getReader();
  const chunks = [];
  let got = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    chunks.push(value);
    got += value.length;
    onProgress(got, total);
  }
  const out = new Uint8Array(got);
  let off = 0;
  for (const c of chunks) { out.set(c, off); off += c.length; }
  return out;
}

export function parseNifti(bytes) {
  const dv = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  let le = true;
  if (dv.getInt32(0, true) !== 348) {
    if (dv.getInt32(0, false) !== 348) throw new Error('Not a NIfTI-1 file');
    le = false;
  }
  const dims = [dv.getInt16(42, le), dv.getInt16(44, le), dv.getInt16(46, le)];
  const datatype = dv.getInt16(70, le);
  const spacing = [dv.getFloat32(80, le), dv.getFloat32(84, le), dv.getFloat32(88, le)];
  const offset = Math.round(dv.getFloat32(108, le)) || 352;
  if (datatype !== 2) throw new Error(`Expected uint8 data, got datatype ${datatype}`);
  const n = dims[0] * dims[1] * dims[2];
  // `bytes` is the whole uncompressed file, reused by the 3D view
  return { dims, spacing, data: bytes.subarray(offset, offset + n), bytes };
}

/** Load a volume once; later calls share the same promise and the same progress reports. */
export function loadVolume(url, onProgress) {
  if (cache.has(url)) {
    const p = cache.get(url);
    cache.delete(url);
    cache.set(url, p); // refresh LRU position
    const st = inflight.get(url);
    if (st && onProgress) { st.listeners.add(onProgress); onProgress(st.got, st.total); }
    return p;
  }
  const st = { got: 0, total: 0, listeners: new Set(onProgress ? [onProgress] : []) };
  inflight.set(url, st);
  const report = (got, total) => { st.got = got; st.total = total; st.listeners.forEach((f) => f(got, total)); };
  const p = (async () => {
    let bytes = await fetchBytes(url, report);
    if (bytes[0] === 0x1f && bytes[1] === 0x8b) bytes = await gunzip(bytes);
    return parseNifti(bytes);
  })();
  p.then(() => inflight.delete(url), () => { inflight.delete(url); cache.delete(url); });
  cache.set(url, p);
  while (cache.size > CACHE_MAX) cache.delete(cache.keys().next().value);
  return p;
}

/** 256-entry table from raw uint8 to the encoded physical value (HU for CT). */
export function decodeTable(enc) {
  const t = new Float32Array(256);
  if (!enc || enc.type === 'label' || enc.type === 'labelmap') {
    for (let i = 0; i < 256; i++) t[i] = i;
  } else if (enc.type === 'piecewise') {
    const raw = enc.raw, val = enc.val;
    for (let i = 0; i < 256; i++) {
      let s = 0;
      while (s < raw.length - 2 && i > raw[s + 1]) s++;
      const f = (i - raw[s]) / (raw[s + 1] - raw[s]);
      t[i] = val[s] + Math.min(1, Math.max(0, f)) * (val[s + 1] - val[s]);
    }
  } else {
    for (let i = 0; i < 256; i++) t[i] = enc.lo + (i / 255) * (enc.hi - enc.lo);
  }
  return t;
}

/** Grey lookup (Uint8Array(256)) for a window [lo, hi] in physical units; null window = full range. */
export function greyTable(decoded, lo, hi) {
  if (lo == null || hi == null) { lo = decoded[0]; hi = decoded[255]; }
  const g = new Uint8Array(256);
  const w = hi - lo || 1;
  for (let i = 0; i < 256; i++) {
    const v = ((decoded[i] - lo) / w) * 255;
    g[i] = v < 0 ? 0 : v > 255 ? 255 : v;
  }
  return g;
}

/** Raw value whose decoded value is closest to x (used to set 3D thresholds). */
export function rawFor(decoded, x) {
  let best = 0, bd = Infinity;
  for (let i = 0; i < 256; i++) {
    const d = Math.abs(decoded[i] - x);
    if (d < bd) { bd = d; best = i; }
  }
  return best;
}
