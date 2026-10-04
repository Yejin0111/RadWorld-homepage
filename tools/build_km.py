"""Build data/km.json: Kaplan-Meier curves for Figure 5e of the paper.

Reads the five cross-validation test folds of the virtual post-TACE CT survival model for each
cohort, splits patients into high and low risk exactly as the paper's plotting code does (risk score
at or above the first fold's training median), and writes the step curves, hazard ratio and log-rank
P value. Only aggregate curve points leave this script.

Check against Figure 5e: the row labelled "Number at risk" in the figure is not a count of patients
at risk. The plotting code prints round(S(t) x N // 2), the survival probability scaled by half the
cohort. So the curves are verified by recomputing exactly that, and the true numbers at risk, which
differ, are not shown on the page.

Usage: python3 tools/build_km.py
"""
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FIG5 = Path.home() / "Library/CloudStorage/Dropbox/应用/Overleaf/Gen3D/resources/codes/figure5"
GROUP = "ed256_g1_fc1_bs16_lr1e-4"
COHORTS = [  # folder, model run, name in the paper, x-axis ticks of Figure 5e, published values to check
    ("nfy", "prepost-seq-s50k", "FHHMU", [0, 20, 40, 60],
     {"n": 166, "low": [83, 56, 41, 30], "high": [83, 27, 15, 0], "hr": (2.73, 1.76, 4.25)}),
    ("zz", "prepost-seq-s80k", "FAHJU", [0, 38, 76, 115],
     {"n": 218, "low": [109, 39, 30, 30], "high": [109, 14, 11, 6], "hr": (2.45, 1.78, 3.39)}),
]


def km_curve(t, e):
    order = np.argsort(t)
    t, e = t[order], e[order]
    xs, ys, s = [], [], 1.0
    for tt in np.unique(t[e == 1]):
        d = ((t == tt) & (e == 1)).sum()
        n = (t >= tt).sum()
        s *= 1.0 - d / n
        xs.append(float(tt))
        ys.append(float(s))
    return xs, ys


def at_risk(t, ticks):
    return [int((t >= x).sum()) for x in ticks]


def surv_at(xs, ys, ticks):
    out = []
    for x in ticks:
        k = int(np.searchsorted(np.asarray(xs), x, side="right")) - 1
        out.append(1.0 if k < 0 else ys[k])
    return out


def round_half_up(v):
    return int(math.floor(v + 0.5))


def logrank_p(t, e, high):
    o1 = e1 = v = 0.0
    for tt in np.unique(t[e == 1]):
        d = ((t == tt) & (e == 1)).sum()
        n = (t >= tt).sum()
        d1 = ((t == tt) & (e == 1) & high).sum()
        n1 = ((t >= tt) & high).sum()
        if n > 1:
            e1 += d * n1 / n
            v += n1 * (n - n1) * d * (n - d) / (n * n * (n - 1))
        o1 += d1
    z = (o1 - e1) / math.sqrt(v)
    return 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))


def cox_hr(t, e, high):
    """Hazard ratio of high versus low risk, one-covariate Cox model with Breslow ties."""
    x = high.astype(float)
    order = np.argsort(t)
    t, e, x = t[order], e[order], x[order]
    uniq = np.unique(t[e == 1])
    beta = 0.0
    for _ in range(50):
        s0 = np.array([np.exp(x[t >= u] * beta).sum() for u in uniq])
        s1 = np.array([(x[t >= u] * np.exp(x[t >= u] * beta)).sum() for u in uniq])
        d = np.array([((t == u) & (e == 1)).sum() for u in uniq])
        grad = x[e == 1].sum() - (d * s1 / s0).sum()
        hess = -(d * (s1 / s0 - (s1 / s0) ** 2)).sum()  # x is binary, so S2 = S1
        step = grad / hess
        beta -= step
        if abs(step) < 1e-10:
            break
    se = math.sqrt(-1.0 / hess)
    return math.exp(beta), math.exp(beta - 1.96 * se), math.exp(beta + 1.96 * se)


out = {}
for folder, run, name, ticks, paper in COHORTS:
    d = pd.concat([pd.read_csv(FIG5 / folder / GROUP / run / f"fold{i}_{folder}_test.csv") for i in range(5)], ignore_index=True)
    threshold = float(d.loc[d["train_median"].notna(), "train_median"].iloc[0])  # as in the paper's plot_csv
    t = d["PFS"].to_numpy(float)
    e = d["event"].to_numpy(int)
    high = d["risk_score"].to_numpy(float) >= threshold
    hr = cox_hr(t, e, high)
    p = logrank_p(t, e, high)
    groups, printed, true_at_risk = {}, {}, {}
    half = {"low": len(d) // 2, "high": len(d) - len(d) // 2}  # the figure code's group sizes
    for key, mask in (("low", ~high), ("high", high)):
        xs, ys = km_curve(t[mask], e[mask])
        groups[key] = {"n": int(mask.sum()),
                       "steps": [[round(x, 2), round(y, 4)] for x, y in zip(xs, ys)],
                       "end": round(float(t[mask].max()), 2)}
        printed[key] = [round_half_up(v * half[key]) for v in surv_at(xs, ys, ticks)]
        true_at_risk[key] = at_risk(t[mask], ticks)
    problems = []
    if len(d) != paper["n"]:
        problems.append(f"N {len(d)} != {paper['n']}")
    for key in ("low", "high"):
        if printed[key] != paper[key]:
            problems.append(f"{key} curve {printed[key]} != Figure 5e {paper[key]}")
    if tuple(round(v, 2) for v in hr) != paper["hr"]:
        problems.append(f"HR {tuple(round(v, 2) for v in hr)} != {paper['hr']}")
    if not p < 1e-4:
        problems.append(f"log-rank P {p} is not below 0.0001")
    if problems:
        raise SystemExit(f"{name}: " + "; ".join(problems))
    out[name] = {"n": len(d), "ticks": ticks, "hr": [round(v, 2) for v in hr], "p": "< 0.0001", **groups}
    print(f"{name}: N={len(d)} (low {groups['low']['n']}, high {groups['high']['n']}), HR {hr[0]:.2f} "
          f"({hr[1]:.2f} to {hr[2]:.2f}), log-rank P={p:.1e}. Curves match Figure 5e. "
          f"True numbers at risk at {ticks}: low {true_at_risk['low']}, high {true_at_risk['high']} "
          f"(figure row: low {paper['low']}, high {paper['high']})")

(ROOT / "data/km.json").write_text(json.dumps(out, separators=(",", ":")))
print("wrote data/km.json", (ROOT / "data/km.json").stat().st_size, "bytes")
