"""Images for the world-model figure under the title (assets/img/concept/*.webp).

The images are plain scans, without the arrows or zoomed views of the figures. Wherever the paper has
the example, it is the same scan: report to CT from Figure 2e and tumor mask to CT from the liver
example of Figure 2f (both as the images embedded in figure2.pdf, under the figure's arrows and zoomed
views), MR to CT from Figure 4b and the TACE case of Figure 5f. The paper has no image of a CT
generated from an organ mask, so that pair comes from the page's own organ-mask case. Each input and
output pair share one square crop.

Usage: python3 tools/make_concept.py
"""
import io
import json
import sys
from pathlib import Path

import fitz  # PyMuPDF
import nibabel as nib
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prepare_assets as pa  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets/img/concept"
OV = Path.home() / "Library/CloudStorage/Dropbox/应用/Overleaf/Gen3D/resources"
QUAL = OV / "codes/figure4/data/modality_transfer_qualitative"
PX = 360  # shown at up to 180 px, sharp on high-density screens


def figure_image(pdf, xref):
    """One image of a figure as it is embedded there, without the arrows drawn over it."""
    doc = fitz.open(OV / "figures" / pdf)
    pix = fitz.Pixmap(doc, xref)
    return Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")


def body_box(imgs, thr=24, margin=0.04):
    """One square box around the body in all images of a pair."""
    x0 = y0 = 10 ** 9
    x1 = y1 = 0
    for im in imgs:
        a = np.asarray(im.convert("L"))
        ys, xs = np.where(a > thr)
        x0, x1, y0, y1 = min(x0, xs.min()), max(x1, xs.max()), min(y0, ys.min()), max(y1, ys.max())
    side = max(x1 - x0, y1 - y0) * (1 + 2 * margin)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    return [cx - side / 2, cy - side / 2, cx + side / 2, cy + side / 2]


def crop(img, box):
    w, h = img.size
    canvas = Image.new("RGB", (int(box[2] - box[0]), int(box[3] - box[1])), (0, 0, 0))
    src = img.convert("RGB").crop([max(0, int(box[0])), max(0, int(box[1])), min(w, int(box[2])), min(h, int(box[3]))])
    canvas.paste(src, (max(0, -int(box[0])), max(0, -int(box[1]))))
    return canvas.resize((PX, PX), Image.LANCZOS)


def save(img, name):
    path = OUT / f"{name}.webp"
    img.save(path, "WEBP", quality=86, method=6)
    print(f"{path.relative_to(ROOT)}: {path.stat().st_size // 1024} KB")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    # report to CT: Figure 2e, pericardial effusion (third panel), the image without its arrows
    save(figure_image("figure2.pdf", 16).resize((PX, PX), Image.LANCZOS), "out_report")
    # tumor mask to CT: Figure 2f, liver example (its first pair): the normal CT with the tumor mask in
    # red, and the CT with the tumors RadWorld synthesized inside the mask
    normal, synthetic = figure_image("figure2.pdf", 23), figure_image("figure2.pdf", 24)
    box = body_box([normal, synthetic])
    save(crop(normal, box), "in_tumor")
    save(crop(synthetic, box), "out_tumor")
    # source modality to target modality: Figure 4b, MR to CT
    mr = Image.open(QUAL / "mr2ct/1HNA142/1HNA142_Ori_slice_z40_line.png").convert("RGB")
    ct = Image.open(QUAL / "mr2ct/1HNA142/1HNA142_Ours_slice_z40_line.png").convert("RGB")
    box = body_box([mr, ct])
    save(crop(mr, box), "in_source")
    save(crop(ct, box), "out_source")
    # organ mask to CT: the page's organ-mask case at a slice through liver, kidneys and spleen
    g = json.loads((ROOT / "data/gallery.json").read_text())
    ctv, mkv = g["volumes"]["m2i_a_1"], g["volumes"]["m2i_a_0"]
    raw = np.asanyarray(nib.load(str(ROOT / ctv["url"])).dataobj)
    mvol = np.asanyarray(nib.load(str(ROOT / mkv["url"])).dataobj)
    cross = [128, 128, 96]
    w = pa.WINDOWS["abdomen"]
    ct_img = pa.render(raw, ctv["encoding"], (w["lo"], w["hi"]), "axial", cross, ctv["spacing"], width=512)
    mk_img = pa.render_labels(mvol, mkv["encoding"]["colors"], "axial", cross, mkv["spacing"], width=512).convert("RGB")
    box = body_box([mk_img])
    save(crop(mk_img, box), "in_mask")
    save(crop(ct_img, box), "out_mask")
    # pre-treatment CT and the virtual post-treatment CT: Figure 5f, first patient
    pre = Image.open(ROOT / "assets/img/tace/p1_pre.webp").convert("RGB")
    virt = Image.open(ROOT / "assets/img/tace/p1_virtual.webp").convert("RGB")
    box = body_box([pre, virt])
    save(crop(pre, box), "in_pre")
    save(crop(virt, box), "out_tace")


if __name__ == "__main__":
    main()
