#!/usr/bin/env python3
"""Simulation validation of the v3 decision rule (no API calls).
Null: for every visit with >= 8 runs, split runs randomly in half 1,000 times
(true change = 0) and measure the false "exceeds" rate of three rules:
 (a) naive binomial interval on pooled cell counts,
 (b) run-cluster bootstrap without flow adjustment,
 (c) run-cluster bootstrap with GLM logit flow adjustment (= the final v3 rule).
Power: add +0.05 / +0.10 to one half by resampling cell labels, measure detection.
QC sensitivity: v3 pair decisions under skip-rate thresholds 0.20 / 0.25 / 0.30.
Run in the foreground: uv run python src/simulate_rcv.py
Outputs: data/tables/simulation_rcv.json (tables also printed).
"""
import json, sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).parent))
import step4b_model

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "tables"
SEED, SPLITS, B = 20261026, 1000, 200


def boot_means(frac, n, rng):
    idx = rng.integers(0, len(frac), (B, len(frac)))
    return (frac[idx] * n[idx]).sum(axis=1) / n[idx].sum(axis=1)


def boot_ci_excludes_zero(frac_a, n_a, frac_b, n_b, rng):
    """The deployed v3 rule form: |delta| > t(0.975, df=runs_a+runs_b-2) *
    sqrt(var_a + var_b), cluster-bootstrap variances (cf. step4b RCV). The normal
    1.96 variant is also tracked in the null table footnote of STATS_VALIDATION."""
    from scipy import stats as _ss
    ma, mb = boot_means(frac_a, n_a, rng), boot_means(frac_b, n_b, rng)
    delta = float(np.average(frac_a, weights=n_a) - np.average(frac_b, weights=n_b))
    mult = float(_ss.t.ppf(0.975, max(len(frac_a) + len(frac_b) - 2, 1)))
    return abs(delta) > mult * np.sqrt(ma.var(ddof=1) + mb.var(ddof=1))


def naive_exceeds(frac_a, n_a, frac_b, n_b):
    pa, pb = np.average(frac_a, weights=n_a), np.average(frac_b, weights=n_b)
    na, nb = n_a.sum(), n_b.sum()
    p = (pa * na + pb * nb) / (na + nb)
    se = np.sqrt(max(p * (1 - p), 1e-12) * (1 / na + 1 / nb))
    return abs(pa - pb) / se > 1.96


def main():
    runs = pd.read_csv(OUT / "per_run.csv").dropna(subset=["frac_health1"]).copy()
    runs = step4b_model.flow_adjust_runs(runs)  # adds frac_adj via the v3 GLM
    rng = np.random.default_rng(SEED)
    visits = [(k, g) for k, g in runs.groupby(["patient", "visit"]) if len(g) >= 8]
    print(f"visits with >=8 runs: {len(visits)}; splits per visit: {SPLITS}; bootstrap B={B}")
    rules = ["naive_binomial", "bootstrap_raw", "bootstrap_flowadj"]
    null_hits, power_hits, total = {r: 0 for r in rules}, {d: {r: 0 for r in rules} for d in (0.05, 0.10)}, 0
    for (patient, visit), g in visits:
        frac, fadj, n = g.frac_health1.to_numpy(), g.frac_adj.to_numpy(), g.n_kept.to_numpy(dtype=float)
        m = len(g)
        for _ in range(SPLITS):
            perm = rng.permutation(m); A, Bx = perm[: m // 2], perm[m // 2:]
            total += 1
            if naive_exceeds(frac[A], n[A], frac[Bx], n[Bx]): null_hits["naive_binomial"] += 1
            if boot_ci_excludes_zero(frac[A], n[A], frac[Bx], n[Bx], rng): null_hits["bootstrap_raw"] += 1
            if boot_ci_excludes_zero(fadj[A], n[A], fadj[Bx], n[Bx], rng): null_hits["bootstrap_flowadj"] += 1
            for delta in (0.05, 0.10):
                k_new = rng.binomial(n[Bx].astype(int), np.clip(frac[Bx] + delta, 0, 1))
                frac_b2 = k_new / n[Bx]
                # flow-adjust the resampled fractions with the same per-run logit shifts
                shift = np.log(fadj[Bx] / (1 - fadj[Bx])) - np.log(np.clip(frac[Bx], 1e-6, 1 - 1e-6) / (1 - np.clip(frac[Bx], 1e-6, 1 - 1e-6)))
                p2 = np.clip(frac_b2, 1e-6, 1 - 1e-6)
                fadj_b2 = 1 / (1 + np.exp(-(np.log(p2 / (1 - p2)) + shift)))
                if naive_exceeds(frac[A], n[A], frac_b2, n[Bx]): power_hits[delta]["naive_binomial"] += 1
                if boot_ci_excludes_zero(frac[A], n[A], frac_b2, n[Bx], rng): power_hits[delta]["bootstrap_raw"] += 1
                if boot_ci_excludes_zero(fadj[A], n[A], fadj_b2, n[Bx], rng): power_hits[delta]["bootstrap_flowadj"] += 1
        print(f" {patient} {visit}: {m} runs done", flush=True)
    null_rates = {r: round(null_hits[r] / total, 4) for r in rules}
    power_rates = {str(d): {r: round(power_hits[d][r] / total, 4) for r in rules} for d in (0.05, 0.10)}
    print(f"\nNULL false-exceed rates over {total} splits: {null_rates}")
    print(f"POWER detection rates: {power_rates}")
    # QC sensitivity on v3 decisions
    visits_qc = pd.read_csv(OUT / "per_visit_adjusted_v3.csv")
    dec3 = pd.read_csv(OUT / "visit_pairs_decisions_v3.csv")
    vmap = {(r.patient, r.visit): r for r in visits_qc.itertuples()}
    qc_rows = {}
    for thr in (0.20, 0.25, 0.30):
        counts = {"exceeds_RCV": 0, "within_RCV": 0, "indeterminate_QC": 0}
        for r in dec3.to_dict("records"):
            a, b = vmap[(r["patient"], r["from"])], vmap[(r["patient"], r["to"])]
            qc = a.skip_rate > thr or b.skip_rate > thr or a.n_kept < 500 or b.n_kept < 500
            d = "indeterminate_QC" if qc else ("exceeds_RCV" if abs(r["delta_adj"]) > r["RCV95"] else "within_RCV")
            counts[d] += 1
        qc_rows[str(thr)] = counts
    print(f"QC sensitivity (decision counts by skip threshold): {qc_rows}")
    out = {"n_visits": len(visits), "splits_per_visit": SPLITS, "bootstrap_B": B, "total_splits": total,
           "null_false_exceed_rate": null_rates, "power_detection_rate": power_rates, "qc_sensitivity": qc_rows}
    (OUT / "simulation_rcv.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print("wrote data/tables/simulation_rcv.json")


if __name__ == "__main__":
    main()
