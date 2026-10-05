"""Build the web assets for the RadWorld project page.

Reads RadWorld outputs and their inputs from local folders, and writes

  assets/vol/**.nii.gz        uint8 volumes in canonical RAS orientation
  assets/img/poster/**.webp   static pane images shown before a viewer loads
  assets/img/teaser/*.webp    animated axial sweeps for the teaser row
  data/gallery.json           viewer manifest (cases, panes, windows, encodings)
  data/turing.json            visual Turing test cases

Usage:
  python tools/prepare_assets.py            # everything
  python tools/prepare_assets.py --only report,turing

Volumes are stored as uint8 to keep downloads small. CT uses a piecewise-linear
encoding that spends most grey levels on soft tissue (see CT_RAW / CT_HU). The page
decodes raw values back to Hounsfield units with the same breakpoints, so window
presets are given in HU. Everything the page needs to decode a volume is written
to the manifest.

Edit the CONFIG section to add or swap cases. Server-only outputs (whole-volume
generation, mask-guided CT, CBCT-to-CT, T1CE completion, contrast phases) are
listed in PENDING and appear on the page as placeholders until added here.
"""
from __future__ import annotations

import argparse
import base64
import csv
import gzip
import json
from pathlib import Path

import nibabel as nib
import numpy as np
from nibabel import orientations as ornt_
from PIL import Image, ImageDraw

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
HOME = Path.home()
ROOT = Path(__file__).resolve().parents[1]
GEN = HOME / "Desktop/生成工作材料"
VIS = GEN / "visualization"                      # report-guided chest CT (Figure 2e)
TUM = GEN / "samples/best_tumor_cases"           # tumor synthesis and reader study
WORDV = GEN / "m2i_tumor_visualization"          # tumors placed in normal CT (Figure 2f)
FIG1 = HOME / "Library/CloudStorage/Dropbox/应用/Overleaf/Gen3D/resources/codes/figure1/data/visualization"

POSTER_W = 560          # poster width in px for one pane
TEASER_PX = 300         # teaser frame size (square canvas)

# CT encoding: raw uint8 <-> HU breakpoints (monotonic, piecewise linear).
# -1000..-200 HU in 40 steps (20 HU), -200..300 HU in 180 steps (2.8 HU), 300..1000 HU in 35 steps (20 HU).
CT_RAW = [0, 40, 220, 255]
CT_HU = [-1000, -200, 300, 1000]

WINDOWS = {
    "lung": {"label": "Lung", "lo": -1350, "hi": 150},
    "mediastinum": {"label": "Mediastinum", "lo": -160, "hi": 240},
    "abdomen": {"label": "Abdomen", "lo": -135, "hi": 215},
    "soft": {"label": "Soft tissue", "lo": -160, "hi": 240},
    "bone": {"label": "Bone", "lo": -450, "hi": 1050},
    "reader": {"label": "Reader window", "lo": -75, "hi": 175},
    "auto": {"label": "Auto", "lo": None, "hi": None},
}

# Report-guided chest CT. slice = ITK-SNAP axial slice number (1-based, file order),
# window as used for Figure 2e. The folders group cases by CT-RATE labels, which do not always
# match the report text used as the prompt, so each case lists a pattern that the prompt in
# selected_cases.csv must contain (checked at build time, the text itself is never published).
REPORT_CASES = [
    ("pleural_effusion", "Pleural effusion", "第一批/Pleural effusion/valid_1005_a_1.nii.gz", 92, "mediastinum", r"pleural effusion"),
    ("cardiomegaly", "Cardiomegaly", "第一批/Cardiomegaly/valid_1002_a_1.nii.gz", 67, "mediastinum", r"heart size|cardiomegaly"),
    ("consolidation", "Consolidation", "第一批/Consolidation/valid_102_a_1.nii.gz", 84, "lung", r"consolidation"),
    ("fibrotic_sequela", "Pulmonary fibrotic sequela", "第二批/Pulmonary fibrotic sequela/valid_1008_a_1.nii.gz", 71, "lung", r"fibro|sequela"),
    ("hiatal_hernia", "Hiatal hernia", "第一批/Hiatal hernia/valid_1007_a_1.nii.gz", 90, "mediastinum", r"hiatal hernia"),
    ("pericardial_effusion", "Pericardial effusion", "第二批/Pericardial effusion/valid_1019_a_1.nii.gz", 76, "mediastinum", r"pericardial effusion"),
]

# Tumor synthesis in normal CT with a supplied mask (Figure 2f). Requires the WORD licence check.
WORD_TUMOR_CASES = [
    ("word_liver", "Liver tumor in normal CT", "word_0016", "liver_masks", "gen_liver_image"),
    ("word_kidney", "Kidney tumor in normal CT", "word_0017", "kidney_left_masks", "gen_kidney_left_image"),
]

# Datasets whose terms allow showing derived volumes on a public non-commercial page
# (licence check of 2026-09-25, see DESIGN.md). Excluded: LiTS and 3D-IRCADb (NoDerivatives,
# so re-synthesized copies are not allowed), StructSeg2019 and MSWAL (no terms found),
# WORD (GPL-3.0 plus "not for ... second-development"), CT-RATE, Merlin and VinDr (no redistribution).
ALLOWED_DATASETS = {
    "KiTS2023", "HCC-TACE-Seg", "Colorectal_Liver_Metastases", "QIBA-VolCT-1B",
    "RIDER-LungCT-Seg", "QIN-LungCT-Seg", "RIDER_Lung_CT", "MSD_Lung", "MSD_Colon",
    "MSD_Pancreas", "FedBCa", "PANORAMA",
}
DATASET_LICENSE = {
    "KiTS2023": "CC BY-NC-SA 4.0", "HCC-TACE-Seg": "CC BY 4.0", "Colorectal_Liver_Metastases": "CC BY 4.0",
    "QIBA-VolCT-1B": "CC BY 4.0 and CC BY 3.0", "RIDER-LungCT-Seg": "CC BY 3.0", "QIN-LungCT-Seg": "CC BY 3.0",
    "RIDER_Lung_CT": "CC BY 4.0", "MSD_Lung": "CC BY-SA 4.0", "MSD_Colon": "CC BY-SA 4.0",
    "MSD_Pancreas": "CC BY-SA 4.0", "FedBCa": "CC BY 4.0", "PANORAMA": "CC BY-NC 4.0",
}
INCLUDE_WORD = False   # Figure 2f cases; keep off until the WORD authors confirm display is allowed
SHOW_TUMOR_PAIRS = False  # real versus re-synthesized tumors; off since the visual Turing test shows tumor synthesis
DATASET_LABEL = {
    "KiTS2023": "KiTS2023", "HCC-TACE-Seg": "HCC-TACE-Seg (TCIA)",
    "Colorectal_Liver_Metastases": "Colorectal-Liver-Metastases (TCIA)",
    "QIBA-VolCT-1B": "QIBA-VolCT-1B (TCIA)", "RIDER-LungCT-Seg": "RIDER-LungCT-Seg (TCIA)",
    "QIN-LungCT-Seg": "QIN-LungCT-Seg (TCIA)", "RIDER_Lung_CT": "RIDER Lung CT (TCIA)",
    "MSD_Lung": "MSD Lung", "MSD_Colon": "MSD Colon", "MSD_Pancreas": "MSD Pancreas",
    "FedBCa": "FedBCa", "PANORAMA": "PANORAMA",
}

