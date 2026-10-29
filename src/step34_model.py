#!/usr/bin/env python3
"""Step 3+4: contour classifier + adjudication queue; flow standardization + RCV/MDC95 decisions.
Run: uv run python src/step34_model.py  (env: project .venv via uv sync; UV_CACHE_DIR/TMP inside project on Windows sandbox)
Outputs: data/tables/cell_features_M10.csv, adjudication_queue.csv, visit_pairs_decisions.csv; prints summary.
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
DEV, OUT = ROOT / "data" / "dev", ROOT / "data" / "tables"
DEFORMED = {1, 2, 3, 5, 7}
REF_FLOW = 0.016

def shoelace_area(contour):
    """Polygon area of one frame contour (same quantity as cv2.contourArea on the hull)."""
    pts = np.asarray(contour, dtype=float)
    if pts.ndim != 2 or len(pts) < 3: return np.nan
    x, y = pts[:, 0], pts[:, 1]
    return float(abs(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y)) / 2)

def contour_area_mean_std(obj, i):
    """Per-cell area mean/std from contour shoelace. NOT the pickle 'Area' field: the authors'
    tracker appends Area twice per frame with 2+ cells (vendor Cell_tracking_new.py:293-294)
    and then indexes the doubled list by single-cell sort order (line 304), misaligning it."""
    vals = [shoelace_area(c) for c in obj["Contours"][i]]
    vals = [v for v in vals if np.isfinite(v)]
    if not vals: return np.nan, np.nan
    return float(np.mean(vals)), float(np.std(vals))

def load_cells():
    rows = []
    for pkl in sorted(DEV.rglob("*Offline__M10_results.p")):
        m = re.match(r"(P\d)__(\d{8})_P\d\(([^)]+)\)__", pkl.name)
        if not m: continue
        patient, date, visit = m.groups()
        res = DEV / patient / f"{patient}__{date}_{patient}({visit})__Results__results_M10_*.txt"
        res_files = list((DEV / patient).glob(f"{patient}__{date}_*__Results__results_M10_*.txt"))
        if len(res_files) != 1: print("skip ambiguous", pkl.name, len(res_files)); continue
        labels = []
        for line in res_files[0].read_text(errors="replace").splitlines():
            if not line.strip() or line.startswith("#"): continue
            q = line.split(); labels.append((int(float(q[1])), int(float(q[3]))))
        with open(pkl, "rb") as fh: obj = RestrictedUnpickler(fh, encoding="latin1").load()
        n = min(len(labels), len(obj["Frames"]))
        for i in range(n):
            def ms(k):
                a = np.asarray(obj[k][i], dtype=float); return float(np.nanmean(a)), float(np.nanstd(a))
            am, asd = contour_area_mean_std(obj, i); cm, csd = ms("circularity")
            xm, _ = ms("x_ax"); ym, _ = ms("y_ax")
            s, h = labels[i]
            rows.append({"patient": patient, "date": date, "visit": visit, "cell": i, "shape_code": s, "health": h,
                         "area_mean": am, "area_std": asd, "circ_mean": cm, "circ_std": csd,
                         "axis_ratio": (xm / ym if ym else np.nan), "n_frames": len(obj["Frames"][i])})
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "cell_features_M10.csv", index=False)
    return df

def step3(df):
    d = df[df.shape_code != 0].copy()
    feats = ["area_mean", "area_std", "circ_mean", "circ_std", "axis_ratio", "n_frames"]
    print(f"STEP3 cells kept={len(d)} from M10 pickles; patients={sorted(d.patient.unique())}")
    queues = []
    for target in ["health"]:
        y_all, p_all, prob_all = [], [], []
        for test_p in sorted(d.patient.unique()):
            tr, te = d[d.patient != test_p], d[d.patient == test_p]
            if te.empty or tr[target].nunique() < 2: continue
            clf = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000, class_weight="balanced"))
            clf.fit(tr[feats], tr[target]); prob = clf.predict_proba(te[feats]).max(axis=1); pred = clf.predict(te[feats])
            print(f" LOPO test={test_p} target={target} bal_acc={balanced_accuracy_score(te[target], pred):.3f} kappa_vs_author={cohen_kappa_score(te[target], pred):.3f} n={len(te)}")
            q = te[["patient", "date", "visit", "cell", target]].copy(); q["pred"] = pred; q["confidence"] = prob
            queues.append(q)
        queue = pd.concat(queues).sort_values("confidence")
        thr = queue.confidence.quantile(0.20)
        queue["queue_reason"] = np.where(queue.confidence <= thr, "low_confidence_bottom20", "")
        queue.loc[queue.pred != queue.health, "queue_reason"] += "|disagrees_with_author"
        queue = queue[queue.queue_reason != ""]
        queue.to_csv(OUT / "adjudication_queue.csv", index=False)
        err = float((pd.concat(queues).pred != pd.concat(queues).health).mean())
        print(f" adjudication queue rows={len(queue)} (bottom-20% confidence + disagreements); LOPO label disagreement={err:.3f}")
        return err

def step4(label_err):
    runs = pd.read_csv(OUT / "per_run.csv").dropna(subset=["frac_health1"])
    # Expand runs to Bernoulli rows for flow model (counts only; flow is run-level)
    X, y, w_patient = [], [], []
    for _, r in runs.iterrows():
        k, n = int(round(r.frac_health1 * r.n_kept)), int(r.n_kept)
        X += [[r.flow_ul_s, r.flow_ul_s ** 2]] * n; y += [1] * k + [0] * (n - k)
    X, y = np.array(X), np.array(y)
    clf = LogisticRegression(max_iter=1000).fit(X, y)
    print(f"STEP4 flow model logit(health) ~ flow+flow^2 coef={clf.coef_[0]} intercept={clf.intercept_[0]:.3f} (ref flow {REF_FLOW})")
    def adj_frac(g):
        xx = np.column_stack([np.full(len(g), REF_FLOW), np.full(len(g), REF_FLOW ** 2)])
        # per-run predicted probability at ref flow, weighted by kept cells (flow only; patient effect via raw offset)
        pred_ref = clf.predict_proba(xx)[:, 1][0]
        raw_at_flow = clf.predict_proba(np.column_stack([g.flow_ul_s, g.flow_ul_s ** 2]))[:, 1]
        ratio = pred_ref / raw_at_flow.clip(1e-6)
        return float(np.average((g.frac_health1 * ratio).clip(0, 1), weights=g.n_kept)), float(pred_ref)
    visit_rows = pd.read_csv(OUT / "per_visit.csv")
    adj = {}
    for (patient, date), g in runs.groupby(["patient", "date"]):
        a, _ = adj_frac(g); adj[(patient, str(date))] = a
    visit_rows["frac_health1_adj"] = [adj.get((r.patient, str(r.date)), np.nan) for r in visit_rows.itertuples()]
    # Residual overdispersion after flow model, per patient (run level)
    runs["pred_flow"] = clf.predict_proba(np.column_stack([runs.flow_ul_s, runs.flow_ul_s ** 2]))[:, 1]
    phi_by_patient = {}
    for patient, g in runs.groupby("patient"):
        resid_var = ((g.frac_health1 - g.pred_flow) ** 2).mean()
        binom_var = (g.pred_flow * (1 - g.pred_flow) / g.n_kept).mean()
        phi_by_patient[patient] = float(max(1.0, resid_var / binom_var)) if binom_var > 0 else 1.0
    print(" residual phi by patient:", {k: round(v, 2) for k, v in phi_by_patient.items()})
    out = []
    for patient, g in visit_rows.sort_values("date").groupby("patient"):
        g = g.reset_index(drop=True)
        for i in range(len(g) - 1):
            a, b = g.iloc[i], g.iloc[i + 1]
            def var(p, n, phi): return phi * p * (1 - p) / n + label_err * (1 - label_err) / n
            va = var(a.frac_health1_adj, a.n_kept, phi_by_patient[patient]); vb = var(b.frac_health1_adj, b.n_kept, phi_by_patient[patient])
            rcv = 1.96 * np.sqrt(va + vb)
            raw_rcv = 1.96 * np.sqrt(a.frac_health1 * (1 - a.frac_health1) / a.n_kept + b.frac_health1 * (1 - b.frac_health1) / b.n_kept)
            qc = (a.skip_rate > 0.25) or (b.skip_rate > 0.25) or (a.n_kept < 500) or (b.n_kept < 500)
            delta_adj, delta_raw = b.frac_health1_adj - a.frac_health1_adj, b.frac_health1 - a.frac_health1
            decision = "indeterminate_QC" if qc else ("exceeds_RCV" if abs(delta_adj) > rcv else "within_RCV")
            out.append({"patient": patient, "from": a.visit, "to": b.visit, "delta_raw": round(delta_raw, 4),
                        "delta_adj": round(delta_adj, 4), "RCV95": round(rcv, 4),
                        "raw_binomial_only_exceeds": bool(abs(delta_raw) > raw_rcv), "decision": decision})
    dec = pd.DataFrame(out); dec.to_csv(OUT / "visit_pairs_decisions.csv", index=False)
    print(dec.to_string(index=False))
    print(f"\nSUMMARY pairs={len(dec)} raw-binomial-exceeds={int(dec.raw_binomial_only_exceeds.sum())} "
          f"after flow+RCV exceeds={int((dec.decision=='exceeds_RCV').sum())} within={int((dec.decision=='within_RCV').sum())} indeterminate={int((dec.decision=='indeterminate_QC').sum())}")
    visit_rows.to_csv(OUT / "per_visit_adjusted.csv", index=False)

if __name__ == "__main__":
    cells = load_cells(); err = step3(cells); step4(err if err is not None else 0.0)
