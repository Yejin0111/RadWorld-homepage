"""Images for the Translation slides (assets/img/translation/*.webp).

CBCT to CT, MR to CT and T1/T2/FLAIR to T1CE use the slices of the paper's Figure 4b and Extended
Data Figure 5 (resources/codes/figure4/data/modality_transfer_qualitative), the contrast-phase slide
the posters of the public Coltea case already on the page. The images of one slide share one square
crop around the body. The paper draws the Hounsfield-unit profile as a thin line in each method's
colour. It is detected there and drawn again thicker, in one colour, so it stays visible at page size.

Usage: python3 tools/make_translation.py
"""
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
QUAL = Path.home() / "Library/CloudStorage/Dropbox/应用/Overleaf/Gen3D/resources/codes/figure4/data/modality_transfer_qualitative"
OUT = ROOT / "assets/img/translation"
PX = 720
LINE = (255, 209, 102)  # profile line, the same on the generated and the real CT

SETS = {  # slide: [(name, source image, carries the profile line)]
    "cbct": [("input", QUAL / "cbct2ct/2ABC137/2ABC137_Ori_slice_z52_line.png", False),
             ("radworld", QUAL / "cbct2ct/2ABC137/2ABC137_Ours_slice_z52_line.png", True),
             ("real", QUAL / "cbct2ct/2ABC137/2ABC137_GT_slice_z52_line.png", True)],
    "mr2ct": [("input", QUAL / "mr2ct/1HNA124/1HNA124_Ori_slice_z80_line.png", False),
              ("radworld", QUAL / "mr2ct/1HNA124/1HNA124_Ours_slice_z80_line.png", True),
              ("real", QUAL / "mr2ct/1HNA124/1HNA124_GT_slice_z80_line.png", True)],
    "t1ce": [("t1", QUAL / "mr2mr_align/BraTS-GLI-02504-100/BraTS-GLI-02504-100_mr_t1_axial_z96.png", False),
             ("t2", QUAL / "mr2mr_align/BraTS-GLI-02504-100/BraTS-GLI-02504-100_mr_t2w_axial_z96.png", False),
             ("flair", QUAL / "mr2mr_align/BraTS-GLI-02504-100/BraTS-GLI-02504-100_mr_flair_axial_z96.png", False),
             ("radworld", QUAL / "mr2mr_align/BraTS-GLI-02504-100/BraTS-GLI-02504-100_Ours_axial_z96.png", False),
             ("real", QUAL / "mr2mr_align/BraTS-GLI-02504-100/BraTS-GLI-02504-100_GT_axial_z96.png", False)],
    "phase": [("input", ROOT / "assets/img/poster/extra/ct_phase_0_axial.webp", False),
              ("radworld", ROOT / "assets/img/poster/extra/ct_phase_1_axial.webp", False),
              ("real", ROOT / "assets/img/poster/extra/ct_phase_2_axial.webp", False)],
}


def line_ends(rgb):
    """End points of the coloured profile line (pixels whose channels differ, unlike the grey scan)."""
    a = rgb.astype(np.int16)
    ys, xs = np.where(a.max(-1) - a.min(-1) > 25)
    if len(xs) < 20:
        return None
    pts = np.stack([xs, ys], 1).astype(float)
    c = pts.mean(0)
    d = np.linalg.svd(pts - c)[2][0]           # direction of the line
    t = (pts - c) @ d
    return c + t.min() * d, c + t.max() * d


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for slide, items in SETS.items():
        imgs = {n: np.asarray(Image.open(p).convert("RGB")) for n, p, _ in items}
        grey = {n: a.mean(-1) for n, a in imgs.items()}  # the paper's thin line becomes grey, then is drawn over
        # one square crop for the slide: around the body in all images, with a small margin
        x0 = y0 = 10 ** 9
        x1 = y1 = 0
        for g in grey.values():
            ys, xs = np.where(g > 24)
            x0, x1, y0, y1 = min(x0, xs.min()), max(x1, xs.max()), min(y0, ys.min()), max(y1, ys.max())
        side = max(x1 - x0, y1 - y0) * 1.06
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        box = (cx - side / 2, cy - side / 2, cx + side / 2, cy + side / 2)
        scale = PX / side
        for name, path, has_line in items:
            ends = line_ends(imgs[name]) if has_line else None
            g = Image.fromarray(np.clip(grey[name], 0, 255).astype(np.uint8))
            canvas = Image.new("L", (int(round(side)), int(round(side))), 0)
            canvas.paste(g, (int(round(-box[0])), int(round(-box[1]))))
            im = canvas.resize((PX, PX), Image.LANCZOS).convert("RGB")
            if ends is not None:
                (ax, ay), (bx, by) = [((p[0] - box[0]) * scale, (p[1] - box[1]) * scale) for p in ends]
                d = ImageDraw.Draw(im)
                d.line([(ax, ay), (bx, by)], fill=LINE, width=4)
                for x, y in ((ax, ay), (bx, by)):
                    d.ellipse([x - 5, y - 5, x + 5, y + 5], fill=LINE)
            path_out = OUT / f"{slide}_{name}.webp"
            im.save(path_out, "WEBP", quality=86, method=6)
            print(f"{path_out.relative_to(ROOT)}: {path_out.stat().st_size // 1024} KB" + (" (profile line)" if ends is not None else ""))


if __name__ == "__main__":
    main()
