"""Scrollable views of the generated volumes for the Generation slides, and data/showcase.json.

Each view (axial, coronal, sagittal) is one sprite sheet: a grid of slices through the body, so the
page can show one slice at a time and step through them. The view opens on a chosen slice: the
case's representative slice, a slice through the report's finding, or for the Figure 2e case the
figure's slice, with the paper's arrows on it. Mask cases also get the mask blended onto the CT
(shown on request), the mask alone for the input card, slice for slice, and the condition as the
model receives it (body and organ labels, no CT) in all three views, for the overview figure. The
tumor case is the liver example of Figure 2f.
Slices near the ends of the body, where the volume or the mask thins out, are left out. Whole-volume
and organ-mask CT is shown over the whole range of its encoding (-1000 to 1000 HU), MRI over its own
range. Report cases each set their window (REPORT_CASES), the tumor case uses the liver window.

Usage: python3 tools/make_views.py
Sources: the gallery volumes in assets/vol (whole-volume and organ-mask cases), the report-guided
volumes of the Figure 2e pool (~/Desktop/生成工作材料/visualization), with the arrows read from
figure2.pdf, and the Figure 2f volumes (~/Desktop/生成工作材料/m2i_tumor_visualization).
"""
import io
import json
import math
import sys
from pathlib import Path

import fitz  # PyMuPDF
import nibabel as nib
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prepare_assets as pa  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets/img/views"
OV = Path.home() / "Library/CloudStorage/Dropbox/应用/Overleaf/Gen3D"
VIS = Path.home() / "Desktop/生成工作材料/visualization"
PX = 320            # slice size in the sprite; shown at about 260 px
N = 36              # slices per view
COLS = 6            # sprite grid: 6 x 6
MARGIN = 0.12       # share of the body extent left out at each end
PLANES = ("axial", "coronal", "sagittal")
AXIS = {"axial": 2, "coronal": 1, "sagittal": 0}

# Whole-volume requests as in the code release (examples/pretrain*.json): case -> (file, case in it)
RELEASE_EXAMPLES = Path.home() / "Desktop/radworld_server_outputs/release_outputs/examples"
REQUESTS = {"pretrain_ct": ("pretrain.json", "case07"), "gen_abdomen": ("pretrain.json", "case13"),
            "gen_hn": ("pretrain.json", "case01"), "gen_pelvis": ("pretrain.json", "case18"),
            "pretrain_mr": ("pretrain_mr.json", "case07")}
REGIONS = {36: "Head and neck", 37: "Chest", 38: "Abdomen", 39: "Pelvis"}  # body regions of ANATOMY_DICT
MODALITY = {"CT": "CT", "T1ce MRI": "T1CE MRI"}

