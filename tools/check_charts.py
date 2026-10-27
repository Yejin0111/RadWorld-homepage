"""Check every chart on the page against its exact source in the manuscript.

tools/check_numbers.py only confirms that each number appears somewhere in the LaTeX. This script
ties each chart cell to one table cell (Extended Data tables in supp-table.tex), one phrase of the
Results text or one row of a figure's source data, so a value in the wrong row, column or setting fails.
It covers the charts of the Applications section, the reader-study accuracies of the Turing test panel
and the treatment details of the two TACE slides.

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

ours = {"cls-auc": "+ RadWorld", "tumor-dice": "+ RadWorld", "report": "+ RadWorld", "cindex": "+ virtual post-TACE CT"}
for key in ("tumor-dice", "report"):
    claim(key, "RadWorld highest in every row", lambda v, k: all(v[k] > x for i, x in enumerate(v) if i != k))
claim("cls-auc", "better than real-only training for every abnormality", lambda v, k: v[k] > v[0])
if "cls-auc" in charts:
    overall = next((r for r in charts["cls-auc"]["rows"] if r["label"] == "Overall"), None)
    v = [float(x) for x in overall["values"]] if overall else []
    if not v or v[-1] != max(v) or v.count(max(v)) > 1:
        problems.append(f"cls-auc: title claim 'highest overall AUC' fails: {v}")
claim("cindex", "virtual CT above pre-TACE CT alone and with variables", lambda v, k: v[k] > v[0] and v[k] > v[1])

# ---- Results text
text = results_text()


def phrase(pattern, n):
    m = re.search(pattern, text)
    if not m:
        problems.append(f"phrase not found in the Results text: {pattern}")
        return [None] * n
    return list(m.groups())


COHORT = {"Cohort A": "FHHMU", "Cohort B": "FAHJU"}  # the page names the cohorts by letter
base = phrase(r"from ([\d.]+) with pre-TACE CT alone to ([\d.]+) in Cohort FHHMU and from ([\d.]+) to ([\d.]+) in Cohort FAHJU", 4)
virt = phrase(r"adding virtual post-TACE CT increased the concordance index to ([\d.]+) \(95\\% CI[^)]*\) in Cohort FHHMU and ([\d.]+) \(95\\% CI[^)]*\) in Cohort FAHJU", 2)
real = phrase(r"close to the ([\d.]+) and ([\d.]+) obtained with real post-TACE CT", 2)
c = chart("cindex")
if c:
    expect("C-index", "series", c["head"][1:], ["Pre-TACE CT only", "+ patient and procedural variables", "+ real post-TACE CT", "+ virtual post-TACE CT"])
    want = {"FHHMU": [base[0], base[1], real[0], virt[0]], "FAHJU": [base[2], base[3], real[1], virt[1]]}
    for r in c["rows"]:
        expect("C-index", r["label"], r["values"], want.get(COHORT.get(r["label"])))
    expect("C-index", "rows", [r["label"] for r in c["rows"]], list(COHORT))


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


# ---- the radiologist reader study of the Turing test panel (data/turing.json): overall, junior and senior
# accuracies and the share of synthetic scans judged real from the Results text. The mid-level accuracy
# is drawn in Figure 2d (Overall group) but not printed, so it comes from the figure's source data.
import csv
ref = json.loads((ROOT / "data/turing.json").read_text())["reference"]
acc = phrase(r"overall classification accuracy was ([\d.]+)\\%.*?from ([\d.]+)\\% \(95\\% CI[^)]*\) among junior readers to ([\d.]+)\\%", 3)
called_real = phrase(r"classified as real in ([\d.]+)\\% of assessments", 1)[0]
fig2d = {(r["Organ"], r["Level"]): float(r["Accuracy"]) for r in csv.DictReader(open(OV / "resources/codes/figure2/data/generation-quality-tuning-test/accuracy_ci_turing_test.csv"))}
for key, want in (("overall", acc[0]), ("junior", acc[1]), ("senior", acc[2]), ("synthetic_called_real", called_real),
                  ("mid", f'{100 * fig2d[("Overall", "Mid-Level")]:.1f}')):
    expect("reader study", key, f"{ref.get(key)}", want)
for key, level in (("junior", "Junior"), ("senior", "Senior")):  # the printed values agree with the figure's source data
    expect("reader study", f"{key} (Figure 2d source data)", f"{ref.get(key)}", f"{100 * fig2d[('Overall', level)]:.1f}")

# ---- treatment details of the two TACE slides (age and sex left out). Patient 1 is printed in Figure 5f.
# Patient 2 (10218882) is not in the figure: its actual procedure is the one every perturbed condition of
# the ablation keeps, so the chemotherapy comes from the lipiodol-dose rows and the dose from the others.
import subprocess
fig5 = re.sub(r"\s+", " ", subprocess.run(["pdftotext", "-raw", str(OV / "resources/figures/figure5.pdf"), "-"],
                                         capture_output=True, text=True).stdout)
printed = re.findall(r"Chemo regimen: (.*?)\. Lipiodol dose: (.*?)\. Target artery: (.*?)\.\.\.", fig5)
shown = [[html.unescape(re.sub(r"<[^>]+>", "", d)).strip() for d in re.findall(r"<dd>(.*?)</dd>", block, re.S)]
         for block in re.findall(r'<dl class="simulation-conditions".*?</dl>', PAGE, re.S)]
want = [[re.sub(r" of (\d)", r" \1", chemo).capitalize(), dose, artery.capitalize()] for chemo, dose, artery in printed]
expect("TACE", "patient 1 treatment details (Figure 5f)", shown[:1], want[:1])
P2 = Path.home() / "Downloads/tace_probe8_cases/10218882/conditions.csv"
if P2.exists():
    cond = {r["name"].split("_", 1)[1].rsplit(".nii", 1)[0]: r["condition"] for r in csv.DictReader(open(P2, encoding="utf-8-sig"))}
    field = lambda c, k: re.search(k + r": (.*?);", c).group(1)  # noqa: E731
    chemo = re.sub(r"<([^>]+)> of <(\d+)mg>", r"\1 \2 mg", field(cond["L_5"], "CHEMO_REGIMEN")).capitalize()
    ml = float(re.search(r"<([\d.]+)ml>", field(cond["C_swap"], "LIPIODOL_DOSE")).group(1))
    dose = f"{ml:g} mL"
    artery = field(cond["C_swap"], "TARGET_ARTERY").strip("<>").capitalize()
    expect("TACE", "patient 2 treatment details (10218882)", shown[1:2], [[chemo, dose, artery]])
else:
    print(f"skipped patient 2 treatment details: {P2} not found")

if problems:
    print("\n".join(problems))
    sys.exit(1)
print(f"{len(charts)} charts, the reader study and the TACE details match their exact sources")
