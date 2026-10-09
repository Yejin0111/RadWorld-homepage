"""Check every chart on the page against its exact source in the manuscript.

tools/check_numbers.py only confirms that each number appears somewhere in the LaTeX. This script
ties each chart cell to one table cell (Extended Data tables in supp-table.tex) or to one phrase of
the Results text, so a value in the wrong row, column or setting fails.

Usage: python3 tools/check_charts.py [page.html]     (exit code 1 on any mismatch)
"""
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OV = Path.home() / "Library/CloudStorage/Dropbox/应用/Overleaf/Gen3D"
SUPP = (OV / "resources/sections/supp-table.tex").read_text(encoding="utf-8")
RESULTS = (OV / "resources/sections/2_result.tex").read_text(encoding="utf-8")
PAGE = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "index.html").read_text(encoding="utf-8")
problems = []


def clean_tex(t):
    t = re.sub(r"(?<!\\)%[^\n]*", "", t)
    return t.replace("{,}", ",")


def tex_table(label):
    """Rows of an Extended Data table as lists of cell strings, CIs and formatting removed."""
    t = clean_tex(SUPP)
    i = t.index("\\label{supptable:%s}" % label)
    body = t[i:t.index("\\end{table", i)]
    body = re.sub(r"\{\\scriptsize\s*\[[^\]]*\]\}", "", body)
    body = re.sub(r"\\textbf\{([^}]*)\}", r"\1", body)
    body = re.sub(r"\\makecell(\[[^\]]*\])?\{((?:[^{}]|\{[^{}]*\})*)\}", lambda m: m.group(2).replace("\\\\", " / "), body)
    body = re.sub(r"\\multirow\{[^}]*\}(\[[^\]]*\])?\{\*\}(\[[^\]]*\])?", "", body)
    body = re.sub(r"\\multicolumn\{\d+\}\{[^}]*\}\{([^}]*)\}", r"@@\1", body)
    body = re.sub(r"\{\\scriptsize\s*([^}]*)\}", r"\1", body)
    body = body.replace("$", "").replace("\\to", "to").replace("\\times", "x").replace("\\ ", " ").replace("\\&", "and")
    rows = []
    for r in body.split("\\\\"):
        r = re.sub(r"\\(midrule|cmidrule\{[^}]*\}|toprule|bottomrule)", "", r)
        r = re.sub(r"\s+", " ", r).strip()
        if "@@" in r:
            rows.append(["@@" + r.split("@@", 1)[1].strip("{} ")])
        elif "&" in r:
            rows.append([c.strip().strip("{}").strip() for c in r.split("&")])
    return rows


def results_text():
    t = clean_tex(RESULTS)
    t = re.sub(r"~?\\cite\{[^}]*\}", "", t)
    return re.sub(r"\s+", " ", t.replace("$", ""))


def page_charts():
    """Charts keyed by their data-src attribute, so the copy can change without touching the checks."""
    charts = {}
    for fig in re.findall(r'<figure class="chart[^"]*"[^>]*>.*?</figure>', PAGE, re.S):
        key = re.search(r'data-src="([^"]+)"', fig)
        if not key:
            problems.append("chart without data-src: " + re.sub(r"\s+", " ", fig[:120]))
            continue
        title = html.unescape(re.sub(r"<[^>]+>", "", re.search(r"<h3>(.*?)</h3>", fig, re.S).group(1))).strip()
        sub = html.unescape(re.sub(r"<[^>]+>", "", re.search(r"<figcaption>.*?<p>(.*?)</p>", fig, re.S).group(1))).strip()
        variants = {}
        for tattrs, table in re.findall(r"<table([^>]*)>(.*?)</table>", fig, re.S):
            head = [html.unescape(re.sub(r"<[^>]+>", "", c)).strip() for c in re.findall(r"<th[^>]*>(.*?)</th>", re.search(r"<thead>(.*?)</thead>", table, re.S).group(1), re.S)]
            rows, panel = [], ""
            for attrs, inner in re.findall(r"<tr([^>]*)>(.*?)</tr>", re.search(r"<tbody>(.*?)</tbody>", table, re.S).group(1), re.S):
                cells = re.findall(r"<t([hd])([^>]*)>(.*?)</t[hd]>", inner, re.S)
                new_panel = re.search(r'data-panel="([^"]*)"', cells[0][1])
                panel = new_panel.group(1) if new_panel else panel
                group = re.search(r'data-group="([^"]*)"', attrs)
                full = re.search(r'data-full="([^"]*)"', cells[0][1])
                rows.append({
                    "label": html.unescape(re.sub(r"<[^>]+>", "", cells[0][2])).strip(),
                    "full": full.group(1) if full else "",
                    "panel": panel,
                    "group": group.group(1) if group else "",
                    "values": [c[2].strip() for c in cells[1:]],
                })
            name = re.search(r'data-variant="([^"]*)"', tattrs)
            variants[name.group(1) if name else ""] = {"head": head, "rows": rows}
        first = next(iter(variants.values()))
        charts[key.group(1)] = {"title": title, "sub": sub, "head": first["head"], "rows": first["rows"], "variants": variants}
    return charts


