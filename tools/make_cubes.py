"""Faces of the volume cubes in the 'Many tasks' overview (assets/img/concept/cube_*.webp).

Each cube shows three orthogonal slices of a real volume (top: axial, front: coronal, side:
sagittal), framed so the body takes up the same share of every face. An input and its output share
one crop, so the two cubes show the same field of view.
- Report to CT: the pericardial-effusion case of Figure 2e, in the figure's window: the figure's
  axial slice, the sagittal slice through the finding, and a coronal slice through the heart a little
  behind the finding (REPORT_CORONAL), where both lungs frame it. Through the finding itself the coronal
  slice is mostly chest wall and fills the whole face. This cube has a little more margin.
- MR to CT: code-release demo case06. The input MR is first put on the grid of the RadWorld output
  with tools/model_grid.py, which replays the release's preprocessing.
- TACE: patient 1 of Figure 5f, the pre-treatment CT and the virtual post-treatment CT generated
  with the patient's actual procedure (the run Figure 5f shows), axially at the figure's slice and
  coronally and sagittally through the new lipiodol there. These volumes are stored clipped to -140..260 HU and are shown over that range.
Everything outside the patient's filled outline (the scanner table, say) is left black. The
organ-mask cubes use the Generation slide's sprites (tools/make_views.py).

Usage: python3 tools/make_cubes.py
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_views as mv  # noqa: E402
import model_grid  # noqa: E402
import prepare_assets as pa  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets/img/concept"
HOME = Path.home()
SRV = HOME / "Desktop/radworld_server_outputs"
MR2CT_IN = HOME / "Downloads/demo_data/mr2ct/case06_source.nii.gz"
MR2CT_OUT = SRV / "signoff/mr2ct/case06.nii.gz"
MR2CT_ALIGNED = SRV / "aligned/mr2ct_case06_input.nii.gz"
TACE = HOME / "Downloads/tace_probe8_cases/10133214"
TACE_AXIAL = 81
TACE_VIRTUAL = SRV / "paper_figures/figure5/p1_10133214_virtual_zz_fold0_test_epoch1862.nii.gz"  # the run Figure 5f shows
PX = 320
OCCUPANCY = 0.8
REPORT_OCCUPANCY = 0.74
REPORT_CORONAL = 140
PLANES = ("axial", "coronal", "sagittal")
AXIS = {"axial": 2, "coronal": 1, "sagittal": 0}


def body_box(images, thr=12):
    """One box around the largest bright piece of every image (the body, not the table)."""
    box = None
    for im in images:
        a = np.asarray(im.convert("L")) > thr
        lab, n = ndimage.label(a)
        if n:
            a = lab == 1 + int(np.argmax(ndimage.sum(a, lab, range(1, n + 1))))
        ys, xs = np.nonzero(a)
        b = (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1)
        box = b if box is None else (min(box[0], b[0]), min(box[1], b[1]), max(box[2], b[2]), max(box[3], b[3]))
    return box


def patient_only(im, thr=12):
    """Black outside the largest bright piece, with its holes (the lungs) filled in."""
    a = np.asarray(im.convert("RGB")).copy()
    m = a.mean(axis=-1) > thr
    lab, n = ndimage.label(m)
    if n:
        m = lab == 1 + int(np.argmax(ndimage.sum(m, lab, range(1, n + 1))))
    m = ndimage.binary_dilation(ndimage.binary_fill_holes(m), iterations=2)
    a[~m] = 0
    return Image.fromarray(a)


def framed(im, box, occupancy=OCCUPANCY):
    side = max(box[2] - box[0], box[3] - box[1]) / occupancy
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    canvas = Image.new("RGB", (int(round(side)), int(round(side))), (0, 0, 0))
    canvas.paste(im.convert("RGB"), (int(round(side / 2 - cx)), int(round(side / 2 - cy))))
    return canvas.resize((PX, PX), Image.LANCZOS)


def cubes(name_volumes, cross, zooms, occupancy=OCCUPANCY, planes=None):
    """name_volumes: [(name, encoded volume, encoding, window)] on one grid. Writes 3 faces each.
    planes: optional slice per plane, overriding cross."""
    for plane in PLANES:
        c = list(cross)
        if planes and plane in planes:
            c[AXIS[plane]] = planes[plane]
        renders = [patient_only(pa.render(v, enc, w, plane, c, zooms, width=PX * 2)) for _, v, enc, w in name_volumes]
        box = body_box(renders)
        for (name, *_), im in zip(name_volumes, renders):
            path = OUT / f"cube_{name}_{plane}.webp"
            framed(im, box, occupancy).save(path, "WEBP", quality=88, method=6)
            print(f"{path.relative_to(ROOT)}  (slice {c[AXIS[plane]]})")


def report_case():
    rc = next(c for c in mv.REPORT_CASES if c["id"] == "rep_pericardial")
    rel_path, (slice_id, xref) = rc["path"], rc["figure"]
    data, zooms, idx = pa.canonical(mv.VIS / rel_path)
    raw = pa.enc_ct(data)
    k = idx([0, 0, slice_id - 1])[2]
    page_img = pa.render(raw, pa.encoding_ct(), mv.FIG2E_WINDOW, "axial", [raw.shape[0] // 2, raw.shape[1] // 2, k], zooms, width=256)
    fig_arrows, fig_img = mv.figure2e_arrows()[xref]
    name, err = mv.match_orientation(fig_img, page_img)
    to_page = mv.TRANSFORMS[name][1]
    tips = [to_page(*tip) for _, tip in fig_arrows]
    tx, ty = sum(t[0] for t in tips) / len(tips), sum(t[1] for t in tips) / len(tips)
    nx, ny, _ = raw.shape
    cross = [int(round(nx - 1 - tx * (nx - 1))), int(round(ny - 1 - ty * (ny - 1))), k]  # as in make_views.py
    cubes([("report_out", raw, pa.encoding_ct(), mv.FIG2E_WINDOW)], cross, zooms, REPORT_OCCUPANCY, {"coronal": REPORT_CORONAL})


def mr2ct_case():
    if not MR2CT_ALIGNED.exists():
        model_grid.to_model_grid(str(MR2CT_IN), "mr", str(MR2CT_ALIGNED), str(MR2CT_OUT))
    mr, zooms, _ = pa.canonical(MR2CT_ALIGNED)
    ct, _, _ = pa.canonical(MR2CT_OUT)
    lo, hi = np.percentile(mr[mr > mr.min()], [0.5, 99.5])
    body = ct > -500
    cross = [int(round(np.mean(np.nonzero(body.any(axis=tuple(a for a in range(3) if a != ax)))[0]))) for ax in range(3)]
    cubes([("mr2ct_in", pa.enc_lin(mr, lo, hi), pa.encoding_lin(lo, hi, "a.u."), (lo, hi)),
           ("mr2ct_out", pa.enc_ct(ct), pa.encoding_ct(), (-1000, 1000))], cross, zooms)
    both = (ct > -500) & (mr > lo + 0.05 * (hi - lo))
    print(f"MR and CT body overlap (Dice): {2 * both.sum() / ((ct > -500).sum() + (mr > lo + 0.05 * (hi - lo)).sum()):.3f}")


def tace_case():
    pre, zooms, _ = pa.canonical(TACE / f"{TACE.name}_REAL_pre.nii.gz")
    virt, _, _ = pa.canonical(TACE_VIRTUAL)
    new = (virt >= 250) & (pre < 200)  # bright in the virtual CT, not before: the lipiodol
    k = TACE_AXIAL  # the Figure 5f slice
    xs, ys, _ = np.nonzero(new[:, :, k - 3:k + 4]) if new[:, :, k].any() else (np.array([pre.shape[0] // 2]), np.array([pre.shape[1] // 2]), None)
    cross = [int(np.median(xs)), int(np.median(ys)), k]
    cubes([("tace_pre", pa.enc_ct(pre), pa.encoding_ct(), (-140, 260)),
           ("tace_virtual", pa.enc_ct(virt), pa.encoding_ct(), (-140, 260))], cross, zooms)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    report_case()
    mr2ct_case()
    tace_case()