TUMOR_TYPES = [  # folder, label, modality
    ("bladder_tumor", "Bladder cancer", "MRI (T2-weighted)"),
    ("colon_cancer_primaries", "Colorectal cancer", "CT"),
    ("kidney_tumor", "Kidney tumor", "CT"),
    ("liver_tumor", "Liver tumor", "CT"),
    ("lung_tumor", "Lung tumor", "CT"),
    ("pancreatic_tumor", "Pancreatic tumor", "CT"),
]
TURING_PER_CLASS = 2      # per tumor type: this many real and this many synthetic

# Original vs RadWorld pairs (tumor region re-synthesized), outside the reader set, picked by eye
# from the candidate sheets for image quality: (folder, label, file in best_tumor_cases, window).
TUMOR_PAIRS = [
    ("lung_tumor", "Lung tumor", "044.nii.gz", "lung"),
    ("kidney_tumor", "Kidney tumor", "043.nii.gz", "reader"),
    ("liver_tumor", "Liver tumor", "041.nii.gz", "reader"),
    ("pancreatic_tumor", "Pancreatic tumor", "043.nii.gz", "reader"),
]

# Cases built from outputs copied back from the GPU server (see README, "Adding samples").
# Each pane is one NIfTI file. kind: "ct" (HU), "mr" (any scale, 0.5 to 99.5 percentile) or
# "mask" (binary, drawn as an outline). Relative paths are resolved against SERVER_OUT.
# A case with a placeholder of the same id in PENDING replaces that placeholder.
SERVER_OUT = HOME / "Desktop/radworld_server_outputs"
SO, HG, AL = SERVER_OUT / "signoff", SERVER_OUT / "homepage_gen", SERVER_OUT / "aligned"
DEMO_DATA = HOME / "Downloads/demo_data"
GEN_TEXT = "Only the scan type, the anatomy to include, the voxel spacing and the volume size. No image, report or mask."
EXTRA_CASES = [
    # ---- whole-volume generation (fully synthetic). Picked by eye on 2026-09-28 from all 75 CT and
    # 30 MRI samples (25 and 10 prompts, seeds 1995, 7 and 42), for realism in all three planes. The
    # crosshair sits on the body centre, with the axial level on typical anatomy. The skull-stripped
    # brain MRI samples with lesions were dropped because their reformats look artificial.
    {"group": "generation", "layout": "triplanar", "id": "pretrain_ct", "label": "Chest CT",
     "panes": [{"file": str(SO / "pretrain/case07.nii.gz"), "kind": "ct", "title": "RadWorld, generated from scan type and anatomy", "render3d": True}],
     "window": "mediastinum", "windows": ["mediastinum", "lung", "bone"], "summary": GEN_TEXT, "inputLabel": "Input",
     "cross": [127, 104, 79]},
    {"group": "generation", "layout": "triplanar", "id": "gen_abdomen", "label": "Abdomen and pelvis CT",
     "panes": [{"file": str(HG / "seed_42/pretrain/case13.nii.gz"), "kind": "ct", "title": "RadWorld, generated from scan type and anatomy", "render3d": True}],
     "window": "abdomen", "windows": ["abdomen", "bone"], "summary": GEN_TEXT, "inputLabel": "Input",
     "cross": [127, 111, 76]},
    {"group": "generation", "layout": "triplanar", "id": "gen_hn", "label": "Head and neck CT",
     "panes": [{"file": str(SO / "pretrain/case01.nii.gz"), "kind": "ct", "title": "RadWorld, generated from scan type and anatomy", "render3d": True}],
     "window": "soft", "windows": ["soft", "bone"], "summary": GEN_TEXT, "inputLabel": "Input", "render3dPresets": ["bone"],
     "cross": [127, 118, 102]},
    {"group": "generation", "layout": "triplanar", "id": "gen_pelvis", "label": "Pelvis CT",
     "panes": [{"file": str(HG / "seed_7/pretrain/case18.nii.gz"), "kind": "ct", "title": "RadWorld, generated from scan type and anatomy", "render3d": True}],
     "window": "abdomen", "windows": ["abdomen", "bone"], "summary": GEN_TEXT, "inputLabel": "Input",
     "cross": [126, 128, 44]},
    {"group": "generation", "layout": "triplanar", "id": "pretrain_mr", "label": "Brain MRI (T1CE)",
     "panes": [{"file": str(HG / "seed_42/pretrain_mr/case07.nii.gz"), "kind": "mr", "title": "RadWorld, generated from scan type and anatomy"}],
     "summary": GEN_TEXT, "inputLabel": "Input"},
    # ---- translation: input, RadWorld output and acquired reference on one grid (tools/model_grid.py)
    {"group": "translation", "layout": "compare", "id": "cbct2ct", "label": "CBCT to CT, head and neck", "source": "SynthRAD2025",
     "text": "Cone-beam CT with streak artifacts, translated into CT. The patient's real CT is shown for comparison.",
     "panes": [{"file": str(AL / "cbct2ct_case05_input.nii.gz"), "kind": "ct", "title": "Input CBCT"},
               {"file": str(SO / "cbct2ct/case05.nii.gz"), "kind": "ct", "title": "RadWorld CT", "render3d": True},
               {"file": str(AL / "cbct2ct_case05_reference.nii.gz"), "kind": "ct", "title": "Real CT"}],
     "window": "soft", "windows": ["soft", "bone"], "credit": "SynthRAD2025 case 2HNA070 (center A), CC BY-NC 4.0",
     "render3dPresets": ["bone"]},  # head and neck of a real patient: no surface rendering
    {"group": "translation", "layout": "compare", "id": "cbct2ct_ab", "label": "CBCT to CT, abdomen", "source": "SynthRAD2025",
     "text": "Abdominal cone-beam CT with uncalibrated intensities, translated into CT. The patient's real CT is shown for comparison.",
     "panes": [{"file": str(AL / "cbct2ct_case01_input.nii.gz"), "kind": "auto", "title": "Input CBCT"},
               {"file": str(SO / "cbct2ct/case01.nii.gz"), "kind": "ct", "title": "RadWorld CT", "render3d": True},
               {"file": str(AL / "cbct2ct_case01_reference.nii.gz"), "kind": "ct", "title": "Real CT"}],
     "window": "abdomen", "windows": ["abdomen", "bone"], "credit": "SynthRAD2025 case 2ABC137 (center C), CC BY-NC 4.0", "level": 0.3},
    {"group": "translation", "layout": "compare", "id": "mr2ct_ab", "label": "MR to CT, abdomen", "source": "SynthRAD2025",
     "text": "Abdominal MR, translated into CT. The patient's real CT is shown for comparison.",
     "panes": [{"file": str(AL / "mr2ct_case01_input.nii.gz"), "kind": "mr", "title": "Input MR"},
               {"file": str(SO / "mr2ct/case01.nii.gz"), "kind": "ct", "title": "RadWorld CT", "render3d": True},
               {"file": str(AL / "mr2ct_case01_reference.nii.gz"), "kind": "ct", "title": "Real CT"}],
     "window": "abdomen", "windows": ["abdomen", "bone"], "credit": "SynthRAD2025 case 1ABB035 (center B), CC BY-NC 4.0"},
    {"group": "translation", "layout": "compare", "id": "ct_phase", "label": "Non-contrast to arterial phase", "source": "Coltea-Lung-CT-100W",
     "text": "Arterial-phase CT generated from non-contrast CT. The real arterial phase, aligned to the input, is shown for comparison.",
     "panes": [{"file": str(DEMO_DATA / "ct_arterial/case02_source.nii.gz"), "kind": "ct", "title": "Input non-contrast CT"},
               {"file": str(SO / "ct_arterial/case02.nii.gz"), "kind": "ct", "title": "RadWorld arterial phase", "render3d": True},
               {"file": str(AL / "ct_arterial_case02_reference.nii.gz"), "kind": "ct", "title": "Real arterial phase"}],
     "window": "mediastinum", "windows": ["mediastinum", "lung"], "credit": "Coltea-Lung-CT-100W case CH24092019, CC BY-SA 4.0"},
    {"group": "translation", "layout": "compare", "id": "ct_venous", "label": "Non-contrast to venous phase", "source": "Coltea-Lung-CT-100W",
     "text": "Venous-phase CT generated from non-contrast CT. The real venous phase, aligned to the input, is shown for comparison.",
     "panes": [{"file": str(DEMO_DATA / "ct_venous/case01_source.nii.gz"), "kind": "ct", "title": "Input non-contrast CT"},
               {"file": str(SO / "ct_venous/case01.nii.gz"), "kind": "ct", "title": "RadWorld venous phase", "render3d": True},
               {"file": str(AL / "ct_venous_case01_reference.nii.gz"), "kind": "ct", "title": "Real venous phase"}],
     "window": "mediastinum", "windows": ["mediastinum", "lung"], "credit": "Coltea-Lung-CT-100W case SG20102015, CC BY-SA 4.0"},
]

