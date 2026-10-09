"""Scrollable views of the generated volumes for the Generation slides, and data/showcase.json.

Each view (axial, coronal, sagittal) is one sprite sheet: a grid of slices through the body, so the
page can show one slice at a time and step through them as the pointer moves across the image. The
view opens on a chosen slice: the case's representative slice, or for the report cases the slice of
Figure 2e, with the paper's arrows on it. Organ-mask cases also get the mask blended onto the CT
(shown while the pointer is on the image) and the mask alone for the input card, slice for slice.
Slices near the ends of the body, where the volume or the mask thins out, are left out. CT is shown over
the whole range of its encoding (-1000 to 1000 HU), without a window, and MRI over its own range. Only the
report cases keep the window of Figure 2e, which their findings need (fluid next to the heart, for one).

Usage: python3 tools/make_views.py
Sources: the gallery volumes in assets/vol (whole-volume and organ-mask cases), and the report-guided
volumes of Figure 2e (~/Desktop/生成工作材料/visualization), with the arrows read from figure2.pdf.
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

# The four report-guided cases of Figure 2e, in its order: volume, slice (ITK-SNAP, 1-based, file
# order, as in extrace_vis_slices.py), the figure's image in figure2.pdf, tab label and the report's
# sentence with the main finding, in our own words (the CT-RATE report text itself may not be
# redistributed). The page shows that sentence between ellipses, as an excerpt of the report.
FIG2E_WINDOW = (-200, 200)  # the window of the figure
FULL_HU = (-1000, 1000)     # every other CT: the whole range of the encoding
MASK_AXIAL = {"m2i_a": 96}   # organ-mask cases: open on a slice through liver, kidneys and spleen
REPORT_CASES = [
    ("rep_calcification", "第一批/Arterial wall calcification/valid_100_a_1.nii.gz", 35, 15, "Calcified plaques",
     "There are calcified atherosclerotic plaques in the walls of the thoracic aorta and the coronary arteries."),
    ("rep_hernia", "第一批/Hiatal hernia/valid_1007_a_1.nii.gz", 90, 21, "Hiatal hernia",
     "There is a small sliding hiatal hernia at the lower end of the esophagus."),
    ("rep_pericardial", "第二批/Pericardial effusion/valid_1014_a_1.nii.gz", 67, 16, "Pericardial effusion",
     "There is a mild pericardial effusion, up to 12 mm thick."),
    ("rep_heart", "第一批/Cardiomegaly/valid_1002_a_1.nii.gz", 67, 22, "Enlarged heart",
     "The heart is markedly enlarged."),
]


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


def square(img):
    if img.height > PX:
        img = img.resize((int(img.width * PX / img.height), PX), Image.BICUBIC)
    canvas = Image.new("RGB", (PX, PX), (0, 0, 0))
    canvas.paste(img, ((PX - img.width) // 2, (PX - img.height) // 2))
    return canvas


def sprite(frames, path):
    rows = math.ceil(len(frames) / COLS)
    sheet = Image.new("RGB", (COLS * PX, rows * PX), (0, 0, 0))
    for i, f in enumerate(frames):
        sheet.paste(f, ((i % COLS) * PX, (i // COLS) * PX))
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path, "WEBP", quality=80, method=6)
    return {"src": pa.rel(path), "n": len(frames), "cols": COLS, "rows": rows}


def blend(ct_img, mask_img, body_color):
    """CT with the organ labels blended on at half strength (background and whole-body label left out)."""
    a = np.asarray(ct_img).astype(float)
    m = np.asarray(mask_img.convert("RGB")).astype(float)
    organ = ~(np.all(m == 0, axis=-1) | np.all(m == np.array(body_color, float), axis=-1))
    a[organ] = 0.5 * a[organ] + 0.5 * m[organ]
    return Image.fromarray(a.astype(np.uint8))


def build_case(cid, raw, enc, window, zooms, defaults, present, mask=None):
    """Sprites of the three views (and of the mask) for one volume. defaults: slice per plane."""
    views = {}
    for plane in PLANES:
        ax = AXIS[plane]
        lo, hi = view_range(present, ax)
        ks, start = frames_for(lo, hi, defaults[plane])
        cross = list(defaults["cross"])
        frames, overlays, masks = [], [], []
        for k in ks:
            c = cross.copy()
            c[ax] = k
            img = square(pa.render(raw, enc, window, plane, c, zooms, width=PX))
            frames.append(img)
            if mask is not None:
                m = square(pa.render_labels(mask["vol"], mask["colors"], plane, c, mask["zooms"], width=PX))
                overlays.append(blend(img, m, mask["body_color"]))
                masks.append(m)
        v = {"sprite": sprite(frames, OUT / f"{cid}_{plane}.webp"), "start": start}
        if mask is not None:
            v["overlay"] = sprite(overlays, OUT / f"{cid}_{plane}_mask.webp")
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


def main():
    gallery = json.loads((ROOT / "data/gallery.json").read_text())
    OUT.mkdir(parents=True, exist_ok=True)
    show = {"generation": [], "report": [], "mask": []}

    for case in gallery["groups"]["generation"]["cases"]:
        pane = case["panes"][0]
        v = gallery["volumes"][pane["vol"]]
        raw = np.asanyarray(nib.load(str(ROOT / v["url"])).dataobj)
        win = gallery["windows"]["auto"]
        window = FULL_HU if v["encoding"]["type"] == "piecewise" else (win["lo"], win["hi"])  # CT in HU, MRI over its range
        cross = case["cross"]
        views = build_case(case["id"], raw, v["encoding"], window, v["spacing"],
                           {"axial": cross[2], "coronal": cross[1], "sagittal": cross[0], "cross": cross}, body(raw, v["encoding"]))
        show["generation"].append({"id": case["id"], "label": case["label"], "input": {"kind": "request", "tags": request_tags(case["id"])}, "views": views})

    arrows = figure2e_arrows()
    enc = pa.encoding_ct()
    for cid, rel_path, slice_id, xref, label, finding in REPORT_CASES:
        data, zooms, idx = pa.canonical(VIS / rel_path)
        raw = pa.enc_ct(data)
        k = idx([0, 0, slice_id - 1])[2]
        cross = [raw.shape[0] // 2, raw.shape[1] // 2, k]
        page_img = pa.render(raw, enc, FIG2E_WINDOW, "axial", cross, zooms, width=256)
        fig_arrows, fig_img = arrows[xref]
        name, err = match_orientation(fig_img, page_img)
        if err > 3:
            raise SystemExit(f"{cid}: the page slice does not match Figure 2e (difference {err:.1f})")
        to_page = TRANSFORMS[name][1]
        page_arrows = [[*to_page(*tail), *to_page(*tip)] for tail, tip in fig_arrows]
        # coronal and sagittal open through the arrow tips (their middle), so the finding is in all three views
        tx = sum(a[2] for a in page_arrows) / len(page_arrows)
        ty = sum(a[3] for a in page_arrows) / len(page_arrows)
        nx, ny, nz = raw.shape
        cross = [int(round(nx - 1 - tx * (nx - 1))), int(round(ny - 1 - ty * (ny - 1))), k]  # screen to voxel, axial view
        views = build_case(cid, raw, enc, FIG2E_WINDOW, zooms, {"axial": k, "coronal": cross[1], "sagittal": cross[0], "cross": cross}, body(raw, enc))
        views["axial"]["arrows"] = [[round(c, 4) for c in a] for a in page_arrows]
        print(f"{cid}: Figure 2e orientation '{name}' (difference {err:.2f}), {len(page_arrows)} arrow(s)")
        show["report"].append({"id": cid, "label": label, "input": {"kind": "report", "text": finding}, "views": views})

    for case in gallery["groups"]["mask"]["cases"]:
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
        show["mask"].append({"id": case["id"], "label": case["label"], "input": {"kind": "mask"}, "views": views})

    (ROOT / "data/showcase.json").write_text(json.dumps(show, ensure_ascii=False, indent=1))
    print("data/showcase.json:", {g: len(c) for g, c in show.items()})


if __name__ == "__main__":
    main()