def expect(chart, where, got, want):
    if got != want:
        problems.append(f"{chart}: {where}: page {got}, manuscript {want}")


charts = page_charts()


def chart(key):
    if key not in charts:
        problems.append(f"chart missing on the page: {key}")
        return None
    return charts[key]


# ---- Extended Data Table: per-organ Dice (MAISI, RadWorld)
c = chart("organ-dice")
if c:
    tab = {r[0]: r for r in tex_table("m2i_dice") if len(r) >= 4}
    expect("organ Dice", "series", c["head"][1:], ["MAISI", "RadWorld"])
    for r in c["rows"]:
        src = tab.get(r["label"])
        if not src:
            problems.append(f"organ {r['label']} not in the Dice table")
            continue
        expect("organ Dice", r["label"], r["values"], [src[2], src[3]])  # upper bound, MAISI, RadWorld
    expect("organ Dice", "row count", len(c["rows"]), 16)

# ---- Extended Data Table: FID (first metric column) for eight benchmarks
c = chart("fid")
if c:
    rows, block, region = tex_table("fid_msssim"), None, None
    fid = {}
    region_of = lambda s: s.lower().split()[0].replace("pelvic", "pelvis")  # noqa: E731
    for r in rows:
        if len(r) >= 7 and r[0] in ("CT", "MR"):
            block = r[0]
        if len(r) >= 7:
            if r[1]:  # "Head and Neck / SegRap2023, N=120": key by region, since MRISegmenter covers two
                region = region_of(r[1])
            fid[(block, region, r[2])] = r[3]
    order = ["HA-GAN", "MAISI", "3D-MedDiffusion", "RadWorld"]
    expect("FID", "series", c["head"][1:], order)
    for r in c["rows"]:
        block = {"CT": "CT", "MRI": "MR"}[r["panel"]]
        expect("FID", f"{r['panel']} {r['label']}", r["values"], [fid.get((block, region_of(r["label"]), m)) for m in order])
    expect("FID", "row count", len(c["rows"]), 8)

# ---- Extended Data Table: tumor segmentation, real only and the +2x setting of each generator. Rows use
# the table's abbreviations (as in Figure 3b), and each full name, shown in the tooltip, is the one of
# the Results text.
FULL = {"NPC": "Nasopharyngeal carcinoma", "HNSCC": "Head and neck squamous cell carcinoma",
        "NSCLC": "Non-small cell lung cancer", "HCC": "Hepatocellular carcinoma",
        "PDAC": "Pancreatic ductal adenocarcinoma", "CRC": "Colorectal cancer",
        "RCC": "Renal cell carcinoma", "BLCA": "Bladder cancer"}