# ---- CT generated from organ label maps (m2i_organ demo). The label maps were made from WORD CT
# scans, whose terms (GPL-3.0, research use only) have not been confirmed for a public page, so
# keep INCLUDE_WORD_M2I = False for the public build unless the WORD authors agree, or regenerate
# these cases from label maps of a CC BY dataset.
INCLUDE_WORD_M2I = True
M2I = Path.home() / "Downloads/demo_data/m2i_organ"
M2I_TEXT = "RadWorld generated this CT from the organ mask, which labels each organ and structure."
if INCLUDE_WORD_M2I:
    EXTRA_CASES += [
        {"group": "mask", "layout": "compare", "id": "m2i_a", "label": "Abdomen and pelvis 1", "source": "WORD",
         "text": M2I_TEXT, "credit": "Organ mask derived from a WORD CT scan (research use)",
         "panes": [{"file": str(M2I / "case02_cond.nii.gz"), "kind": "labels", "body": 250, "title": "Input organ mask"},
                   {"file": str(SO / "m2i_organ/case02.nii.gz"), "kind": "ct", "title": "RadWorld CT", "render3d": True}],
         "window": "abdomen", "windows": ["abdomen", "bone"], "cross": [127, 141, 106], "render3dPresets": ["bone"]},
        {"group": "mask", "layout": "compare", "id": "m2i_b", "label": "Abdomen and pelvis 2", "source": "WORD",
         "text": M2I_TEXT, "credit": "Organ mask derived from a WORD CT scan (research use)",
         "panes": [{"file": str(M2I / "case10_cond.nii.gz"), "kind": "labels", "body": 250, "title": "Input organ mask"},
                   {"file": str(SO / "m2i_organ/case10.nii.gz"), "kind": "ct", "title": "RadWorld CT", "render3d": True}],
         "window": "abdomen", "windows": ["abdomen", "bone"], "cross": [127, 129, 99], "render3dPresets": ["bone"]},
    ]

# Report-guided cases generated from reports written by the authors (tools/server/reports_*_v2.json),
# so the full input report can be shown next to the volume. Picked by eye from four samples each.
HG2 = SERVER_OUT / "homepage_gen2"
REPORT_JSON = [ROOT / "tools/server/reports_chest_v2.json", ROOT / "tools/server/reports_chest_v3.json"]
OWN_REPORT_CASES = [  # id, tab label, region, sample file (relative to SERVER_OUT), window, windows, axial level (0 = inferior)
    ("rep_cardiomegaly", "Cardiomegaly", "chest", "homepage_gen2/cfg_4/reports_chest_v2/cardiomegaly_s3.nii.gz", "mediastinum", ["mediastinum", "lung", "bone"], 0.5),
    ("rep_effusion", "Pleural effusion", "chest", "homepage_gen2/cfg_4/reports_chest_v2/pleural_effusion_s0.nii.gz", "mediastinum", ["mediastinum", "lung", "bone"], 0.4),
    ("rep_pneumonia", "Pneumonia", "chest", "homepage_gen3/reports_chest_v3/pneumonia_bilateral_s3.nii.gz", "lung", ["lung", "mediastinum"], 0.45),
    ("rep_mass", "Lung cancer", "chest", "homepage_gen3/reports_chest_v3/lung_mass_s3.nii.gz", "lung", ["lung", "mediastinum"], 0.78),
]

# Report-guided CT from the code release: outputs of scripts/demo.sh (t2i_chest, t2i_abdomen),
# copied from the release folder on the server to SERVER_OUT/release_outputs. Their prompts are
# dataset reports that may not be redistributed, so the page lists only the main findings, in our
# own words, and never the report text.
RELEASE_OUT = SERVER_OUT / "release_outputs/outputs"
RELEASE_REPORT_CASES = [  # id, tab label, release case, window, windows, axial level (0 = inferior), main findings
    ("rep_covid", "Pneumonia", "t2i_chest/case04", "lung", ["lung", "mediastinum", "bone"], 0.5,
     "Patchy ground-glass opacities at the periphery of both lower lobes, consistent with COVID-19 pneumonia."),
    ("rep_effusions", "Pleural effusions", "t2i_chest/case02", "mediastinum", ["mediastinum", "lung", "bone"], 0.55,
     "Pleural effusions on both sides, larger on the right. Patchy and band-like opacities in both lungs. "
     "Calcified plaques in the aorta and coronary arteries."),
    ("rep_gallbladder", "Distended gallbladder", "t2i_abdomen/case08", "abdomen", ["abdomen", "bone"], 0.68,
     "Distended gallbladder with a thickened wall and no stones. Diverticulosis of the colon."),
]
# Reviewed but not shown: the other release cases, whose main findings are too subtle to see at a glance
# (for example t2i_abdomen/case01, enlarged liver, and case15, right hydronephrosis).

# Tab order per group (ids not listed keep their build order, after the listed ones).
TAB_ORDER = {
    "generation": ["pretrain_ct", "gen_abdomen", "gen_hn", "gen_pelvis", "pretrain_mr"],
    "translation": ["cbct2ct", "mr2ct", "cbct2ct_ab", "mr2ct_ab", "ct_phase", "ct_venous"],
    "report": ["rep_covid", "rep_effusions", "rep_gallbladder"],
}

