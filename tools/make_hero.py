"""Render uniformly framed hero sweeps from downloaded RadWorld volumes.

Requires NumPy and Pillow. Source volumes and scientific demo assets stay intact.
Each clip has one fixed field of view and preserves physical aspect ratio.
Foreground occupancy is normalized for display, not anatomical comparison.
"""
import gzip
import json
import struct
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SIZE = 320
OCCUPANCY = 0.82
SAMPLES = [
    ("gen_abdomen_0", "axial", "Abdomen and pelvis CT", -135, 215),
    ("pretrain_ct_0", "axial", "Chest CT", -160, 240),
    ("pretrain_mr_0", "axial", "Brain MRI", None, None),
    ("rep_effusions", "axial", "Report-guided chest CT", -160, 240),
    ("mr2ct_radworld", "axial", "CT translated from MRI", -450, 1050),
    ("gen_pelvis_0", "axial", "Pelvis CT", -135, 215),
    ("rep_covid", "axial", "Report-guided chest CT", -160, 240),
    ("rep_gallbladder", "axial", "Report-guided abdominal CT", -135, 215),
    ("gen_hn_0", "coronal", "Head and neck CT, coronal", -160, 240),
    ("pretrain_mr_0", "coronal", "Brain MRI, coronal", None, None),
    ("gen_abdomen_0", "coronal", "Abdomen and pelvis CT, coronal", -135, 215),
    ("mr2ct_radworld", "coronal", "CT translated from MRI, coronal", -450, 1050),
]


def load_volume(meta):
    data = gzip.decompress((ROOT / meta["url"]).read_bytes())
    endian = "<" if struct.unpack_from("<i", data)[0] == 348 else ">"
    assert struct.unpack_from(endian + "i", data)[0] == 348, "Expected NIfTI-1"
    assert struct.unpack_from(endian + "h", data, 70)[0] == 2, "Expected uint8"
    dims = struct.unpack_from(endian + "8h", data, 40)
    assert dims[0] == 3 and list(dims[1:4]) == meta["dims"]
    offset = int(struct.unpack_from(endian + "f", data, 108)[0])
    return np.frombuffer(data, dtype=np.uint8, count=int(np.prod(meta["dims"])), offset=offset).reshape(meta["dims"], order="F")


def slice_image(volume, plane, index):
    image = volume[:, :, index] if plane == "axial" else volume[:, index, :]
    return image[::-1, ::-1].T


def body_component(mask):
    """Exclude disconnected bed/edge pixels from display framing."""
    ys, xs = np.nonzero(mask)
    center = np.argmin((xs - mask.shape[1] / 2) ** 2 + (ys - mask.shape[0] / 2) ** 2)
    labels = Image.fromarray(mask.astype(np.uint8)).copy()
    ImageDraw.floodfill(labels, (int(xs[center]), int(ys[center])), 2)
    return np.array(labels) == 2


def render_clip(volume, meta, plane, lo, hi):
    encoding = meta["encoding"]
    if encoding["type"] == "piecewise":
        values = np.interp(np.arange(256), encoding["raw"], encoding["val"])
        tissue = values[volume] > -500
    else:
        values = np.linspace(encoding["lo"], encoding["hi"], 256)
        tissue = volume > 28
    lo = values[28] if lo is None else lo
    hi = values[-1] if hi is None else hi
    grey = np.clip((values - lo) / (hi - lo) * 255, 0, 255).astype(np.uint8)
    axis = 2 if plane == "axial" else 1
    counts = tissue.sum(axis=tuple(a for a in range(3) if a != axis))
    valid = np.flatnonzero(counts > counts.max() * 0.3)
    lower, upper = np.quantile(valid, [0.2, 0.8])
    indices = np.linspace(lower, upper, 40).round().astype(int)
    spacing = meta["spacing"]
    sx, sy = spacing[0], spacing[1] if plane == "axial" else spacing[2]
    bounds = []
    for index in indices:
        mask = body_component(slice_image(tissue, plane, index))
        ys, xs = np.nonzero(mask)
        # Ignore sparse peripheral pixels while retaining the anatomical field.
        x0, x1 = np.quantile(xs, [0.005, 0.995])
        y0, y1 = np.quantile(ys, [0.005, 0.995])
        bounds.append((x0 * sx, y0 * sy, (x1 + 1) * sx, (y1 + 1) * sy))
    x0, y0 = np.min(np.array(bounds)[:, :2], axis=0)
    x1, y1 = np.max(np.array(bounds)[:, 2:], axis=0)
    side = max(x1 - x0, y1 - y0) / OCCUPANCY
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    crop = ((cx - side / 2) / sx, (cy - side / 2) / sy,
            (cx + side / 2) / sx, (cy + side / 2) / sy)
    frames = [Image.fromarray(grey[slice_image(volume, plane, index)]).convert("RGB")
              .crop(crop).resize((SIZE, SIZE), Image.Resampling.LANCZOS) for index in indices]
    order = list(range(len(frames))) + list(range(len(frames) - 2, 0, -1))
    start = len(frames) // 2
    order = order[start:] + order[:start]
    return [frames[index] for index in order], frames[start]


def main():
    volumes = json.loads((ROOT / "data/gallery.json").read_text())["volumes"]
    output = ROOT / "assets/img/hero"
    output.mkdir(parents=True, exist_ok=True)
    manifest = []
    for key, plane, label, lo, hi in SAMPLES:
        meta = volumes[key]
        frames, still = render_clip(load_volume(meta), meta, plane, lo, hi)
        name = f"{key}_{plane}"
        target, poster = output / f"{name}.webp", output / f"{name}_still.webp"
        frames[0].save(target, "WEBP", save_all=True, append_images=frames[1:], duration=90, loop=0, quality=72, method=4)
        still.save(poster, "WEBP", quality=85)
        manifest.append({"volume": key, "plane": plane, "label": label,
                         "src": str(target.relative_to(ROOT)), "still": str(poster.relative_to(ROOT))})
        print(f"{target.relative_to(ROOT)}: {len(frames)} frames, {target.stat().st_size // 1024} KB")
    (ROOT / "data/hero.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
