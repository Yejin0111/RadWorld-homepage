"""Convert the abstract and figure legends of the manuscript to HTML snippets.

Label numbers come from main.aux, so the snippets match the compiled PDF.
Usage: python tools/latex_to_html.py > /tmp/snippets.html
"""
import re
from pathlib import Path

OV = Path.home() / "Library/CloudStorage/Dropbox/应用/Overleaf/Gen3D"
aux = (OV / "main.aux").read_text(encoding="utf-8", errors="ignore")
labels = {m.group(1): m.group(2) for m in re.finditer(r"\\newlabel\{([^}]+)\}\{\{([^}]*)\}", aux)}


def tex2html(t):
    t = re.sub(r"(?<!\\)%[^\n]*", "", t)
    t = t.replace("{,}", ",").replace("~", "\u00a0")
    t = re.sub(r"\\ref\{([^}]+)\}", lambda m: labels.get(m.group(1), "??"), t)
    t = re.sub(r"\s*\\cite\{[^}]+\}", "", t)
    t = re.sub(r"\\textbf\{([^{}]*)\}", r"<b>\1</b>", t)
    t = re.sub(r"\\textit\{([^{}]*)\}", r"<i>\1</i>", t)
    t = t.replace("\\%", "%").replace("\\'{e}", "é").replace("\\&", "&amp;")
    t = t.replace("$P$", "<i>P</i>").replace("$t$", "<i>t</i>")
    t = t.replace("$\\times$", "×").replace("\\times", "×")
    t = re.sub(r"\$([^$]*)\$", lambda m: m.group(1).replace("\\,", " ").replace("\\ ", " "), t)
    t = t.replace("<", "&lt;").replace("&lt;b>", "<b>").replace("&lt;/b>", "</b>").replace("&lt;i>", "<i>").replace("&lt;/i>", "</i>")
    t = t.replace("---", "\u2013").replace("--", "\u2013")
    t = t.replace("\\ ", " ").replace("\\", "")
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"\bN ?= ?(?=\d)", "<i>N</i>\u00a0=\u00a0", t)
    t = re.sub(r"\*?P ?&lt; ?(?=\d)", lambda m: ("*" if m.group(0).startswith("*") else "") + "<i>P</i>\u00a0&lt;\u00a0", t)
    t = re.sub(r"\bP ?= ?(?=\d)", "<i>P</i>\u00a0=\u00a0", t)
    return t


abs_tex = (OV / "resources/sections/abs.tex").read_text(encoding="utf-8")
abs_tex = re.sub(r"\\begin\{spacing\}\{[^}]*\}|\\end\{spacing\}|\\noindent|\\newpage", "", abs_tex)
print("<!-- ABSTRACT -->")
print(f"<p>{tex2html(abs_tex)}</p>")
for i in range(1, 6):
    src = (OV / f"resources/latex/figures/figure{i}.tex").read_text(encoding="utf-8")
    cap = re.search(r"\\caption\{(.*)\}\s*\\label", src, re.S).group(1)
    print(f"<!-- FIGURE {i} -->")
    print(tex2html(cap))
print("<!-- LABELS -->")
for k in sorted(labels):
    if k.startswith(("supptable", "fig:ed")):
        print(k, labels[k])
