#!/usr/bin/env python3
"""Step 3 check: do contour roughness / convexity (solidity) features improve LOPO kappa for `health`?
Features per frame from pickle Contours (x,y arrays): shoelace area, perimeter, convex-hull area.
roughness = perimeter / (2*sqrt(pi*area)) (1.0 = circle); solidity = area / hull_area.
Run: uv run python src/step3_contour_check.py
"""
import re, sys
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import balanced_accuracy_score, cohen_kappa_score
sys.path.insert(0, str(Path(__file__).parent))
from step2_analysis import RestrictedUnpickler

ROOT = Path(__file__).resolve().parent.parent
DEV = ROOT / "data" / "dev"

def hull_area(pts):
    p = sorted(set(map(tuple, pts)))
    if len(p) < 3: return 0.0
    def cross(o, a, b): return (a[0]-o[0])*(b[1]-o[1]) - (a[1]-o[1])*(b[0]-o[0])
    lower = []
    for pt in p:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], pt) <= 0: lower.pop()
        lower.append(pt)
    upper = []
    for pt in reversed(p):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], pt) <= 0: upper.pop()
        upper.append(pt)
    hull = lower[:-1] + upper[:-1]
    return abs(sum(hull[i][0]*hull[(i+1) % len(hull)][1] - hull[(i+1) % len(hull)][0]*hull[i][1] for i in range(len(hull)))) / 2

def frame_feats(contour):
    try:
        pts = np.asarray(contour, dtype=float)
    except Exception:
        return None
    if pts.ndim != 2 or pts.shape[0] < 3 or pts.shape[1] != 2: return None
    x, y = pts[:, 0], pts[:, 1]
    area = abs(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y)) / 2
    per = float(np.sum(np.hypot(np.diff(np.append(x, x[0])), np.diff(np.append(y, y[0])))))
    if area <= 0: return None
    ha = hull_area(pts)
    return per / (2 * np.sqrt(np.pi * area)), (area / ha if ha > 0 else np.nan)

def main():
    base = pd.read_csv(ROOT / "data" / "tables" / "cell_features_M10.csv")
    extra = {}
    for pkl in sorted(DEV.rglob("*Offline__M10_results.p")):
        m = re.match(r"(P\d)__(\d{8})_P\d\(([^)]+)\)__", pkl.name)
        if not m: continue
        patient, date, visit = m.groups()
        with open(pkl, "rb") as fh: obj = RestrictedUnpickler(fh, encoding="latin1").load()
        for i, cell_contours in enumerate(obj["Contours"]):
            vals = [frame_feats(c) for c in cell_contours]
            vals = [v for v in vals if v]
            if not vals: continue
            r = np.array([v[0] for v in vals]); s = np.array([v[1] for v in vals])
            extra[(patient, date, i)] = (float(np.nanmean(r)), float(np.nanstd(r)), float(np.nanmean(s)), float(np.nanstd(s)))
    base["rough_mean"] = [extra.get((r.patient, str(r.date), r.cell), (np.nan,)*4)[0] for r in base.itertuples()]
    base["rough_std"] = [extra.get((r.patient, str(r.date), r.cell), (np.nan,)*4)[1] for r in base.itertuples()]
    base["solid_mean"] = [extra.get((r.patient, str(r.date), r.cell), (np.nan,)*4)[2] for r in base.itertuples()]
    base["solid_std"] = [extra.get((r.patient, str(r.date), r.cell), (np.nan,)*4)[3] for r in base.itertuples()]
    d = base[base.shape_code != 0].dropna().copy()
    print(f"cells with contour feats: {len(d)}")
    for name, feats in [("BASE (area/circ/axis/frames)", ["area_mean", "area_std", "circ_mean", "circ_std", "axis_ratio", "n_frames"]),
                        ("BASE+CONTOUR (rough/solid)", ["area_mean", "area_std", "circ_mean", "circ_std", "axis_ratio", "n_frames", "rough_mean", "rough_std", "solid_mean", "solid_std"])]:
        kaps, accs = [], []
        for test_p in sorted(d.patient.unique()):
            tr, te = d[d.patient != test_p], d[d.patient == test_p]
            clf = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000, class_weight="balanced"))
            clf.fit(tr[feats], tr.health); pred = clf.predict(te[feats])
            kaps.append(cohen_kappa_score(te.health, pred)); accs.append(balanced_accuracy_score(te.health, pred))
        print(f"{name}: LOPO kappa per patient={np.round(kaps,3)} mean={np.mean(kaps):.3f} | bal_acc mean={np.mean(accs):.3f}")

if __name__ == "__main__":
    main()
