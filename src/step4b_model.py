#!/usr/bin/env python3
"""Step 4b: patient-intercept flow GLM + cluster-bootstrapped RCV + treatment context.
Run: uv run python src/step4b_model.py
Outputs: data/tables/visit_pairs_decisions_v2.csv, data/tables/per_visit_adjusted_v2.csv
Bootstrap: cluster = run, resampled within visit (kept-cell weighted), B=400, seed=42 (deterministic).
Treatment (authors' notebooks fig2-fig4): P1,P2,P3 dasatinib; P4,P5 lithium; first visit = day 0 (treatment start).
"""
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

ROOT = __file__.rsplit("\\", 2)[0] if "\\" in __file__ else "."
import pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "tables"
REF_FLOW, B, SEED = 0.016, 400, 42
TREATMENT = {"P1": "dasatinib", "P2": "dasatinib", "P3": "dasatinib", "P4": "lithium", "P5": "lithium"}
LABEL_ERR = 0.391  # Step 3 LOPO disagreement (proxy until double-rater kappa/AC1 exists)

def fit_glm(runs: pd.DataFrame):
    patients = sorted(runs.patient.unique())
    def feats(flow, patient):
        base = [np.full(len(flow), f) for f in []]
        cols = [flow, flow ** 2] + [(patient == p).astype(float) for p in patients[1:]]
        return np.column_stack(cols)
    X, y = [], []
    for _, r in runs.iterrows():
        n, k = int(r.n_kept), int(round(r.frac_health1 * r.n_kept))
        X.append(np.repeat(feats(np.array([r.flow_ul_s]), np.array([r.patient]))[0:1], n, axis=0))
        y += [1] * k + [0] * (n - k)
    clf = LogisticRegression(max_iter=1000).fit(np.vstack(X), np.array(y))
    return clf, patients, feats

def main():
    runs = pd.read_csv(OUT / "per_run.csv").dropna(subset=["frac_health1"]).copy()
    clf, patients, feats = fit_glm(runs)
    def pred(flow, patient):
        return float(clf.predict_proba(feats(np.array([flow]), np.array([patient])))[:, 1][0])
    # adjusted run fraction at REF_FLOW via ratio to model prediction at observed flow (patient intercept retained)
    runs["frac_adj"] = [r.frac_health1 * pred(REF_FLOW, r.patient) / max(pred(r.flow_ul_s, r.patient), 1e-6)
                        for r in runs.itertuples()]
    runs["frac_adj"] = runs.frac_adj.clip(0, 1)
    rng = np.random.default_rng(SEED)
    visit_stats = {}
    for (patient, date, visit), g in runs.groupby(["patient", "date", "visit"]):
        point = float(np.average(g.frac_adj, weights=g.n_kept))
        boots = []
        arr_f, arr_n = g.frac_adj.values, g.n_kept.values
        for _ in range(B):
            idx = rng.integers(0, len(g), len(g))
            boots.append(float(np.average(arr_f[idx], weights=arr_n[idx])))
        boot_var = float(np.var(boots, ddof=1))
        n = int(g.n_kept.sum())
        label_var = LABEL_ERR * (1 - LABEL_ERR) / n
        visit_stats[(patient, str(date))] = {"patient": patient, "date": str(date), "visit": visit,
                                             "frac_adj": point, "var": boot_var + label_var, "n_kept": n,
                                             "skip_rate": float(g.skip_rate.mean()), "boot_sd": float(np.sqrt(boot_var))}
    visits = pd.DataFrame(visit_stats.values()).sort_values(["patient", "date"])
    visits.to_csv(OUT / "per_visit_adjusted_v2.csv", index=False)
    raw_visit = pd.read_csv(OUT / "per_visit.csv")
    raw_map = {(r.patient, str(r.date)): r.frac_health1 for r in raw_visit.itertuples()}
    out = []
    for patient, g in visits.groupby("patient"):
        g = g.reset_index(drop=True)
        for i in range(len(g) - 1):
            a, b = g.iloc[i], g.iloc[i + 1]
            rcv = 1.96 * np.sqrt(a["var"] + b["var"])
            delta_adj, delta_raw = b.frac_adj - a.frac_adj, raw_map[(patient, b.date)] - raw_map[(patient, a.date)]
            qc = (a.skip_rate > 0.25) or (b.skip_rate > 0.25) or (a.n_kept < 500) or (b.n_kept < 500)
            ctx = TREATMENT[patient] + (" initiation (from day-0 baseline)" if i == 0 else " on-treatment")
            out.append({"patient": patient, "from": a.visit, "to": b.visit, "treatment": ctx,
                        "delta_raw": round(delta_raw, 4), "delta_adj": round(delta_adj, 4), "RCV95": round(rcv, 4),
                        "decision": "indeterminate_QC" if qc else ("exceeds_RCV" if abs(delta_adj) > rcv else "within_RCV")})
    dec = pd.DataFrame(out)
    dec.to_csv(OUT / "visit_pairs_decisions_v2.csv", index=False)
    print(f"GLM patients={patients} coef={np.round(clf.coef_[0], 3)} B={B} seed={SEED} ref_flow={REF_FLOW}")
    print(dec.to_string(index=False))
    print(f"\nSUMMARY v2 pairs={len(dec)} exceeds={int((dec.decision=='exceeds_RCV').sum())} "
          f"within={int((dec.decision=='within_RCV').sum())} indeterminate={int((dec.decision=='indeterminate_QC').sum())}")

if __name__ == "__main__":
    main()
