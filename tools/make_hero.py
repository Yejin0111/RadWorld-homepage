"""Render uniformly framed hero sweeps from generated RadWorld volumes.

Seven generated volumes give the twelve tiles: head CT, chest CT and brain MRI in three planes
(two head CTs, two brain MRIs), abdomen CT in two and pelvis CT in one, so the grid shows more
anatomy than one plane of many cases. Each
sweep covers the region its tile names (the head of a head-and-neck CT, the lungs of a chest CT)
and runs through the middle of the volume in coronal and sagittal views. CT is shown over -1000 to
1000 HU and MRI over the model's whole intensity range (-1 to 1), without a window, except where a
tile sets its own range (the axial head, whose brain and skull would otherwise outshine the rest). Each
clip has one fixed field of view and preserves physical aspect ratio. Foreground occupancy is
normalized for display, not anatomical comparison. The scanner table is left black: pieces outside
the patient's outline that are thin or lie wholly behind the back. Anything inside the outline (the
vessels of the lungs, say) and anything beside the body (the arms) is kept.

The sources are the original outputs (HU for CT, the model's intensity scale for MRI), not the
8-bit copies of the page: whole-volume generations in ~/Desktop/radworld_server_outputs, and for the
head the CT RadWorld translated from MR for case 1HNA124 (the MR-to-CT example of the Translation
section and Extended Data Figure 5c), whose 1.25 mm pixels stay sharp where the generated
head-and-neck CTs (2.0 to 2.5 mm) look blocky at this size. Tiles are listed in grid order,
which keeps neighbouring tiles different at 4, 3 and 2 columns (phones show the first six).

Requires NumPy, SciPy, nibabel and Pillow. Writes assets/img/hero/*.webp and data/hero.json.
Usage: python3 tools/make_hero.py
"""
import json
from pathlib import Path

import nibabel as nib
import numpy as np
from PIL import Image
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
SERVER_OUT = Path.home() / "Desktop/radworld_server_outputs"
FIGURE_DATA = Path.home() / "Library/CloudStorage/Dropbox/应用/Overleaf/Gen3D/resources/codes/figure1/data/visualization/modality_transfer"
SIZE = 320
OCCUPANCY = 0.82
FRAMES = 40
CT_RANGE, MR_RANGE = (-1000, 1000), (-1, 1)  # tissue windows tried before: W400/L40 head and chest, W350/L40 abdomen and pelvis
VOLUMES = {  # name: (generated volume, displayed range: HU for CT, model units for MRI)
    "head_ct": (FIGURE_DATA / "1HNA124_ct.nii.gz", CT_RANGE),
    "chest_ct": (SERVER_OUT / "signoff/pretrain/case07.nii.gz", CT_RANGE),
    "abdomen_ct": (SERVER_OUT / "homepage_gen/seed_42/pretrain/case13.nii.gz", CT_RANGE),
    "pelvis_ct": (SERVER_OUT / "homepage_gen/seed_7/pretrain/case18.nii.gz", CT_RANGE),
    "brain_mr": (SERVER_OUT / "homepage_gen/seed_42/pretrain_mr/case07.nii.gz", MR_RANGE),
    "brain_mr2": (SERVER_OUT / "homepage_gen/seed_42/pretrain_mr/case03.nii.gz", MR_RANGE),  # skull-stripped
    "head_neck_ct": (SERVER_OUT / "signoff/pretrain/case01.nii.gz", CT_RANGE),
}
SAMPLES = [  # volume, plane, label, first and last slice (RAS, along the plane's axis)[, own range]
    ("head_ct", "axial", "Head CT", 72, 114, (-1000, 1300)),  # skull base to the upper brain
    ("brain_mr2", "coronal", "Brain MRI, coronal", 64, 143),
    ("abdomen_ct", "axial", "Abdomen CT", 56, 104),      # kidneys to the liver dome
    ("chest_ct", "coronal", "Chest CT, coronal", 85, 145),
    ("chest_ct", "sagittal", "Chest CT, sagittal", 87, 172),
    ("pelvis_ct", "axial", "Pelvis CT", 6, 44),           # femoral heads to the iliac crest
    ("head_ct", "sagittal", "Head CT, sagittal", 107, 148),
    ("brain_mr", "axial", "Brain MRI", 26, 93),
    ("abdomen_ct", "coronal", "Abdomen CT, coronal", 72, 144),
    ("brain_mr2", "sagittal", "Brain MRI, sagittal", 98, 158),
    ("chest_ct", "axial", "Chest CT", 58, 102),           # the lungs
    ("head_neck_ct", "coronal", "Head and neck CT, coronal", 96, 130),  # head and neck, not the occiput alone
]
AXIS = {"axial": 2, "coronal": 1, "sagittal": 0}


