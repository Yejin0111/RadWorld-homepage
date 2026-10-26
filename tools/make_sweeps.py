"""Synchronised axial sweeps for the Translation and Treatment slides (assets/img/sweeps/).

Every pane of a slide is a sprite sheet of the same axial slices of volumes on one grid, so the
page (assets/js/scan-sweeps.js) can step all panes of a slide together. A sweep covers the key region
only: SPAN slices on each side of the slide's key slice (the slice of the paper's figure), within
the body. The still of each pane (the img the page shows first, and with reduced motion) is the key
slice. There is no profile line: the panes show the scans alone. All panes of a slide share one
square crop around the body of the reference scan, and the scanner table is left black.

Sources (the paper's own volumes, ~/Desktop/radworld_server_outputs/paper_figures from gzy_cpu):
- CBCT to CT, 2ABC137, and MR to CT, 1HNA124: data/generation/figure4 (Figure 4b, ED Figure 5b, 5c)
- T1, T2 and FLAIR to T1CE, BraTS-GLI-02504-100: the aligned BraTS 2024 set of ED Figure 5a
- Non-contrast to arterial phase: the page's Coltea case CH24092019 (demo input, RadWorld output and
  the acquired phase aligned by tools/model_grid.py)
- TACE: patient 1 of Figure 5f (10133214) and a second patient of the same cohort and run (10218882):
  pre- and post-treatment CT, and the virtual post-treatment CT of the cross-validation run that
  Figure 5f shows (zz fold 0, epoch 1862, matched to the figure slice by slice), generated with each
  patient's actual procedure
TACE volumes are stored clipped to -140..260 HU and are shown over that range.

Usage: python3 tools/make_sweeps.py
"""
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_cubes as mc  # noqa: E402
import prepare_assets as pa  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets/img/sweeps"
HOME = Path.home()
SRV = HOME / "Desktop/radworld_server_outputs"
PF = SRV / "paper_figures"
F4 = PF / "figure4/data/generation/figure4"
BRATS = PF / "figure4/codes/nnUNet/data"
COHORT = HOME / "Downloads/tace_probe8_cases"
COHORT_IMG = COHORT / "data/train/tace_registration_fix_bg/image"
PX = 320
SPAN = 24          # slices on each side of the key slice
STEP = 2           # every second slice: about the pace of the Generation reel (2.5 slices per 120 ms)
OCCUPANCY = 0.86
CT, MED, TACE = (-1000, 1000), (-160, 240), (-140, 260)

# slide: (key slice in canonical RAS order, panes as (name, file, window; None = MR percentiles)).
# The last pane is the reference for the crop.
SLIDES = {
    "cbct": (75, [("input", F4 / "cbct2ct/cbct/2ABC137.nii.gz", CT), ("radworld", F4 / "cbct2ct/Ours/2ABC137.nii.gz", CT),
                  ("real", F4 / "cbct2ct/gt/2ABC137.nii.gz", CT)]),
    "mr2ct": (47, [("input", F4 / "mr2ct_resized/mr/1HNA124.nii.gz", None), ("radworld", F4 / "mr2ct_resized/Ours/1HNA124.nii.gz", CT),
                   ("real", F4 / "mr2ct_resized/gt/1HNA124.nii.gz", CT)]),
    "phase": (64, [("input", HOME / "Downloads/demo_data/ct_arterial/case02_source.nii.gz", CT),
                   ("radworld", SRV / "signoff/ct_arterial/case02.nii.gz", CT),
                   ("real", SRV / "aligned/ct_arterial_case02_reference.nii.gz", CT)]),
    "t1ce": (85, [("t1", BRATS / "BraTS2024_GLI_Additional_resample_Ori/imagesTr/BraTS-GLI-02504-100_0001.nii.gz", None),
                  ("t2", BRATS / "BraTS2024_GLI_Additional_resample_Ori/imagesTr/BraTS-GLI-02504-100_0003.nii.gz", None),
                  ("flair", BRATS / "BraTS2024_GLI_Additional_resample_Ori/imagesTr/BraTS-GLI-02504-100_0002.nii.gz", None),
                  ("radworld", BRATS / "BraTS2024_GLI_Additional_resample_Ours/imagesTr/BraTS-GLI-02504-100_0000.nii.gz", None),
                  ("real", BRATS / "BraTS2024_GLI_Additional_resample_Ori/imagesTr/BraTS-GLI-02504-100_0000.nii.gz", None)]),
    "tace_p1": (81, [("pre", COHORT / "10133214/10133214_REAL_pre.nii.gz", TACE),
                     ("virtual", PF / "figure5/p1_10133214_virtual_zz_fold0_test_epoch1862.nii.gz", TACE),
                     ("post", COHORT / "10133214/10133214_REAL_post.nii.gz", TACE)]),
    "tace_p2": (42, [("pre", COHORT / "10218882/10218882_REAL_pre.nii.gz", TACE),  # lipiodol in the lower right lobe
                     ("virtual", PF / "figure5/p2_10218882_virtual_zz_fold0_test_epoch1862.nii.gz", TACE),
                     ("post", COHORT / "10218882/10218882_REAL_post.nii.gz", TACE)]),
}