# Placeholders for settings whose outputs are only on the GPU server.
PENDING = []  # every setting shown on the page has samples now


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def canonical(path):
    """Load a NIfTI file, reorient to RAS. Returns data, zooms and a function that maps
    a voxel index in file order to the canonical index."""
    img = nib.load(str(path))
    data = np.asanyarray(img.dataobj)
    tr = ornt_.ornt_transform(ornt_.io_orientation(img.affine), ornt_.axcodes2ornt(("R", "A", "S")))
    out = ornt_.apply_orientation(data, tr)
    zooms_in = [float(z) for z in img.header.get_zooms()[:3]]
    zooms = [0.0, 0.0, 0.0]
    for i, (ax, _) in enumerate(tr):
        zooms[int(ax)] = zooms_in[i]

    def map_index(ijk):
        res = [0, 0, 0]
        for i, (ax, fl) in enumerate(tr):
            v = int(ijk[i])
            res[int(ax)] = data.shape[i] - 1 - v if fl < 0 else v
        return res

    return np.ascontiguousarray(out), [round(z, 4) for z in zooms], map_index


def enc_ct(hu):
    return np.round(np.interp(np.clip(hu, -1000, 1000), CT_HU, CT_RAW)).astype(np.uint8)


def dec_ct(raw):
    return np.interp(raw.astype(np.float32), CT_RAW, CT_HU)


def enc_lin(a, lo, hi):
    return np.round(np.clip((a.astype(np.float32) - lo) / (hi - lo), 0, 1) * 255).astype(np.uint8)


def encoding_ct():
    return {"type": "piecewise", "raw": CT_RAW, "val": CT_HU, "unit": "HU"}


def encoding_lin(lo, hi, unit=""):
    return {"type": "linear", "lo": float(lo), "hi": float(hi), "unit": unit}


def decode(raw, enc):
    if enc["type"] == "piecewise":
        return np.interp(raw.astype(np.float32), enc["raw"], enc["val"])
    return enc["lo"] + raw.astype(np.float32) / 255.0 * (enc["hi"] - enc["lo"])


def lut(enc, window):
    """256-entry grey LUT for a raw uint8 volume, given its encoding and a window."""
    vals = decode(np.arange(256), enc)
    lo, hi = window
    if lo is None:
        lo, hi = float(vals[0]), float(vals[-1])
    return np.clip((vals - lo) / (hi - lo), 0, 1) * 255


def save_u8(arr, zooms, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    aff = np.diag([zooms[0], zooms[1], zooms[2], 1.0])
    img = nib.Nifti1Image(np.asarray(arr, dtype=np.uint8), aff)
    img.set_sform(aff, code=1)
    img.set_qform(aff, code=1)
    img.header.set_xyzt_units("mm")
    img.header["descrip"] = b"RadWorld project page volume"
    path.write_bytes(gzip.compress(img.to_bytes(), compresslevel=9, mtime=0))
    return path.stat().st_size


def plane_slice(vol, plane, cross):
    """Return the 2D slice in screen orientation (radiological, superior/anterior up)."""
    i, j, k = cross
    if plane == "axial":
        s = vol[:, :, k]
    elif plane == "coronal":
        s = vol[:, j, :]
    else:
        s = vol[i, :, :]
    return s[::-1, ::-1].T


def plane_extent(shape, zooms, plane):
    nx, ny, nz = shape
    dx, dy, dz = zooms
    return {"axial": (nx * dx, ny * dy), "coronal": (nx * dx, nz * dz), "sagittal": (ny * dy, nz * dz)}[plane]


def outline(mask2d):
    m = mask2d > 0
    inner = m.copy()
    inner[1:, :] &= m[:-1, :]
    inner[:-1, :] &= m[1:, :]
    inner[:, 1:] &= m[:, :-1]
    inner[:, :-1] &= m[:, 1:]
    return m & ~inner


def screen_xy(shape, plane, cross):
    """Crosshair position in the screen-oriented slice (column, row)."""
    nx, ny, nz = shape
    i, j, k = cross
    return {"axial": (nx - 1 - i, ny - 1 - j), "coronal": (nx - 1 - i, nz - 1 - k), "sagittal": (ny - 1 - j, nz - 1 - k)}[plane]


def render(vol, enc, window, plane, cross, zooms, mask=None, width=POSTER_W, color=(255, 196, 61), zoom=1.0):
    s = plane_slice(vol, plane, cross)
    grey = lut(enc, window)[s].astype(np.uint8)
    rgb = np.stack([grey] * 3, -1)
    if mask is not None:
        o = outline(plane_slice(mask, plane, cross))
        rgb[o] = color
    if zoom > 1:  # same view rectangle as the page viewer: centred on the crosshair, clamped
        H, W = s.shape
        vw, vh = W / zoom, H / zoom
        cx, cy = screen_xy(vol.shape, plane, cross)
        x0 = min(max(cx + 0.5 - vw / 2, 0), W - vw)
        y0 = min(max(cy + 0.5 - vh / 2, 0), H - vh)
        img = Image.fromarray(rgb).resize((W * 4, H * 4), Image.NEAREST)
        rgb_img = img.crop((int(x0 * 4), int(y0 * 4), int((x0 + vw) * 4), int((y0 + vh) * 4)))
    else:
        rgb_img = Image.fromarray(rgb)
    w_mm, h_mm = plane_extent(vol.shape, zooms, plane)
    h = max(1, int(round(width * h_mm / w_mm)))
    return rgb_img.resize((width, h), Image.BICUBIC)


def label_colors(labels, body=None):
    """RGB per remapped label (index 0 is background). Neighbouring labels get well separated hues
    (golden-angle steps), and the whole-body label, if given, a quiet grey."""
    import colorsys
    colors, k = [[0, 0, 0]], 0
    for v in labels:
        if v == body:
            colors.append([66, 68, 78])
            continue
        r, g, b = colorsys.hls_to_rgb((k * 0.618033988749895) % 1.0, 0.58, 0.62)
        colors.append([int(r * 255), int(g * 255), int(b * 255)])
        k += 1
    return colors


def render_labels(vol, colors, plane, cross, zooms, width=POSTER_W):
    s = plane_slice(vol, plane, cross)
    img = Image.fromarray(np.array(colors, np.uint8)[s])
    w_mm, h_mm = plane_extent(vol.shape, zooms, plane)
    return img.resize((width, max(1, int(round(width * h_mm / w_mm)))), Image.NEAREST)


def save_webp(img, path, q=86):
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "WEBP", quality=q, method=6)
    return path


def rel(p):
    return str(Path(p).relative_to(ROOT))


def body_z_range(vol_raw, enc, thr):
    """Axial range containing tissue above a threshold (in decoded units)."""
    vals = decode(np.arange(256), enc)
    above = vals[vol_raw] > thr
    z = np.where(above.reshape(-1, vol_raw.shape[2]).sum(0) > 500)[0]
    return (int(z.min()), int(z.max())) if len(z) else (0, vol_raw.shape[2] - 1)