# Report-guided cases (CT-RATE prompts, from the Figure 2e pool). Each: id, volume, tab label (the
# Figure 3a name of the finding), the report's sentence with that finding in our own words (the
# CT-RATE text may not be redistributed; the page shows it between ellipses, as an excerpt), the
# window, and where the views open: either the Figure 2e slice and image in figure2.pdf (slice in
# ITK-SNAP order, 1-based, as in extrace_vis_slices.py; coronal and sagittal then go through the
# figure's arrow tips), or canonical (sagittal, coronal, axial) indices through the finding.
FIG2E_WINDOW = (-200, 200)  # the window of the figure
FULL_HU = (-1000, 1000)     # the whole range of the encoding
MEDIASTINUM = (-160, 240)
LUNG_FINDINGS = (-1100, 300)  # W1400/L-400: the lung findings show, the background stays black
REPORT_CASES = [
    {"id": "rep_nodule", "path": "第二批/Lung nodule/valid_1004_a_1.nii.gz", "label": "Lung nodule", "window": LUNG_FINDINGS,
     "finding": "There are multiple nodules, about 5 mm across, in both lungs.", "at": (80, 128, 52)},
    {"id": "rep_pericardial", "path": "第二批/Pericardial effusion/valid_1014_a_1.nii.gz", "label": "Pericardial effusion", "window": MEDIASTINUM,
     "finding": "There is a mild pericardial effusion, up to 12 mm thick.", "figure": (67, 16)},
    {"id": "rep_fibrotic", "path": "第二批/Pulmonary fibrotic sequela/valid_1008_a_1.nii.gz", "label": "Fibrotic sequela", "window": LUNG_FINDINGS,
     "finding": "There are linear fibroatelectatic sequelae in the lingula of the left lung and reticulonodular sequelae at both lung apices.",
     "at": (73, 122, 60)},
    {"id": "rep_calcification", "path": "第一批/Arterial wall calcification/valid_101_a_1.nii.gz", "label": "Calcification", "window": MEDIASTINUM,
     "finding": "There are calcified atherosclerotic changes in the walls of the aorta and the coronary arteries.", "at": (134, 192, 72)},
]
MASK_AXIAL = {"m2i_a": 96}   # organ-mask case: open on a slice through liver, kidneys and spleen
MASK_LABELS = {"m2i_a": "Abdomen and pelvis"}  # the organ-mask case shown (the overview's, too)
LABEL_BODY = [104, 108, 122]  # the body label in the condition views, light enough to read on a dark page
# Tumor mask to CT: the liver example of Figure 2f (WORD case 0016). As in the figure, the CT is the
# normal CT with the voxels RadWorld generated inside the tumor mask, in the authors' liver window.
TUMOR = Path.home() / "Desktop/生成工作材料/m2i_tumor_visualization"
TUMOR_CASE = {"id": "m2t_liver", "label": "Liver tumor", "case": "word_0016",
              "gen": "epoch_1570_step_100000.pth_cfg_4_seed_1995/gen_liver_image", "window": (-50, 200)}
TUMOR_MARGIN_MM = 45  # the views sweep the region around the tumor, so that it shows on many slices
# Whole-volume cases: tab labels follow the requested regions (the request tags)
GEN_LABELS = {"pretrain_ct": "Head and neck to abdomen CT", "gen_hn": "Head and neck to chest CT",
              "gen_abdomen": "Chest to pelvis CT", "pretrain_mr": "Brain MRI (T1CE)"}
GEN_LEFT_OUT = {"gen_pelvis"}  # requested chest to pelvis, but the generated volume stops at the kidneys


def view_range(present, ax):
    """Slices along an axis where `present` (a boolean volume) has content, trimmed at both ends."""
    counts = present.sum(axis=tuple(a for a in range(3) if a != ax))
    idx = np.where(counts > 0.02 * counts.max())[0]
    lo, hi = int(idx.min()), int(idx.max())
    span = hi - lo
    return lo + MARGIN * span, hi - MARGIN * span


def frames_for(lo, hi, default):
    """N slices from lo to hi, one of them exactly the default slice. Returns the slices and its place."""
    ks = sorted(set(np.linspace(lo, hi, N).round().astype(int).tolist()))
    near = min(range(len(ks)), key=lambda i: abs(ks[i] - default))
    ks[near] = int(default)
    ks = sorted(set(ks))
    return ks, ks.index(int(default))


