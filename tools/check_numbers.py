"""Check that every number on the page appears in the manuscript, and that the page prose
follows the manuscript style rules (no semicolons, no em dashes).

Usage: python tools/check_numbers.py
Exit code 1 if a number is not found in the LaTeX sources (or the text of the figure PDFs) or a style rule
is broken. Needs pdftotext (poppler).
"""
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OV = Path.home() / "Library/CloudStorage/Dropbox/应用/Overleaf/Gen3D"

# ---- manuscript text: only files that main.tex and supplementary.tex actually include
def included(path, seen):
    if path in seen or not path.exists():
        return
    seen.add(path)
    body = re.sub(r"(?<!\\)%[^\n]*", "", path.read_text(encoding="utf-8", errors="ignore"))
    for m in re.finditer(r"\\(?:input|include)\{([^}]+)\}", body):
        name = m.group(1) if m.group(1).endswith(".tex") else m.group(1) + ".tex"
        included(OV / name, seen)


files = set()
for root_tex in ("main.tex", "supplementary.tex"):
    included(OV / root_tex, files)
tex = ""
for f in sorted(files):
    tex += re.sub(r"(?<!\\)%[^\n]*", "", f.read_text(encoding="utf-8", errors="ignore")) + "\n"
tex = tex.replace("{,}", ",").replace("\\%", "%")
# text printed inside the figures counts too (for example the treatment details of Figure 5f)
import subprocess
for pdf in sorted((OV / "resources/figures").glob("figure*.pdf")):
    tex += "\n" + subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True).stdout
tex_numbers = set(re.findall(r"\d[\d,]*\.?\d*", tex))

# ---- page text (visible prose only), plus text the scripts write at run time
page = (ROOT / "index.html").read_text(encoding="utf-8")
def strip_code(src):
    """Remove ${...} expressions (with nested braces) so only the literal text remains."""
    out, i = [], 0
    while i < len(src):
        if src.startswith("${", i):
            depth, i = 1, i + 2
            while i < len(src) and depth:
                depth += {"{": 1, "}": -1}.get(src[i], 0)
                i += 1
            out.append(" ")
        else:
            out.append(src[i])
            i += 1
    return "".join(out)


runtime = []
for js in ("turing.js",):
    src = strip_code((ROOT / "assets/js" / js).read_text(encoding="utf-8"))
    for lit in re.findall(r"`([^`]*)`|'([^'\n]*)'", src):
        runtime.append(lit[0] or lit[1])
data = json.loads((ROOT / "data/turing.json").read_text())
runtime += [str(v) for v in data["reference"].values() if not isinstance(v, list)]
runtime += [str(x) for v in data["reference"].values() if isinstance(v, list) for x in v]
body = re.sub(r"(?s)<(script|style|svg|pre)[^>]*>.*?</\1>", " ", page)
# chart tables are checked cell by cell against their exact sources by tools/check_charts.py
body = re.sub(r"(?s)<table[^>]*>.*?</table>", " ", body)
body = re.sub(r"(?s)<head>.*?</head>", " ", body)
body = re.sub(r"<!--.*?-->", " ", body, flags=re.S)
text = html.unescape(re.sub(r"<[^>]+>", " ", body))
text = re.sub(r"\s+", " ", text + " " + html.unescape(re.sub(r"<[^>]+>", " ", " ".join(runtime))))

# numbers that are not claims: affiliation marks, years, figure and table numbers, model names
IGNORE = {str(i) for i in range(0, 11)} | {"2026", "3D", "12", "16", "22", "40", "82302306"}
IGNORE_CONTEXT = [r"Figure \d", r"Table \d+", r"Extended Data (Figure|Table) \d+", r"Recall@8", r"CC BY(-[A-Z]+)* \d\.\d",
                  r"BraTS20\d\d", r"KiTS20\d\d", r"SynthRAD20\d\d", r"BLEU-2", r"Llama-3\.1-8B", r"1HNA124", r"MS-SSIM", r"T[12]"]
scan = text
for pat in IGNORE_CONTEXT:
    scan = re.sub(pat, " ", scan)

missing = []
for num in sorted(set(re.findall(r"(?<![\w.])\d[\d,]*\.?\d*(?![\w])", scan))):
    n = num.rstrip(".,")
    if n in IGNORE or not n:
        continue
    if n not in tex_numbers and n.replace(",", "") not in {t.replace(",", "") for t in tex_numbers}:
        ctx = re.search(re.escape(num) + r".{0,40}", scan)
        missing.append((n, ctx.group(0) if ctx else ""))

# ---- style: no semicolons or em dashes in prose (the manuscript rule)
style = []
for m in re.finditer(r"[;—]", text):
    style.append(text[max(0, m.start() - 50): m.end() + 20])

# ---- the page describes data by body region and disease: no dataset or cohort names and no sample
# sizes, except in the image credits of the footer. Chart tables count, since tooltips show them, and
# so do the viewer captions from data/gallery.json.
DATASET_NAMES = ["SegRap", "CT-RATE", "TriALS", "PENGWIN", "BraTS", "MSD", "MRISegmenter", "StructSeg", "HECKTOR",
                 "LiTS", "KiTS", "FedBCa", "RAD-ChestCT", "AMOS", "SynthRAD", "Coltea", "WORD", "Merlin", "FHHMU",
                 "FAHJU", "PANORAMA", "TCIA", "HCC-TACE", "QIBA", "RIDER", "QIN-Lung", "Colorectal-Liver", "MSWAL"]
shown = re.sub(r"(?s)<(script|style|svg|pre)[^>]*>.*?</\1>", " ", page)
shown = re.sub(r"(?s)<head>.*?</head>|<!--.*?-->|<details>.*?</details>", " ", shown)
gallery = json.loads((ROOT / "data/gallery.json").read_text())
captions = [str(c.get(k, "")) for g in gallery["groups"].values() for c in g["cases"]
            for k in ("label", "text", "summary", "note", "inputLabel")]
captions += [p.get("title", "") for g in gallery["groups"].values() for c in g["cases"] for p in c.get("panes", [])]
captions += [c["type"] + " " + c["modality"] for c in data["cases"]]
showcase = json.loads((ROOT / "data/showcase.json").read_text())  # the Generation slides
captions += [c["label"] + " " + " ".join(c["input"].get("tags", [])) + " " + c["input"].get("text", "") for g in showcase.values() for c in g]
shown = html.unescape(re.sub(r"<[^>]+>", " ", shown)) + " " + " ".join(captions) + " " + " ".join(runtime)
names = [(n, re.search(r".{0,40}" + re.escape(n) + r".{0,30}", shown).group(0)) for n in DATASET_NAMES
         if re.search(r"(?<![\w-])" + re.escape(n), shown)]
names += [("N =", m.group(0)) for m in re.finditer(r".{0,40}\bN\s*=\s*\d.{0,10}", shown)]

print(f"numbers checked against {len(tex_numbers)} manuscript numbers")
for n, ctx in missing:
    print(f"  NOT IN MANUSCRIPT: {n}   ...{ctx}")
for s in style:
    print(f"  STYLE (semicolon or em dash): ...{s}...")
for n, ctx in names:
    print(f"  DATASET NAME OR SAMPLE SIZE ({n}): ...{ctx}...")
if not missing and not style and not names:
    print("all numbers found in the manuscript, no semicolons or em dashes, no dataset names or sample sizes")
sys.exit(1 if missing or style or names else 0)