def load_volume(path):
    image = nib.as_closest_canonical(nib.load(str(path)))
    return np.asanyarray(image.dataobj).astype(np.float32), image.header.get_zooms()[:3]


def slice_image(volume, plane, index):
    image = np.take(volume, index, axis=AXIS[plane])
    return image[::-1, ::-1].T  # patient's right on the left, anterior or superior at the top


def body_component(mask):
    """The patient: the largest connected piece, so the bed and islands inside the lungs are left out."""
    labels, count = ndimage.label(mask)
    if count < 2:
        return mask
    return labels == 1 + int(np.argmax(ndimage.sum(mask, labels, range(1, count + 1))))


def table(tissue, plane):
    """The scanner table: pieces outside the patient's outline that are thin or wholly behind the back."""
    patient = body_component(tissue)
    rows, cols = np.nonzero(patient)
    outline = np.zeros_like(patient)  # filled row by row and column by column, so the lungs are inside
    for r in np.unique(rows):
        span = cols[rows == r]; outline[r, span.min():span.max() + 1] = True
    across = np.zeros_like(patient)
    for c in np.unique(cols):
        span = rows[cols == c]; across[span.min():span.max() + 1, c] = True
    outline &= across
    labels, _ = ndimage.label(tissue & ~patient)
    hidden = np.zeros_like(tissue)
    for label, box in enumerate(ndimage.find_objects(labels), start=1):
        part = labels[box] == label
        if (part & outline[box]).any():
            continue
        thin = part.sum() / max(part.shape) <= 6  # a line is a few pixels thick however long or curved
        behind = box[0].start > rows.max() if plane == "axial" else box[1].start > cols.max() if plane == "sagittal" else False
        if thin or behind:
            hidden[box] |= part
    return ndimage.binary_dilation(hidden, iterations=1)


def render_clip(volume, zooms, plane, window, first, last):
    lo, hi = window
    tissue = volume > (-500 if lo < -1 else -0.85)  # the patient: CT in HU, MRI above its background
    indices = np.linspace(first, last, FRAMES).round().astype(int)
    sx, sy = {"axial": (zooms[0], zooms[1]), "coronal": (zooms[0], zooms[2]), "sagittal": (zooms[1], zooms[2])}[plane]
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
    grey = lambda image: (np.clip((image - lo) / (hi - lo), 0, 1) * 255).astype(np.uint8)  # noqa: E731
    frames = []
    for index in indices:
        image = grey(slice_image(volume, plane, index))
        if lo < -1:  # CT: leave the table out
            image[table(slice_image(tissue, plane, index), plane)] = 0
        frames.append(Image.fromarray(image).convert("RGB").crop(crop).resize((SIZE, SIZE), Image.Resampling.LANCZOS))
    order = list(range(len(frames))) + list(range(len(frames) - 2, 0, -1))
    start = len(frames) // 2
    order = order[start:] + order[:start]
    return [frames[index] for index in order], frames[start]


def main():
    output = ROOT / "assets/img/hero"
    output.mkdir(parents=True, exist_ok=True)
    volumes = {name: load_volume(path) for name, (path, _) in VOLUMES.items()}
    manifest = []
    for key, plane, label, first, last, *own in SAMPLES:
        volume, zooms = volumes[key]
        window = own[0] if own else VOLUMES[key][1]
        frames, still = render_clip(volume, zooms, plane, window, first, last)
        name = f"{key}_{plane}"
        target, poster = output / f"{name}.webp", output / f"{name}_still.webp"
        frames[0].save(target, "WEBP", save_all=True, append_images=frames[1:], duration=90, loop=0, quality=72, method=4)
        still.save(poster, "WEBP", quality=85)
        manifest.append({"volume": key, "source": str(VOLUMES[key][0].relative_to(Path.home())), "plane": plane, "label": label, "slices": [first, last], "range": list(window),
                         "src": str(target.relative_to(ROOT)), "still": str(poster.relative_to(ROOT))})
        print(f"{target.relative_to(ROOT)}: {len(frames)} frames, {target.stat().st_size // 1024} KB")
    (ROOT / "data/hero.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