c = chart("tumor-dice")
if c:
    seg, order = {}, []
    for r in tex_table("tumor_segmentation"):
        m = re.search(r"([A-Z]+) \(([^)]+)\)", " ".join(r[:2]))
        if m and len(r) >= 9:
            seg[m.group(1)] = r[-7:]  # Real, +1x Diff, +2x Diff, +1x Free, +2x Free, +1x RW, +2x RW
            order.append(m.group(1))
    expect("tumor Dice", "series", c["head"][1:], ["Real data only", "+ DiffTumor", "+ FreeTumor", "+ RadWorld"])
    expect("tumor Dice", "cancers, in the order of the table", [r["label"] for r in c["rows"]], order)
    for r in c["rows"]:
        src = seg.get(r["label"])
        if not src:
            problems.append(f"tumor {r['label']} not in the segmentation table")
            continue
        expect("tumor Dice", r["label"], r["values"], [src[0], src[2], src[4], src[6]])
        expect("tumor Dice", f"{r['label']} full name", r["full"], FULL.get(r["label"]))
        if r["full"] and r["full"].lower() not in re.sub(r"\s+", " ", RESULTS).lower():
            problems.append(f"tumor Dice: full name not in the Results text: {r['full']}")

# ---- Extended Data Table: classification AUC, the 12 abnormalities and the order of Figure 3a, plus the
# Average row as Overall. Figure 3a sorts the abnormalities by mean AUC over its five settings.
c = chart("cls-auc")
if c:
    import csv
    tab = {r[0]: r for r in tex_table("disease_classification") if len(r) >= 8}
    expect("classification", "series", c["head"][1:], ["Real data only", "+ GenerateCT", "+ MedSyn", "+ RadWorld"])
    for r in c["rows"]:
        src = tab.get("Average" if r["label"] == "Overall" else r["label"])
        if not src:
            problems.append(f"abnormality {r['label']} not in the classification table")
            continue
        expect("classification", r["label"], r["values"], [src[1], src[3], src[5], src[7]])  # real and the +2x columns
    nb = json.loads((OV / "resources/codes/figure3/figure3_a.ipynb").read_text())
    code = "\n".join("".join(cell["source"]) for cell in nb["cells"] if cell["cell_type"] == "code")
    shown = re.findall(r'"([a-z_]+)"', code[code.index("classes_to_show <- c("):code.index("# Display name mapping")])
    fig_csv = list(csv.DictReader(open(OV / "resources/codes/figure3/data/chest-disease-classification/summary_by_model_auc.csv")))
    auc = {(r["class"], r["model"]): float(r["mean_auc"]) for r in fig_csv if r["metric"] == "auc"}
    models = ["baseline", "genct_2x", "medsyn_2x", "ours_1x", "ours_2x"]
    order = sorted(shown, key=lambda k: sum(auc[(k, m)] for m in models) / len(models))
    names = {"lymphadenopathy": "Adenopathy", "pulmonary_fibrotic_sequela": "Fibrotic sequela"}
    want = [names.get(k, k.replace("_", " ").capitalize()) for k in order] + ["Overall"]
    expect("classification", "abnormalities and order of Figure 3a", [r["label"] for r in c["rows"]], want)

# ---- Extended Data Table: report generation, each metric by region at +2x, as in Figure 3c
c = chart("report")
if c:
    rows = tex_table("report_generation")

    def block(region):  # Real, then +1x and +2x of GenCT, MedSyn and RadWorld: BLEU-2, ROUGE-L, METEOR, GREEN
        start = next(i for i, r in enumerate(rows) if r[0] == region)
        return {r[1]: r[2:6] for r in rows[start:start + 7]}

    methods = ["Real", "+2x Syn. (GenCT)", "+2x Syn. (MedSyn)", "+2x Syn. (RadWorld)"]
    metrics = ["BLEU-2", "ROUGE-L", "METEOR", "GREEN"]
    regions = {"Chest": "Chest", "Abdomen": "Abdomen", "Pelvis": "Pelvic"}
    expect("report generation", "series", c["head"][1:], ["Real data only", "+ GenerateCT", "+ MedSyn", "+ RadWorld"])
    expect("report generation", "panels and regions", [(r["panel"], r["label"]) for r in c["rows"]],
           [(m, g) for m in metrics for g in regions])
    for r in c["rows"]:
        b, k = block(regions.get(r["label"], r["label"])), metrics.index(r["panel"]) if r["panel"] in metrics else None
        expect("report generation", f"{r['panel']} {r['label']}", r["values"], [b[m][k] for m in methods] if k is not None else None)