class Manifest:
    def __init__(self):
        self.volumes = {}
        self.groups = {}

    def add_volume(self, key, arr, zooms, enc, path):
        size = save_u8(arr, zooms, path)
        self.volumes[key] = {"url": rel(path), "dims": list(arr.shape), "spacing": zooms, "encoding": enc, "bytes": size}
        return key

    def add_case(self, group, layout, case):
        g = self.groups.setdefault(group, {"layout": layout, "cases": []})
        g["cases"].append(case)


# ---------------------------------------------------------------------------
# builders
# ---------------------------------------------------------------------------
def build_report(man):
    # The CT-RATE terms do not allow redistributing any portion of the dataset, so the page names
    # the finding described in each source report instead of reproducing the report.
    import re
    prompts = {r["filename"]: r["caption"] for r in csv.DictReader(open(VIS / "selected_cases.csv", encoding="utf-8"))}
    enc = encoding_ct()
    for cid, label, relpath, slice_id, win, pattern in REPORT_CASES:
        if not re.search(pattern, prompts.get(Path(relpath).name, ""), re.I):
            raise SystemExit(f"report case {cid}: the prompt for {relpath} does not mention '{pattern}'")
        src = VIS / relpath
        data, zooms, idx = canonical(src)
        raw = enc_ct(data)
        k = idx([0, 0, slice_id - 1])[2]
        cross = [raw.shape[0] // 2, raw.shape[1] // 2, k]
        vkey = man.add_volume(f"report_{cid}", raw, zooms, enc, ROOT / f"assets/vol/report/{cid}.nii.gz")
        posters = {}
        for plane in ("axial", "coronal", "sagittal"):
            posters[plane] = rel(save_webp(render(raw, enc, (WINDOWS[win]["lo"], WINDOWS[win]["hi"]), plane, cross, zooms),
                                           ROOT / f"assets/img/poster/report/{cid}_{plane}.webp"))
        man.add_case("report", "triplanar", {
            "id": cid, "label": label,
            "summary": f"Generated from a CT-RATE validation report that describes {label.lower()}.",
            "note": "The report itself is not reproduced here because the CT-RATE terms do not allow redistribution. "
                    "The volume is a RadWorld output, not the patient's acquired scan.",
            "panes": [{"vol": vkey, "title": "RadWorld, generated from the report", "posters": posters, "render3d": True}],
            "window": win, "windows": ["mediastinum", "lung", "bone"], "cross": cross,
        })
        print(f"report/{cid}: {man.volumes[vkey]['bytes'] // 1024} KB")


def build_mr2ct(man):
    enc_c = encoding_ct()
    mr, zooms, _ = canonical(FIG1 / "modality_transfer/1HNA124_mr.nii.gz")
    ct_gen, _, _ = canonical(FIG1 / "modality_transfer/1HNA124_ct.nii.gz")
    ct_ref, _, _ = canonical(FIG1 / "modality_transfer/1HNA124_ct_real.nii.gz")
    # the preprocessed reference CT is padded with -1 HU at both sides; show the padding as air
    pad = np.all(ct_ref == -1, axis=1, keepdims=True) & (ct_ref == -1)
    ct_ref = np.where(pad, -1000, ct_ref)
    lo, hi = np.percentile(mr[mr > 0], [0.5, 99.5]) if (mr > 0).any() else (mr.min(), mr.max())
    enc_m = encoding_lin(0, hi, "a.u.")
    mr_u8 = enc_lin(mr, 0, hi)
    gen_u8, ref_u8 = enc_ct(ct_gen), enc_ct(ct_ref)
    bone = (ct_ref > 300).reshape(-1, ct_ref.shape[2]).sum(0)
    k = int(np.argmax(bone))
    cross = [mr.shape[0] // 2, mr.shape[1] // 2, k]
    v_mr = man.add_volume("mr2ct_mr", mr_u8, zooms, enc_m, ROOT / "assets/vol/translation/mr2ct_input_mr.nii.gz")
    v_gen = man.add_volume("mr2ct_radworld", gen_u8, zooms, enc_c, ROOT / "assets/vol/translation/mr2ct_radworld.nii.gz")
    v_ref = man.add_volume("mr2ct_reference", ref_u8, zooms, enc_c, ROOT / "assets/vol/translation/mr2ct_reference.nii.gz")
    panes = []
    for key, arr, enc, title, win in [(v_mr, mr_u8, enc_m, "Input MR", "auto"),
                                      (v_gen, gen_u8, enc_c, "RadWorld CT", "bone"),
                                      (v_ref, ref_u8, enc_c, "Real CT", "bone")]:
        w = WINDOWS[win]
        img = render(arr, enc, (w["lo"], w["hi"]), "axial", cross, zooms)
        posters = {"axial": rel(save_webp(img, ROOT / f"assets/img/poster/translation/mr2ct_{key}_axial.webp"))}
        panes.append({"vol": key, "title": title, "posters": posters, "fixedWindow": "auto" if enc is enc_m else None,
                      "render3d": key == v_gen})
    man.add_case("translation", "compare", {
        "id": "mr2ct", "label": "MR to CT, head and neck", "source": "SynthRAD2025", "credit": "SynthRAD2025 case 1HNA124 (center A), CC BY-NC 4.0",
        "text": "Head and neck MR, translated into CT. The patient's real CT is shown for comparison.",
        "panes": panes, "plane": "axial", "window": "bone", "windows": ["bone", "soft"], "cross": cross,
        # head and neck: no surface or soft-tissue rendering, which would reconstruct the patient's face
        "render3dPresets": ["bone"],
    })
    print("translation/mr2ct:", sum(man.volumes[v]["bytes"] for v in (v_mr, v_gen, v_ref)) // 1024, "KB")


def build_word_tumors(man):
    enc = encoding_ct()
    for cid, label, case, mask_dir, gen_dir in WORD_TUMOR_CASES:
        real, zooms, _ = canonical(WORDV / "real_images" / f"{case}.nii.gz")
        gen, _, _ = canonical(WORDV / gen_dir / f"{case}.nii.gz")
        mask, _, _ = canonical(WORDV / mask_dir / f"{case}.nii.gz")
        mask = (mask > 0).astype(np.uint8)
        zz = np.where(mask.reshape(-1, mask.shape[2]).sum(0) > 0)[0]
        k = int(zz[np.argmax(mask.reshape(-1, mask.shape[2]).sum(0)[zz])])
        ii, jj = np.where(mask[:, :, k])
        cross = [int(ii.mean()), int(jj.mean()), k]
        r_u8, g_u8 = enc_ct(real), enc_ct(gen)
        v_r = man.add_volume(f"{cid}_input", r_u8, zooms, enc, ROOT / f"assets/vol/tumor/{cid}_input.nii.gz")
        v_g = man.add_volume(f"{cid}_radworld", g_u8, zooms, enc, ROOT / f"assets/vol/tumor/{cid}_radworld.nii.gz")
        v_m = man.add_volume(f"{cid}_mask", mask, zooms, {"type": "label"}, ROOT / f"assets/vol/tumor/{cid}_mask.nii.gz")
        w = WINDOWS["abdomen"]
        panes = []
        for key, arr, title, mode in [(v_r, r_u8, "Normal CT with the supplied tumor mask", "always"),
                                      (v_g, g_u8, "RadWorld, tumor synthesized inside the mask", "toggle")]:
            img = render(arr, enc, (w["lo"], w["hi"]), "axial", cross, zooms, mask=mask if mode == "always" else None, zoom=2.5)
            panes.append({"vol": key, "title": title, "mask": mode,
                          "posters": {"axial": rel(save_webp(img, ROOT / f"assets/img/poster/tumor/{cid}_{key}_axial.webp"))}})
        man.add_case("tumor_word", "compare", {
            "id": cid, "label": label, "credit": f"Normal abdominal CT from WORD ({case})", "mask": v_m, "zoom": 2.5,
            "panes": panes, "plane": "axial", "window": "abdomen", "windows": ["abdomen", "mediastinum", "bone"], "cross": cross,
        })
        print(f"tumor_word/{cid}:", sum(man.volumes[v]["bytes"] for v in (v_r, v_g, v_m)) // 1024, "KB")


def build_extra(man):
    for spec in EXTRA_CASES:
        vols, zooms, first_shape = [], None, None
        for pane in spec["panes"]:
            path = Path(pane["file"]) if Path(pane["file"]).is_absolute() else SERVER_OUT / pane["file"]
            data, z, _ = canonical(path)
            if first_shape is None:
                first_shape, zooms = data.shape, z
            elif data.shape != first_shape:
                raise SystemExit(f"{spec['id']}: {path.name} has shape {data.shape}, expected {first_shape}")
            if pane["kind"] == "ct":
                enc, u8 = encoding_ct(), enc_ct(data)
            elif pane["kind"] == "mask":
                enc, u8 = {"type": "label"}, (data > 0).astype(np.uint8)
            elif pane["kind"] == "labels":  # label map, remapped to 1..K and drawn in colour
                labels = [int(v) for v in np.unique(data) if v != 0]
                remap = np.zeros(int(data.max()) + 1, np.uint8)
                remap[labels] = np.arange(1, len(labels) + 1)
                u8 = remap[data.astype(np.int64)]
                enc = {"type": "labelmap", "colors": label_colors(labels, pane.get("body"))}
            else:
                lo, hi = np.percentile(data, [0.5, 99.5])
                enc, u8 = encoding_lin(lo, hi, "a.u."), enc_lin(data, lo, hi)
            vols.append((pane, enc, u8))
        nx, ny, nz = first_shape
        cross = spec.get("cross") or [nx // 2, ny // 2, int(round(spec.get("level", 0.5) * (nz - 1)))]
        mask_key, mask_arr = None, None
        panes = []
        for n, (pane, enc, u8) in enumerate(vols):
            key = man.add_volume(f"{spec['id']}_{n}", u8, zooms, enc, ROOT / f"assets/vol/extra/{spec['id']}_{n}.nii.gz")
            if pane["kind"] == "mask":
                mask_key, mask_arr = key, u8
                continue
            w = WINDOWS[spec.get("window", "auto")] if enc["type"] == "piecewise" else WINDOWS["auto"]
            planes = ("axial", "coronal", "sagittal") if spec["layout"] == "triplanar" else ("axial",)
            draw = (lambda pl: render_labels(u8, enc["colors"], pl, cross, zooms)) if enc["type"] == "labelmap" \
                else (lambda pl: render(u8, enc, (w["lo"], w["hi"]), pl, cross, zooms))
            posters = {pl: rel(save_webp(draw(pl), ROOT / f"assets/img/poster/extra/{spec['id']}_{n}_{pl}.webp",
                                         q=95 if enc["type"] == "labelmap" else 86)) for pl in planes}
            panes.append({"vol": key, "title": pane["title"], "posters": posters, "render3d": bool(pane.get("render3d")),
                          "fixedWindow": None if enc["type"] == "piecewise" else "auto", "mask": pane.get("mask")})
        case = {k: v for k, v in spec.items() if k not in ("group", "layout", "panes", "file")}
        case.update({"panes": panes, "cross": cross, "extra": True, "plane": "axial"})
        if mask_key:
            case["mask"] = mask_key
        man.add_case(spec["group"], spec["layout"], case)
        print(f"extra/{spec['id']}: {sum(man.volumes[p['vol']]['bytes'] for p in panes) // 1024} KB")


def short_id(identifier):
    """Case name without series details: 'HCC_073_04-03-2004-NA-CT-...' becomes 'HCC_073'."""
    import re
    name = identifier.split("/")[-1].replace(".nii.gz", "")
    return re.split(r"_\d{2}-\d{2}-\d{4}", name)[0]


def build_own_reports(man):
    texts = {}
    for path in REPORT_JSON:
        if path.exists():
            for e in json.loads(path.read_text()):
                texts[e["image_file"]] = e["text"]
    for cid, label, region, rel_file, win, windows, level in OWN_REPORT_CASES:
        path = SERVER_OUT / rel_file
        if not path.exists():
            print(f"own report {cid}: missing {path}")
            continue
        text = texts[Path(rel_file).name.replace(".nii.gz", "")]
        text = text.split(":", 1)[1].strip() if ":" in text[:12] else text
        data, zooms, _ = canonical(path)
        enc, u8 = encoding_ct(), enc_ct(data)
        nx, ny, nz = u8.shape
        cross = [nx // 2, ny // 2, int(round(level * (nz - 1)))]
        w = WINDOWS[win]
        vkey = man.add_volume(cid, u8, zooms, enc, ROOT / f"assets/vol/report/{cid}.nii.gz")
        posters = {pl: rel(save_webp(render(u8, enc, (w["lo"], w["hi"]), pl, cross, zooms),
                                     ROOT / f"assets/img/poster/report/{cid}_{pl}.webp")) for pl in ("axial", "coronal", "sagittal")}
        man.add_case("report", "triplanar", {
            "id": cid, "label": label, "summary": text, "inputLabel": "Input: radiology report",
            "note": "Report written by the authors for this demonstration. RadWorld generated the whole 3D volume from it.",
            "panes": [{"vol": vkey, "title": "RadWorld, generated from the report", "posters": posters, "render3d": True}],
            "window": win, "windows": windows, "cross": cross,
        })
        print(f"own report {cid}: {man.volumes[vkey]['bytes'] // 1024} KB")


def build_release_reports(man):
    for cid, label, case, win, windows, level, findings in RELEASE_REPORT_CASES:
        path = RELEASE_OUT / f"{case}.nii.gz"
        if not path.exists():
            print(f"release report {cid}: missing {path}")
            continue
        data, zooms, _ = canonical(path)
        enc, u8 = encoding_ct(), enc_ct(data)
        nx, ny, nz = u8.shape
        cross = [nx // 2, ny // 2, int(round(level * (nz - 1)))]
        w = WINDOWS[win]
        vkey = man.add_volume(cid, u8, zooms, enc, ROOT / f"assets/vol/report/{cid}.nii.gz")
        posters = {pl: rel(save_webp(render(u8, enc, (w["lo"], w["hi"]), pl, cross, zooms),
                                     ROOT / f"assets/img/poster/report/{cid}_{pl}.webp")) for pl in ("axial", "coronal", "sagittal")}
        man.add_case("report", "triplanar", {
            "id": cid, "label": label, "summary": findings, "inputLabel": "Input: radiology report (main findings)",
            "note": "The full report text is not shown. RadWorld generated the whole 3D volume from the report.",
            "panes": [{"vol": vkey, "title": "RadWorld, generated from the report", "posters": posters, "render3d": True}],
            "window": win, "windows": windows, "cross": cross,
        })
        print(f"release report {cid}: {man.volumes[vkey]['bytes'] // 1024} KB")


def reader_identifiers():
    ids = set()
    for f in (TUM / "human_check_cases/mapping_files").glob("*.csv"):
        ids |= {r["identifier"] for r in csv.DictReader(open(f))}
    return ids


def build_tumor_pairs(man):
    used = reader_identifiers()
    for folder, label, fname, win in TUMOR_PAIRS:
        rows = {r["new_filename"]: r for r in csv.DictReader(open(TUM / f"{folder}_best_50_cases.csv"))}
        r = rows[fname]
        dataset = r["identifier"].split("/")[2]
        if r["identifier"] in used or dataset not in ALLOWED_DATASETS:
            raise SystemExit(f"{folder}/{fname}: in the reader set or from a dataset that may not be shown")
        real, zooms, _ = canonical(TUM / "real" / folder / fname)
        gen, _, _ = canonical(TUM / "gen" / folder / fname)
        mask, _, _ = canonical(TUM / "mask" / folder / fname)
        mask = (mask > 0).astype(np.uint8)
        k = int(np.argmax(mask.reshape(-1, mask.shape[2]).sum(0)))
        ii, jj = np.where(mask[:, :, k])
        cross = [int(ii.mean()), int(jj.mean()), k]
        if win == "lung":  # stored over the full HU range, so lung and mediastinal windows both work
            enc, r_u8, g_u8, windows = encoding_ct(), enc_ct(real), enc_ct(gen), ["lung", "mediastinum"]
        else:  # stored clipped to the reader window
            enc, r_u8, g_u8, windows = encoding_lin(-75, 175, "HU"), enc_lin(real, -75, 175), enc_lin(gen, -75, 175), ["reader"]
        cid = f"pair_{folder}"
        v_r = man.add_volume(f"{cid}_original", r_u8, zooms, enc, ROOT / f"assets/vol/tumor/{cid}_original.nii.gz")
        v_g = man.add_volume(f"{cid}_radworld", g_u8, zooms, enc, ROOT / f"assets/vol/tumor/{cid}_radworld.nii.gz")
        v_m = man.add_volume(f"{cid}_mask", mask, zooms, {"type": "label"}, ROOT / f"assets/vol/tumor/{cid}_mask.nii.gz")
        w = WINDOWS[windows[0]]
        panes = []
        for key, arr, title in [(v_r, r_u8, "Real CT"), (v_g, g_u8, "RadWorld, synthetic tumor")]:
            img = render(arr, enc, (w["lo"], w["hi"]), "axial", cross, zooms, zoom=1.6)
            panes.append({"vol": key, "title": title, "mask": "toggle", "render3d": False,
                          "posters": {"axial": rel(save_webp(img, ROOT / f"assets/img/poster/tumor/{cid}_{key}_axial.webp"))}})
        man.add_case("tumor_pairs", "compare", {
            "id": cid, "label": label, "source": DATASET_LABEL.get(dataset, dataset),
            "text": "RadWorld synthesized a tumor inside the tumor mask of a real CT. The original scan is shown for comparison.",
            "credit": f"{DATASET_LABEL.get(dataset, dataset)}, {short_id(r['identifier'])}, {DATASET_LICENSE[dataset]}",
            "mask": v_m, "zoom": 1.6, "panes": panes, "plane": "axial", "window": windows[0], "windows": windows, "cross": cross,
            "crosshair": False,  # the shared position starts at the lesion centre, keep the lesion unobstructed
        })
        print(f"tumor_pairs/{cid}: {dataset} {fname}", sum(man.volumes[v]["bytes"] for v in (v_r, v_g, v_m)) // 1024, "KB")


def crop_box(mask, inplane=192, zmin_len=24, zmax_len=96, zmargin=8):
    """Crop around a lesion: the whole lesion plus margins when it fits in zmax_len slices,
    otherwise zmax_len slices centred on the area-weighted lesion centre."""
    nx, ny, nz = mask.shape
    ii, jj, kk = np.where(mask > 0)
    ci, cj = (int(ii.min()) + int(ii.max())) // 2, (int(jj.min()) + int(jj.max())) // 2
    i0 = int(np.clip(ci - inplane // 2, 0, max(0, nx - inplane)))
    j0 = int(np.clip(cj - inplane // 2, 0, max(0, ny - inplane)))
    zlo, zhi = int(kk.min()), int(kk.max())
    if zhi - zlo + 1 + 2 * zmargin <= zmax_len:
        z0, z1 = zlo - zmargin, zhi + zmargin + 1
    elif zhi - zlo + 1 <= zmax_len:
        mid = (zlo + zhi) // 2
        z0 = mid - zmax_len // 2
        z1 = z0 + zmax_len
    else:
        per_z = mask.reshape(-1, nz).sum(0)
        kc = int(round(float((per_z * np.arange(nz)).sum() / per_z.sum())))
        z0 = kc - zmax_len // 2
        z1 = z0 + zmax_len
    shift = max(0, -z0) - max(0, z1 - nz)  # keep the window inside the volume
    z0, z1 = max(0, z0 + shift), min(nz, z1 + shift)
    while z1 - z0 < zmin_len and (z0 > 0 or z1 < nz):
        z0, z1 = max(0, z0 - 1), min(nz, z1 + 1)
    return slice(i0, i0 + inplane), slice(j0, j0 + inplane), slice(z0, z1)


def build_turing(man_turing):
    cases = []
    for folder, label, modality in TUMOR_TYPES:
        rows = list(csv.DictReader(open(TUM / f"human_check_cases/mapping_files/{folder}_mapping.csv")))
        picked = {"real": [], "gen": []}
        for r in sorted(rows, key=lambda r: r["encoded_filename"]):
            ds = r["identifier"].split("/")[2]
            if ds not in ALLOWED_DATASETS or len(picked[r["source"]]) >= TURING_PER_CLASS:
                continue
            picked[r["source"]].append((r, ds))
        for src in ("real", "gen"):
            for r, ds in picked[src]:
                fn = r["encoded_filename"]
                img, zooms, _ = canonical(TUM / f"human_check_cases/{folder}/images/{fn}")
                mask, _, _ = canonical(TUM / f"human_check_cases/{folder}/masks/{fn}")
                mask = (mask > 0).astype(np.uint8)
                if mask.sum() == 0:
                    continue
                si, sj, sk = crop_box(mask)
                img, mask = img[si, sj, sk], mask[si, sj, sk]
                if folder == "bladder_tumor":
                    enc, u8, windows = encoding_lin(-1, 1, "a.u."), enc_lin(img, -1, 1), ["auto"]
                elif folder == "lung_tumor":
                    enc, u8, windows = encoding_ct(), enc_ct(img), ["lung", "mediastinum"]
                else:
                    enc, u8, windows = encoding_lin(-75, 175, "HU"), enc_lin(img, -75, 175), ["reader"]
                per_z = mask.reshape(-1, mask.shape[2]).sum(0)
                k = int(np.argmax(per_z))
                ii, jj = np.where(mask[:, :, k])
                cid = f"{folder.split('_')[0]}_{fn.split('_')[0]}"
                vpath = ROOT / f"assets/vol/turing/{cid}.nii.gz"
                mpath = ROOT / f"assets/vol/turing/{cid}_mask.nii.gz"
                vb, mb = save_u8(u8, zooms, vpath), save_u8(mask, zooms, mpath)
                truth = "real" if src == "real" else "synthetic"
                cross_c = [int(ii.mean()), int(jj.mean()), k]
                cases.append({
                    "id": cid, "type": label, "modality": modality, "vol": rel(vpath), "mask": rel(mpath),
                    "dims": list(u8.shape), "spacing": zooms, "encoding": enc, "bytes": vb + mb,
                    "windows": windows, "cross": cross_c,
                    "source": DATASET_LABEL.get(ds, ds), "license": DATASET_LICENSE[ds],
                    "k": base64.b64encode(f"{cid}:{truth}".encode()).decode(),
                })
                print(f"turing/{cid}: {truth:9s} {ds:28s} {u8.shape} {(vb + mb) // 1024} KB")
    return {
        "cases": cases,
        "reference": {
            "overall": 59.7, "overall_ci": [55.6, 63.9], "junior": 52.9, "senior": 66.0,
            "synthetic_called_real": 58.8, "readers": 6, "scans_per_reader": 240, "judgments": 1440,
        },
    }


def build_teaser(man):
    """Animated sweeps (WebP) through volumes already in the manifest. The first teaser item, a
    rotating 3D rendering, comes from tools/capture_3d_teaser.py."""
    items = [  # volume key, window, plane
        ("pretrain_ct_0", "mediastinum", "axial"),
        ("pretrain_mr_0", "auto", "axial"),
        ("rep_effusions", "mediastinum", "axial"),
        ("mr2ct_radworld", "bone", "axial"),
    ]
    axis = {"axial": 2, "coronal": 1, "sagittal": 0}
    out = []
    for key, win, plane in items:
        if key not in man.volumes:
            print("teaser: missing", key)
            continue
        v = man.volumes[key]
        raw = np.asanyarray(nib.load(str(ROOT / v["url"])).dataobj)
        enc, zooms = v["encoding"], v["spacing"]
        w = WINDOWS[win]
        vals = decode(np.arange(256), enc)
        tissue = vals[raw] > (-500 if enc["type"] == "piecewise" else vals[0] + 0.1 * (vals[-1] - vals[0]))
        ax = axis[plane]
        counts = tissue.sum(axis=tuple(a for a in range(3) if a != ax))
        idx = np.where(counts > 0.02 * counts.max())[0]
        lo_i, hi_i = int(idx.min()), int(idx.max())
        span = hi_i - lo_i
        ks = np.linspace(lo_i + 0.12 * span, hi_i - 0.12 * span, 48).round().astype(int)
        ks = np.concatenate([ks, ks[::-1][1:-1]])
        frames = []
        nx, ny, nz = raw.shape
        for k in ks:
            cross = [nx // 2, ny // 2, nz // 2]
            cross[ax] = int(k)
            img = render(raw, enc, (w["lo"], w["hi"]), plane, cross, zooms, width=TEASER_PX)
            if img.height > TEASER_PX:
                img = img.resize((int(img.width * TEASER_PX / img.height), TEASER_PX), Image.BICUBIC)
            canvas = Image.new("RGB", (TEASER_PX, TEASER_PX), (0, 0, 0))
            canvas.paste(img, ((TEASER_PX - img.width) // 2, (TEASER_PX - img.height) // 2))
            frames.append(canvas)
        path = ROOT / f"assets/img/teaser/{key}.webp"
        path.parent.mkdir(parents=True, exist_ok=True)
        frames[0].save(path, "WEBP", save_all=True, append_images=frames[1:], duration=70, loop=0, quality=72, method=6)
        still = save_webp(frames[len(frames) // 4], ROOT / f"assets/img/teaser/{key}_still.webp")
        out.append({"src": rel(path), "still": rel(still)})
        print(f"teaser/{key}: {path.stat().st_size // 1024} KB")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="comma list: report,mr2ct,word,pairs,extra,turing,teaser")
    args = ap.parse_args()
    only = set(filter(None, args.only.split(",")))
    run = lambda name: not only or name in only  # noqa: E731

    gallery_path = ROOT / "data/gallery.json"
    man = Manifest()
    if only and gallery_path.exists():  # partial rebuild: keep the other groups
        old = json.loads(gallery_path.read_text())
        man.volumes, man.groups = old.get("volumes", {}), old.get("groups", {})
        names = {"report": ["report"], "mr2ct": ["translation"], "word": ["tumor_word"], "pairs": ["tumor_pairs"]}
        def drop(case):
            for p in case.get("panes", []):
                man.volumes.pop(p["vol"], None)
            man.volumes.pop(case.get("mask"), None)
        for n in only:
            for g in names.get(n, []):  # rebuilt groups lose their built-in cases, extra cases stay
                if g in man.groups:
                    keep = [c for c in man.groups[g]["cases"] if c.get("extra")]
                    for c in man.groups[g]["cases"]:
                        if not c.get("extra"):
                            drop(c)
                    man.groups[g]["cases"] = keep
            if n == "extra":
                for g in man.groups.values():
                    for c in [c for c in g["cases"] if c.get("extra")]:
                        drop(c)
                    g["cases"] = [c for c in g["cases"] if not c.get("extra")]

    if run("report"):
        build_release_reports(man)  # build_own_reports() and the CT-RATE build_report() are kept for reference
    if run("mr2ct"):
        build_mr2ct(man)
    if run("word") and INCLUDE_WORD:
        build_word_tumors(man)
    if run("pairs") and SHOW_TUMOR_PAIRS:
        build_tumor_pairs(man)
    if run("extra"):
        build_extra(man)
    teaser = build_teaser(man) if run("teaser") else json.loads(gallery_path.read_text()).get("teaser", []) if gallery_path.exists() else []
    for g, order in TAB_ORDER.items():
        if g in man.groups:
            rank = {cid: n for n, cid in enumerate(order)}
            man.groups[g]["cases"].sort(key=lambda c: rank.get(c["id"], len(order)))
    man.groups = {g: v for g, v in man.groups.items() if v["cases"]}  # drop groups left empty
    built = {c["id"] for g in man.groups.values() for c in g["cases"]}
    gallery = {
        "windows": WINDOWS, "volumes": man.volumes, "groups": man.groups, "teaser": teaser,
        "pending": [p for p in PENDING if p["id"] not in built],
    }
    gallery_path.parent.mkdir(parents=True, exist_ok=True)
    gallery_path.write_text(json.dumps(gallery, ensure_ascii=False, indent=1))
    if run("turing"):
        (ROOT / "data/turing.json").write_text(json.dumps(build_turing(None), ensure_ascii=False, indent=1))
    total = sum(v["bytes"] for v in man.volumes.values())
    print(f"gallery volumes: {len(man.volumes)}, {total / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
