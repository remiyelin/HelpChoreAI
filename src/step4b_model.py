#!/usr/bin/env python3
"""Step 4b v3: unpenalised binomial GLM (statsmodels) on run-level counts, logit-scale
flow standardisation, cluster-bootstrapped RCV WITHOUT the label-variance term.
Run: uv run python src/step4b_model.py
Outputs: data/tables/per_visit_adjusted_v3.csv, data/tables/visit_pairs_decisions_v3.csv
(v2 tables are frozen inputs of the Checker chain and are NOT overwritten.)

Model: successes = n_health1, trials = n_kept per run; logit(p) = patient intercept
(+ b*log(flow) only if it improves AIC by > 2). Standardisation shifts each run's
observed log-odds by (eta_ref - eta_run) — no probability ratios. RCV: cluster
bootstrap (cluster = run, within visit, kept-cell weighted, B=2000, seed=20261026);
visit variance is the bootstrap variance only. The old 0.391 label-variance term
survives ONLY as the RCV95_sensitivity column (it is classifier-vs-author
disagreement, not measurement noise of the fraction, and it is also estimable
from double ratings rather than assumed).
Treatment (authors' notebooks fig2-fig4): P1,P2,P3 dasatinib; P4,P5 lithium; first visit = day 0.
"""
import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats as _sstats

import pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "tables"
REF_FLOW, B, SEED = 0.016, 2000, 20261026
TREATMENT = {"P1": "dasatinib", "P2": "dasatinib", "P3": "dasatinib", "P4": "lithium", "P5": "lithium"}
LABEL_ERR = 0.391  # sensitivity only (Step 3 LOPO disagreement); never in the RCV itself
EPS = 1e-6


def fit_glm(runs: pd.DataFrame):
    """Unpenalised binomial GLM on run counts. Returns (model, patients, use_logflow, aics)."""
    patients = sorted(runs.patient.unique())
    d = runs.copy()
    d["k"] = np.round(d.frac_health1 * d.n_kept).astype(int)
    d["nk"] = d.n_kept - d.k
    d["logflow"] = np.log(d.flow_ul_s)
    X0 = np.column_stack([(d.patient == p).astype(float) for p in patients])
    endog = d[["k", "nk"]].to_numpy(dtype=float)
    m0 = sm.GLM(endog, X0, family=sm.families.Binomial()).fit()
    X1 = np.column_stack([X0, d.logflow])
    m1 = sm.GLM(endog, X1, family=sm.families.Binomial()).fit()
    use_logflow = bool(m1.aic < m0.aic - 2)
    return (m1 if use_logflow else m0), patients, use_logflow, (float(m0.aic), float(m1.aic))


def eta(model, patients, use_logflow, flow, patient):
    """Linear predictor for (flow, patient) under the fitted GLM."""
    x = np.array([1.0 if patient == p else 0.0 for p in patients] + ([np.log(flow)] if use_logflow else []))
    return float(x @ model.params)


def standardise(runs: pd.DataFrame, model, patients, use_logflow) -> pd.DataFrame:
    """Shift each run's observed log-odds to REF_FLOW: logit(p_adj) = logit(p_obs) + eta_ref - eta_run."""
    d = runs.copy()
    p_obs = d.frac_health1.clip(EPS, 1 - EPS)
    shift = [eta(model, patients, use_logflow, REF_FLOW, r.patient) - eta(model, patients, use_logflow, r.flow_ul_s, r.patient)
             for r in d.itertuples()]
    d["frac_adj"] = 1 / (1 + np.exp(-(np.log(p_obs / (1 - p_obs)) + np.array(shift))))
    return d


def flow_adjust_runs(runs: pd.DataFrame) -> pd.DataFrame:
    """Fit the GLM and return runs with a frac_adj column (used by step4b and the simulation)."""
    model, patients, use_logflow, _ = fit_glm(runs)
    return standardise(runs, model, patients, use_logflow)


def main():
    runs = pd.read_csv(OUT / "per_run.csv").dropna(subset=["frac_health1"]).copy()
    model, patients, use_logflow, (aic0, aic1) = fit_glm(runs)
    print(f"GLM unpenalised binomial on run counts: patients={patients} use_logflow={use_logflow} "
          f"AIC patient-only={aic0:.1f} +log(flow)={aic1:.1f}")
    print(f"params={np.round(model.params, 4)} (last is log-flow slope when used); flow slope must be < 0")
    runs = standardise(runs, model, patients, use_logflow)
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
        visit_stats[(patient, str(date))] = {"patient": patient, "date": str(date), "visit": visit,
                                             "frac_adj": point, "var": boot_var, "n_kept": n, "n_runs": int(len(g)),
                                             "label_var_sens": LABEL_ERR * (1 - LABEL_ERR) / n,
                                             "skip_rate": float(g.skip_rate.mean()), "boot_sd": float(np.sqrt(boot_var))}
    visits = pd.DataFrame(visit_stats.values()).sort_values(["patient", "date"])
    visits.to_csv(OUT / "per_visit_adjusted_v3.csv", index=False)
    raw_visit = pd.read_csv(OUT / "per_visit.csv")
    raw_map = {(r.patient, str(r.date)): r.frac_health1 for r in raw_visit.itertuples()}
    out = []
    for patient, g in visits.groupby("patient"):
        g = g.reset_index(drop=True)
        for i in range(len(g) - 1):
            a, b = g.iloc[i], g.iloc[i + 1]
            # Few-cluster calibration: t multiplier with run-count df instead of 1.96
            # (simulation: normal multiplier false-exceeds at 0.084; see STATS_VALIDATION).
            mult = float(_sstats.t.ppf(0.975, max(a.n_runs + b.n_runs - 2, 1)))
            rcv = mult * np.sqrt(a["var"] + b["var"])
            rcv_sens = mult * np.sqrt(a["var"] + b["var"] + a.label_var_sens + b.label_var_sens)
            delta_adj, delta_raw = b.frac_adj - a.frac_adj, raw_map[(patient, b.date)] - raw_map[(patient, a.date)]
            qc = (a.skip_rate > 0.25) or (b.skip_rate > 0.25) or (a.n_kept < 500) or (b.n_kept < 500)
            ctx = TREATMENT[patient] + (" initiation (from day-0 baseline)" if i == 0 else " on-treatment")
            out.append({"patient": patient, "from": a.visit, "to": b.visit, "treatment": ctx,
                        "delta_raw": round(delta_raw, 4), "delta_adj": round(delta_adj, 4), "RCV95": round(rcv, 4),
                        "RCV95_sensitivity": round(rcv_sens, 4),
                        "decision": "indeterminate_QC" if qc else ("exceeds_RCV" if abs(delta_adj) > rcv else "within_RCV")})
    dec = pd.DataFrame(out)
    dec.to_csv(OUT / "visit_pairs_decisions_v3.csv", index=False)
    print(dec.to_string(index=False))
    print(f"\nSUMMARY v3 pairs={len(dec)} exceeds={int((dec.decision=='exceeds_RCV').sum())} "
          f"within={int((dec.decision=='within_RCV').sum())} indeterminate={int((dec.decision=='indeterminate_QC').sum())}")


if __name__ == "__main__":
    main()