# ---- Translation, whole-volume MAE, PSNR and MS-SSIM by method. CBCT, MR and T1CE: the 3D block of the
# Extended Data Table. The contrast phases are pooled as in Figure 4a, so they come from its source data.
import csv
rows = tex_table("modality_transfer")
i3d = next(i for i, r in enumerate(rows) if r[0].startswith("@@3D"))
vol, task = {}, None
for r in rows[i3d + 1:]:
    if len(r) < 6:
        continue
    if r[0]:
        task = r[0]
    vol[(task, r[1])] = {"MAE ↓": r[2], "PSNR (dB) ↑": r[3], "MS-SSIM ↑": r[5]}  # MAE, PSNR, SSIM, MS-SSIM
TR_ORDER = ["ResViT", "pGAN", "MMGAN", "RadWorld"]
METRICS = ["MAE ↓", "PSNR (dB) ↑", "MS-SSIM ↑"]
fig4a = {r["method"]: r for r in csv.DictReader(open(OV / "resources/codes/figure4/data/modality_transfer/ct_phase/summary_by_model.csv"))}
pooled = {m: {"MAE ↓": f"{float(fig4a[k]['MAE_3D']):.3f}", "PSNR (dB) ↑": f"{float(fig4a[k]['PSNR_3D']):.1f}",
              "MS-SSIM ↑": f"{float(fig4a[k]['MS_SSIM_3D']):.4f}"}
          for m, k in zip(TR_ORDER, ["ResViT", "P2P", "MMGAN", "Ours"])}


def tr_task(key):
    return next(t for t in {k for k, _ in vol} if key in t)


for chart_key, setting in (("tr-cbct", "CBCT to CT"), ("tr-mr2ct", "MR to CT"), ("tr-t1ce", "T1CE"), ("tr-phase", None)):
    c = chart(chart_key)
    if not c:
        continue
    expect(chart_key, "series", c["head"][1:], TR_ORDER)
    expect(chart_key, "metrics", [(r["panel"], r["label"]) for r in c["rows"]], [(m, m) for m in METRICS])
    for r in c["rows"]:
        want = [pooled[m][r["label"]] for m in TR_ORDER] if setting is None else [vol[(tr_task(setting), m)][r["label"]] for m in TR_ORDER]
        expect(chart_key, r["label"], r["values"], want)

# ---- Hounsfield-unit profiles of Extended Data Figure 5b,c (rounded to whole HU), and the title's claim:
# RadWorld closer to the real CT than MMGAN along the line
QUAL = OV / "resources/codes/figure4/data/modality_transfer_qualitative"
for chart_key, f in (("hu-cbct", QUAL / "cbct2ct/2ABC137/2ABC137_line_profile_z52.csv"), ("hu-mr2ct", QUAL / "mr2ct/1HNA124/1HNA124_line_profile_z80.csv")):
    c = chart(chart_key)
    if not c:
        continue
    src = list(csv.DictReader(open(f)))
    expect(chart_key, "series", c["head"][1:], ["Real CT", "MMGAN", "RadWorld"])
    page_rows = [[r["label"]] + r["values"] for r in c["rows"]]
    want_rows = [[x["index"], str(round(float(x["GT"]))), str(round(float(x["MMGAN"]))), str(round(float(x["Ours"])))] for x in src]
    expect(chart_key, "profile length", len(page_rows), len(want_rows))
    for got, want in [(g, w) for g, w in zip(page_rows, want_rows) if g != w][:3]:
        expect(chart_key, f"position {want[0]}", got, want)
    gap = lambda k: sum(abs(float(x[k]) - float(x["GT"])) for x in src) / len(src)  # noqa: E731
    if not gap("Ours") < gap("MMGAN"):
        problems.append(f"{chart_key}: title claim fails, RadWorld {gap('Ours'):.0f} HU from the real CT, MMGAN {gap('MMGAN'):.0f} HU")