def load(path):
    v, zooms, _ = pa.canonical(path)
    v = v.astype(np.float32)
    if "mr2ct_resized/gt" in str(path):  # the preprocessed reference is padded with -1 HU at the sides: air
        v = np.where(np.all(v == -1, axis=1, keepdims=True) & (v == -1), -1000, v)
    return v, zooms


def encode(v, window):
    if window is None:  # MR: 0.5 to 99.5 percentiles of the foreground
        lo, hi = np.percentile(v[v > np.percentile(v, 30)], [0.5, 99.5])
        return pa.enc_lin(v, lo, hi), pa.encoding_lin(lo, hi, "a.u."), (lo, hi)
    return pa.enc_ct(v), pa.encoding_ct(), window


def largest(mask):
    lab, n = ndimage.label(mask)
    return mask if n < 2 else lab == 1 + int(np.argmax(ndimage.sum(mask, lab, range(1, n + 1))))


def sprite(frames, path):
    cols = math.ceil(math.sqrt(len(frames)))
    rows = math.ceil(len(frames) / cols)
    sheet = Image.new("RGB", (cols * PX, rows * PX), (0, 0, 0))
    for i, f in enumerate(frames):
        sheet.paste(f, ((i % cols) * PX, (i // cols) * PX))
    sheet.save(path, "WEBP", quality=80, method=6)
    return cols, rows


def build(slide, key, panes):
    vols = [(name, *load(path), window) for name, path, window in panes]
    assert len({v.shape for _, v, _, _ in vols}) == 1, f"{slide}: panes are not on one grid"
    ref, zooms = vols[-1][1], vols[-1][2]
    is_ct = vols[-1][3] is not None
    body = largest(ref > (-500 if is_ct else np.percentile(ref, 40)))
    zs = np.nonzero(body.any(axis=(0, 1)))[0]
    lo, hi = max(int(zs.min()), key - SPAN), min(int(zs.max()), key + SPAN)
    ks = sorted(set(range(key, lo - 1, -STEP)) | set(range(key, hi + 1, STEP)))  # through the key slice
    cross = [ref.shape[0] // 2, ref.shape[1] // 2, key]
    renders = []
    for name, v, _, window in vols:
        raw, enc, w = encode(v, window)
        ims = [pa.render(raw, enc, w, "axial", cross[:2] + [k], zooms, width=PX * 2) for k in ks]
        renders.append([mc.patient_only(im) if window is not None else im.convert("RGB") for im in ims])
    box = mc.body_box(renders[-1], thr=20)
    side = max(box[2] - box[0], box[3] - box[1]) / OCCUPANCY
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    crop = (cx - side / 2, cy - side / 2, cx + side / 2, cy + side / 2)
    entry = {"slices": [ks[0], ks[-1]], "key": key, "start": ks.index(key), "n": len(ks), "panes": {}}
    for (name, *_), ims in zip(vols, renders):
        frames = [im.crop(crop).resize((PX, PX), Image.LANCZOS) for im in ims]
        cols, rows = sprite(frames, OUT / f"{slide}_{name}.webp")
        frames[entry["start"]].save(OUT / f"{slide}_{name}_still.webp", "WEBP", quality=88, method=6)
        entry["panes"][name] = {"sprite": f"assets/img/sweeps/{slide}_{name}.webp", "still": f"assets/img/sweeps/{slide}_{name}_still.webp",
                                "cols": cols, "rows": rows}
    size = sum((OUT / f"{slide}_{n}.webp").stat().st_size for n in entry["panes"]) // 1024
    print(f"{slide}: slices {ks[0]}-{ks[-1]} (key {key}), {len(ks)} frames, {size} KB")
    return entry


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = {slide: build(slide, key, panes) for slide, (key, panes) in SLIDES.items()}
    (ROOT / "data/sweeps.json").write_text(json.dumps(manifest, indent=1) + "\n")