def square(img, resample=Image.BICUBIC):
    if img.height > PX:
        img = img.resize((int(img.width * PX / img.height), PX), resample)
    canvas = Image.new("RGB", (PX, PX), (0, 0, 0))
    canvas.paste(img, ((PX - img.width) // 2, (PX - img.height) // 2))
    return canvas


def sprite(frames, path, lossless=False):
    rows = math.ceil(len(frames) / COLS)
    sheet = Image.new("RGB", (COLS * PX, rows * PX), (0, 0, 0))
    for i, f in enumerate(frames):
        sheet.paste(f, ((i % COLS) * PX, (i // COLS) * PX))
    path.parent.mkdir(parents=True, exist_ok=True)
    if lossless:  # flat label colours: exact, and smaller than lossy
        sheet.save(path, "WEBP", lossless=True, method=6)
    else:
        sheet.save(path, "WEBP", quality=80, method=6)
    return {"src": pa.rel(path), "n": len(frames), "cols": COLS, "rows": rows}


def blend(ct_img, mask_img, body_color):
    """CT with the organ labels blended on at half strength (background and whole-body label left out)."""
    a = np.asarray(ct_img).astype(float)
    m = np.asarray(mask_img.convert("RGB")).astype(float)
    organ = ~(np.all(m == 0, axis=-1) | np.all(m == np.array(body_color, float), axis=-1))
    a[organ] = 0.5 * a[organ] + 0.5 * m[organ]
    return Image.fromarray(a.astype(np.uint8))


def relabel(mask_img, body_color):
    """The mask alone with the body label in LABEL_BODY (labels are drawn without interpolation)."""
    a = np.asarray(mask_img.convert("RGB")).copy()
    a[np.all(a == np.array(body_color, np.uint8), axis=-1)] = LABEL_BODY
    return Image.fromarray(a)


def build_case(cid, raw, enc, window, zooms, defaults, present, mask=None):
    """Sprites of the three views (and of the mask) for one volume. defaults: slice per plane."""
    views = {}
    for plane in PLANES:
        ax = AXIS[plane]
        lo, hi = view_range(present, ax)
        ks, start = frames_for(lo, hi, defaults[plane])
        cross = list(defaults["cross"])
        frames, overlays, masks, labels = [], [], [], []
        for k in ks:
            c = cross.copy()
            c[ax] = k
            img = square(pa.render(raw, enc, window, plane, c, zooms, width=PX))
            frames.append(img)
            if mask is not None:
                m = square(pa.render_labels(mask["vol"], mask["colors"], plane, c, mask["zooms"], width=PX))
                overlays.append(blend(img, m, mask["body_color"]))
                masks.append(m)
                flat = square(pa.render_labels(mask["vol"], mask["colors"], plane, c, mask["zooms"], width=PX), Image.NEAREST)
                labels.append(relabel(flat, mask["body_color"]))  # no blended edges: exact label colours
        v = {"sprite": sprite(frames, OUT / f"{cid}_{plane}.webp"), "start": start}
        if mask is not None:
            v["overlay"] = sprite(overlays, OUT / f"{cid}_{plane}_mask.webp")
            v["label"] = sprite(labels, OUT / f"{cid}_{plane}_label.webp", lossless=True)
            if plane == "axial":
                v["mask"] = sprite(masks, OUT / f"{cid}_input_mask.webp")
        views[plane] = v
        print(f"views/{cid}_{plane}: {len(ks)} slices, opens at {ks[start]}")
    return views


def request_tags(case_id):
    file, name = REQUESTS[case_id]
    entry = next(e for e in json.loads((RELEASE_EXAMPLES / file).read_text()) if e["image_file"] == name)
    return [MODALITY.get(entry["modality"], entry["modality"])] + [REGIONS[i] for i in sorted(entry["category_ids"]) if i in REGIONS]


def body(raw, enc):
    vals = pa.decode(np.arange(256), enc)
    return vals[raw] > (-500 if enc["type"] == "piecewise" else vals[0] + 0.1 * (vals[-1] - vals[0]))


# ---------------------------------------------------------------- arrows of Figure 2e
def figure2e_arrows():
    """Arrows per panel image (xref), as (tail, tip) in fractions of the panel image."""
    doc = fitz.open(OV / "resources/figures/figure2.pdf")
    page = doc[0]
    yellow = lambda c: c is not None and c[0] > 0.9 and c[1] > 0.75 and c[2] < 0.35  # noqa: E731
    out = {}
    for xref in (15, 21, 16, 22):
        r = page.get_image_rects(xref)[0]
        shafts, heads = [], []
        for d in page.get_drawings():
            if not r.intersects(d["rect"]):
                continue
            pts = [(p.x, p.y) for it in d["items"] for p in it[1:] if hasattr(p, "x")]
            if yellow(d.get("color")) and not d.get("fill"):
                shafts.append(pts)
            elif yellow(d.get("fill")):
                heads.append(pts)
        arrows = []
        for s in shafts:  # the head whose centre is nearest to this shaft's end
            tail = s[0]
            head = min(heads, key=lambda h: math.dist(np.mean(h, 0), s[-1]))
            tip = max(head, key=lambda p: math.dist(p, tail))
            f = lambda p: ((p[0] - r.x0) / r.width, (p[1] - r.y0) / r.height)  # noqa: E731
            arrows.append((f(tail), f(tip)))
        pix = fitz.Pixmap(doc, xref)
        out[xref] = (arrows, np.asarray(Image.open(io.BytesIO(pix.tobytes("png"))).convert("L"), float))
    return out


TRANSFORMS = {  # name: function on a 2D array, and the same on a point in fractions
    "id": (lambda a: a, lambda x, y: (x, y)),
    "fliplr": (lambda a: a[:, ::-1], lambda x, y: (1 - x, y)),
    "flipud": (lambda a: a[::-1], lambda x, y: (x, 1 - y)),
    "rot180": (lambda a: a[::-1, ::-1], lambda x, y: (1 - x, 1 - y)),
    "T": (lambda a: a.T, lambda x, y: (y, x)),
    "T_fliplr": (lambda a: a.T[:, ::-1], lambda x, y: (1 - y, x)),
    "T_flipud": (lambda a: a.T[::-1], lambda x, y: (y, 1 - x)),
    "T_rot180": (lambda a: a.T[::-1, ::-1], lambda x, y: (1 - y, 1 - x)),
}


def match_orientation(fig_img, page_img):
    """The transform that turns the figure's image into the page's rendering of the same slice."""
    fig = np.asarray(Image.fromarray(fig_img.astype(np.uint8)).resize((128, 128)), float)
    page = np.asarray(page_img.convert("L").resize((128, 128)), float)
    scores = {n: np.abs(t(fig) - page).mean() for n, (t, _) in TRANSFORMS.items()}
    best = min(scores, key=scores.get)
    return best, scores[best]


def tumor_case():
    """Figure 2f's liver example: the normal CT with the generated tumor inside the mask, and the mask."""
    tc = TUMOR_CASE
    real, zooms, _ = pa.canonical(TUMOR / f"real_images/{tc['case']}.nii.gz")
    gen, _, _ = pa.canonical(TUMOR / tc["gen"] / f"{tc['case']}.nii.gz")
    mask = pa.canonical(TUMOR / f"liver_masks/{tc['case']}.nii.gz")[0] > 0
    raw = pa.enc_ct(np.where(mask, gen, np.clip(real, -1000, 1000)))
    enc = pa.encoding_ct()
    k = int(np.argmax(mask.sum(axis=(0, 1))))  # the slice where the tumor is largest
    xs, ys = np.nonzero(mask[:, :, k])
    cross = [int(np.median(xs)), int(np.median(ys)), k]
    # sweep the region around the tumor: the body, within TUMOR_MARGIN_MM of the mask in every direction
    reach = [int(round(TUMOR_MARGIN_MM / z)) for z in zooms]
    lo = [max(0, int(np.nonzero(mask.any(axis=tuple(a for a in range(3) if a != ax)))[0].min()) - reach[ax]) for ax in range(3)]
    hi = [int(np.nonzero(mask.any(axis=tuple(a for a in range(3) if a != ax)))[0].max()) + reach[ax] for ax in range(3)]
    present = body(raw, enc).copy()
    region = np.zeros_like(present)
    region[lo[0]:hi[0] + 1, lo[1]:hi[1] + 1, lo[2]:hi[2] + 1] = True
    present &= region
    labels = mask.astype(np.uint8)
    views = build_case(tc["id"], raw, enc, tc["window"], zooms, {"axial": cross[2], "coronal": cross[1], "sagittal": cross[0], "cross": cross},
                       present, mask={"vol": labels, "colors": [[0, 0, 0], [255, 0, 0]], "zooms": zooms, "body_color": [66, 68, 78]})
    return {"id": tc["id"], "label": tc["label"], "input": {"kind": "mask"}, "views": views}


def main():
    gallery = json.loads((ROOT / "data/gallery.json").read_text())
    OUT.mkdir(parents=True, exist_ok=True)
    show = {"generation": [], "report": [], "mask": []}

    for case in gallery["groups"]["generation"]["cases"]:
        if case["id"] in GEN_LEFT_OUT:
            continue
        pane = case["panes"][0]
        v = gallery["volumes"][pane["vol"]]
        raw = np.asanyarray(nib.load(str(ROOT / v["url"])).dataobj)
        win = gallery["windows"]["auto"]
        window = FULL_HU if v["encoding"]["type"] == "piecewise" else (win["lo"], win["hi"])  # CT in HU, MRI over its range
        cross = case["cross"]
        views = build_case(case["id"], raw, v["encoding"], window, v["spacing"],
                           {"axial": cross[2], "coronal": cross[1], "sagittal": cross[0], "cross": cross}, body(raw, v["encoding"]))
        show["generation"].append({"id": case["id"], "label": GEN_LABELS.get(case["id"], case["label"]), "input": {"kind": "request", "tags": request_tags(case["id"])}, "views": views})

    arrows = figure2e_arrows()
    enc = pa.encoding_ct()
    for rc in REPORT_CASES:
        cid = rc["id"]
        data, zooms, idx = pa.canonical(VIS / rc["path"])
        raw = pa.enc_ct(data)
        page_arrows = None
        if "figure" in rc:  # open on the Figure 2e slice, coronal and sagittal through the figure's arrow tips
            slice_id, xref = rc["figure"]
            k = idx([0, 0, slice_id - 1])[2]
            page_img = pa.render(raw, enc, FIG2E_WINDOW, "axial", [raw.shape[0] // 2, raw.shape[1] // 2, k], zooms, width=256)
            fig_arrows, fig_img = arrows[xref]
            name, err = match_orientation(fig_img, page_img)
            if err > 3:
                raise SystemExit(f"{cid}: the page slice does not match Figure 2e (difference {err:.1f})")
            to_page = TRANSFORMS[name][1]
            page_arrows = [[*to_page(*tail), *to_page(*tip)] for tail, tip in fig_arrows]
            tx = sum(a[2] for a in page_arrows) / len(page_arrows)
            ty = sum(a[3] for a in page_arrows) / len(page_arrows)
            nx, ny, nz = raw.shape
            cross = [int(round(nx - 1 - tx * (nx - 1))), int(round(ny - 1 - ty * (ny - 1))), k]  # screen to voxel, axial view
            print(f"{cid}: Figure 2e orientation '{name}' (difference {err:.2f}), {len(page_arrows)} arrow(s)")
        else:
            cross = list(rc["at"])
        views = build_case(cid, raw, enc, rc["window"], zooms, {"axial": cross[2], "coronal": cross[1], "sagittal": cross[0], "cross": cross}, body(raw, enc))
        if page_arrows:
            views["axial"]["arrows"] = [[round(c, 4) for c in a] for a in page_arrows]
        show["report"].append({"id": cid, "label": rc["label"], "input": {"kind": "report", "text": rc["finding"]}, "views": views})

    for case in gallery["groups"]["mask"]["cases"]:
        if case["id"] not in MASK_LABELS:
            continue
        ct = gallery["volumes"][case["panes"][1]["vol"]]
        mk = gallery["volumes"][case["panes"][0]["vol"]]
        raw = np.asanyarray(nib.load(str(ROOT / ct["url"])).dataobj)
        mvol = np.asanyarray(nib.load(str(ROOT / mk["url"])).dataobj)
        colors = mk["encoding"]["colors"]
        body_color = next((c for c in colors if c == [66, 68, 78]), [66, 68, 78])
        organs = np.isin(mvol, [i for i, c in enumerate(colors) if i and c != body_color])
        present = body(raw, ct["encoding"]) & organs.any(axis=(0, 1))[None, None, :]  # slices with CT and organs
        cross = list(case["cross"])
        cross[2] = MASK_AXIAL.get(case["id"], cross[2])
        views = build_case(case["id"], raw, ct["encoding"], FULL_HU, ct["spacing"],
                           {"axial": cross[2], "coronal": cross[1], "sagittal": cross[0], "cross": cross}, present,
                           mask={"vol": mvol, "colors": colors, "zooms": mk["spacing"], "body_color": body_color})
        show["mask"].append({"id": case["id"], "label": MASK_LABELS[case["id"]], "input": {"kind": "mask"}, "views": views})
    show["mask"].append(tumor_case())

    (ROOT / "data/showcase.json").write_text(json.dumps(show, ensure_ascii=False, indent=1))
    print("data/showcase.json:", {g: len(c) for g, c in show.items()})


if __name__ == "__main__":
    main()