# ---- Figure 2c and Extended Data Figure 2 source data: Recall@8 and Recall@16 for pools of 32 to 1,024
# candidates, report (i2t) and real-scan (i2i) retrieval. Pool 128 at Recall@8 is also checked against
# the Results text below.
c = chart("report-recall")
REC = OV / "resources/codes/figure2/data/generation-quality-recall"
if c:
    model = {"MedSyn": "MedSyn", "GenerateCT": "GenerateCT", "RadWorld": "Gen3D"}
    panels = {"Chest, Image → Report": ("CT-RATE", "i2t"), "Chest, Image → Image": ("CT-RATE", "i2i"),
              "Abdomen, Image → Report": ("Merlin", "i2t"), "Abdomen, Image → Image": ("Merlin", "i2i")}
    pools = ["32", "64", "128", "256", "512", "1,024"]
    expect("report recall", "variants", list(c["variants"]), ["Recall@8", "Recall@16"])
    for name, v in c["variants"].items():
        k = name.split("@")[1]
        expect("report recall", f"{name} series", v["head"][1:], ["MedSyn", "GenerateCT", "RadWorld"])
        expect("report recall", f"{name} panels and pools", [(r["panel"], r["label"]) for r in v["rows"]], [(pn, pl) for pn in panels for pl in pools])
        for r in v["rows"]:
            ds, kind = panels[r["panel"]]
            src = {x["model"]: float(x[f"recall@{k}_mean"]) for x in csv.DictReader(open(REC / ds / kind / "summary_by_model_recall.csv"))
                   if x["pool_size"] == r["label"].replace(",", "")}
            expect("report recall", f"{name} {r['panel']} {r['label']}", r["values"], [f"{src[model[m]]:.3f}" for m in v["head"][1:]])
        for r in v["rows"]:  # the title's claim holds at every pool size
            vals = [float(x) for x in r["values"]]
            if not vals[2] > max(vals[:2]):
                problems.append(f"report recall: RadWorld not highest in {name} {r['panel']} {r['label']}: {vals}")

# ---- Extended Data Table: BraTS2024 segmentation with the recovered T1CE, all six subregions
c = chart("t1ce")
if c:
    code = {"Enhancing tumor": "ET", "Tumor core": "TC", "Whole tumor": "WT"}  # the BraTS tumor regions
    rows = tex_table("brats_segmentation")
    subregions = next(r for r in rows if "SNFH" in r)[-6:]  # header row: Method, ET, TC, WT, RC, NETC, SNFH
    tab = {r[0]: r for r in rows if r[0] in ("Zero imputation", "MMGAN", "RadWorld")}
    order = ["Zero imputation", "MMGAN", "RadWorld"]
    expect("T1CE recovery", "series", c["head"][1:], order)
    for r in c["rows"]:
        k = subregions.index(code[r["label"]]) + 1
        expect("T1CE recovery", r["label"], r["values"], [tab[m][k] for m in order])
    expect("T1CE recovery", "regions", [r["label"] for r in c["rows"]], list(code))

# ---- the claim in each chart title must hold in every row of that chart
def column(chart_key, name):
    c = charts.get(chart_key)
    k = c["head"].index(name) - 1
    return [(f"{r['panel']} {r['label']}".strip(), [float(v) for v in r["values"]], k) for r in c["rows"]]


def claim(chart_key, text, ok):
    if chart_key not in charts:
        return
    for label, values, k in column(chart_key, ours[chart_key]):
        if not ok(values, k):
            problems.append(f"{chart_key}: title claim '{text}' fails for {label}: {values}")


ours = {"fid": "RadWorld", "organ-dice": "RadWorld", "cls-auc": "+ RadWorld",
        "tumor-dice": "+ RadWorld", "report": "+ RadWorld", "tr-cbct": "RadWorld", "tr-mr2ct": "RadWorld",
        "tr-phase": "RadWorld", "tr-t1ce": "RadWorld", "t1ce": "RadWorld", "lesion": "+ synthetic contrast CT",
        "cindex": "+ virtual post-TACE CT"}
claim("fid", "lowest FID in every benchmark", lambda v, k: all(v[k] < x for i, x in enumerate(v) if i != k))
for key in ("tr-cbct", "tr-mr2ct", "tr-phase", "tr-t1ce"):  # best on every metric: lowest MAE, highest PSNR and MS-SSIM
    if key in charts:
        for r in charts[key]["rows"]:
            v = [float(x) for x in r["values"]]
            best = min(v) if r["label"].startswith("MAE") else max(v)
            if v[-1] != best or v.count(best) > 1:
                problems.append(f"{key}: title claim fails for {r['label']}: {v}")
for key in ("organ-dice", "tumor-dice", "report", "t1ce"):
    claim(key, "RadWorld highest in every row", lambda v, k: all(v[k] > x for i, x in enumerate(v) if i != k))
claim("cls-auc", "better than real-only training for every abnormality", lambda v, k: v[k] > v[0])
if "cls-auc" in charts:
    overall = next((r for r in charts["cls-auc"]["rows"] if r["label"] == "Overall"), None)
    v = [float(x) for x in overall["values"]] if overall else []
    if not v or v[-1] != max(v) or v.count(max(v)) > 1:
        problems.append(f"cls-auc: title claim 'highest overall AUC' fails: {v}")
claim("lesion", "synthetic contrast above non-contrast CT at every level", lambda v, k: v[k] > v[0])
claim("cindex", "virtual CT above pre-TACE CT alone and with variables", lambda v, k: v[k] > v[0] and v[k] > v[1])

# ---- Results text
text = results_text()


def phrase(pattern, n):
    m = re.search(pattern, text)
    if not m:
        problems.append(f"phrase not found in the Results text: {pattern}")
        return [None] * n
    return list(m.groups())


rec = phrase(r"On CT-RATE, RadWorld achieved Recall@8 values of ([\d.]+) for report retrieval and ([\d.]+) for real-scan retrieval\. "
             r"These exceeded the strongest baseline values of ([\d.]+) and ([\d.]+).*?On Merlin, RadWorld reached ([\d.]+) and ([\d.]+), "
             r"compared with ([\d.]+) and ([\d.]+) for the strongest baseline", 8)
c = chart("report-recall")
if c and "Recall@8" in c["variants"]:
    got = {r["panel"]: [float(v) for v in r["values"]] for r in c["variants"]["Recall@8"]["rows"] if r["label"] == "128"}
    for k, panel in enumerate(["Chest, Image → Report", "Chest, Image → Image", "Abdomen, Image → Report", "Abdomen, Image → Image"]):
        v = got.get(panel, [])
        want = [rec[k], rec[2 + k]] if k < 2 else [rec[4 + k - 2], rec[6 + k - 2]]
        expect("report recall", f"{panel}, 128 candidates (Results text)", [f"{v[2]:.3f}", f"{max(v[:2]):.3f}"] if v else None, want)

lesion = phrase(r"overall accuracy from ([\d.]+) \(95\\% CI[^)]*\) with NCCT alone to ([\d.]+) \(95\\% CI[^)]*\), compared with ([\d.]+) \(95\\% CI[^)]*\) with acquired CECT", 3)
c = chart("lesion")
if c:
    # per reader level from the source data of Figure 4c, the overall row also from the Results text
    import csv
    src = OV / "resources/codes/figure4/data/ct_phase_turning_test/accuracy_ci_ct_phase.csv"
    acc4c = {(r["Level"], r["Condition"]): f'{float(r["Accuracy"]):.3f}' for r in csv.DictReader(open(src))}
    levels = {"Junior": "Junior", "Mid-level": "Mid-Level", "Senior": "Senior", "All readers": "Overall"}
    expect("lesion accuracy", "series", c["head"][1:], ["Non-contrast CT only", "+ synthetic contrast CT", "+ acquired contrast CT"])
    for r in c["rows"]:
        lv = levels[r["label"]]
        expect("lesion accuracy", r["label"], r["values"], [acc4c[(lv, k)] for k in ("NC only", "NC + Syn", "NC + Real")])
    expect("lesion accuracy", "All readers (Results text)", next(r for r in c["rows"] if r["label"] == "All readers")["values"], lesion)

base = phrase(r"from ([\d.]+) with pre-TACE CT alone to ([\d.]+) in Cohort FHHMU and from ([\d.]+) to ([\d.]+) in Cohort FAHJU", 4)
virt = phrase(r"adding virtual post-TACE CT increased the concordance index to ([\d.]+) \(95\\% CI[^)]*\) in Cohort FHHMU and ([\d.]+) \(95\\% CI[^)]*\) in Cohort FAHJU", 2)
real = phrase(r"close to the ([\d.]+) and ([\d.]+) obtained with real post-TACE CT", 2)
COHORT = {"Cohort A": "FHHMU", "Cohort B": "FAHJU"}  # the page names the cohorts by letter
c = chart("cindex")
if c:
    expect("C-index", "series", c["head"][1:], ["Pre-TACE CT only", "+ patient and procedural variables", "+ real post-TACE CT", "+ virtual post-TACE CT"])
    want = {"FHHMU": [base[0], base[1], real[0], virt[0]], "FAHJU": [base[2], base[3], real[1], virt[1]]}
    for r in c["rows"]:
        expect("C-index", r["label"], r["values"], want.get(COHORT.get(r["label"])))
    expect("C-index", "rows", [r["label"] for r in c["rows"]], list(COHORT))

acc = phrase(r"overall classification accuracy was ([\d.]+)\\%.*?from ([\d.]+)\\% \(95\\% CI[^)]*\) among junior readers to ([\d.]+)\\%", 3)
c = chart("turing-accuracy")
if c:
    want = {"Junior radiologists": acc[1], "All radiologists": acc[0], "Senior radiologists": acc[2]}
    for r in c["rows"]:
        expect("radiologist accuracy", r["label"], r["values"][0], want.get(r["label"]))

hr = phrase(r"hazard ratio of ([\d.]+) \(95\\% CI, ([\d.]+)--([\d.]+)\) for Cohort FHHMU and ([\d.]+) \(95\\% CI, ([\d.]+)--([\d.]+)\) for Cohort FAHJU", 6)
km = json.loads((ROOT / "data/km.json").read_text())
for k, cohort in enumerate(("FHHMU", "FAHJU")):
    want = hr[3 * k:3 * k + 3]
    fig = re.search(r'<figure class="km" data-cohort="%s">.*?</figure>' % cohort, PAGE, re.S)
    m = re.search(r"Hazard ratio ([\d.]+),", fig.group(0)) if fig else None
    expect("KM", f"{cohort} hazard ratio on the page", m.group(1) if m else None, want[0])
    h3 = re.search(r"<h3>(.*?)</h3>", fig.group(0)).group(1) if fig else None
    expect("KM", f"{cohort} card title", COHORT.get(h3), cohort)
    expect("KM", f"{cohort} hazard ratio in data/km.json", [f"{v:.2f}" for v in km[cohort]["hr"]], want)

# ---- treatment details of the two TACE patients: as printed in Figure 5f (age and sex left out)
import subprocess
fig5 = re.sub(r"\s+", " ", subprocess.run(["pdftotext", "-raw", str(OV / "resources/figures/figure5.pdf"), "-"],
                                         capture_output=True, text=True).stdout)
printed = re.findall(r"Chemo regimen: (.*?)\. Lipiodol dose: (.*?)\. Target artery: (.*?)\.\.\.", fig5)
shown = [[html.unescape(re.sub(r"<[^>]+>", "", d)).strip() for d in re.findall(r"<dd>(.*?)</dd>", block, re.S)]
         for block in re.findall(r'<div class="tace-rx".*?</dl>', PAGE, re.S)]
want = [[re.sub(r" of (\d)", r" \1", chemo).capitalize(), dose, artery.capitalize()] for chemo, dose, artery in printed]
expect("TACE", "treatment details (Figure 5f)", shown, want)

called_real = phrase(r"classified as real in ([\d.]+)\\% of assessments", 1)[0]
m = re.search(r'<p class="turing-stat"><b>([\d.]+)%</b>', PAGE)
expect("Turing section", "synthetic judged real", m.group(1) if m else None, called_real)

if problems:
    print("\n".join(problems))
    sys.exit(1)
print(f"{len(charts)} charts and the key numbers match their exact sources in the manuscript")
