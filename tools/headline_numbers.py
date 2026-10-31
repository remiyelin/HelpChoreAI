#!/usr/bin/env python3
"""P-22: one source of truth for every headline number.

Writes data/tables/headline_numbers.json from the canonical v3 dev tables
plus the sealed holdout tables. Every definition is stated inline; audit
expectations are compared and reported, never forced.
Run: uv run python tools/headline_numbers.py
"""
import json, re, sys
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
import step4b_model as s4
from step2_analysis import RestrictedUnpickler
from step3_contour_check import frame_feats

ROOT = Path(__file__).resolve().parent.parent
TABLES = ROOT / "data" / "tables"
DEV_DIR = ROOT / "data" / "dev"
B_BOOT, SEED_BOOT = 1000, 20261031
AUDIT = {"naive_alarms": 19, "naive_confirmed": 5, "naive_ruled_out": 4, "naive_refused": 10,
         "naive_missed": 1, "slope_dev": -0.3224, "slope_sealed": -0.3219,
         "within_visit_negative": "37 of 37", "rcv95_median": 0.0392,
         "author_solidity_sample": "all 1.000 in a 480-cell sample"}


def _visit(vis, patient, visit):
    row = vis[(vis.patient == patient) & (vis.visit == visit)]
    return row.iloc[0]


def naive_section(dev_vis, dev_dec, sealed_vis, sealed_dec):
    alarms = confirmed = ruled_out = refused = missed = 0
    for vis, dec in ((dev_vis, dev_dec), (sealed_vis, sealed_dec)):
        for r in dec.itertuples():
            a, b = _visit(vis, r.patient, r._2), _visit(vis, r.patient, r.to)
            pa, pb = float(a.frac_health1), float(b.frac_health1)
            na, nb = int(a.n_kept), int(b.n_kept)
            pooled = (pa * na + pb * nb) / (na + nb)
            band = 1.96 * np.sqrt(pooled * (1 - pooled) * (1 / na + 1 / nb))
            if abs(pb - pa) > band:
                alarms += 1
                if r.decision == "exceeds_RCV": confirmed += 1
                elif r.decision == "within_RCV": ruled_out += 1
                else: refused += 1
            elif r.decision == "exceeds_RCV":
                missed += 1
    return {"definition": "|delta_raw| > 1.96*sqrt(p_pool(1-p_pool)(1/n_a+1/n_b)) on raw visit fractions",
            "pairs_total": int(len(dev_dec) + len(sealed_dec)),
            "alarms": alarms, "confirmed": confirmed, "ruled_out": ruled_out,
            "refused": refused, "changes_naive_missed": missed}


def slope_section(runs, rng):
    clean = runs.dropna(subset=["frac_health1"]).reset_index(drop=True)
    model, _p, use_logflow, _a = s4.fit_glm(clean)
    slope = float(model.params[-1]) if use_logflow else None
    boots = []
    for _ in range(B_BOOT):
        idx = rng.integers(0, len(clean), len(clean))
        try:
            m, _p2, use2, _a2 = s4.fit_glm(clean.iloc[idx])
            if use2: boots.append(float(m.params[-1]))
        except Exception:
            continue
    lo, hi = (float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))) if boots else (None, None)
    return {"slope": slope, "bootstrap_95ci": [lo, hi], "B": B_BOOT, "seed": SEED_BOOT,
            "n_boot_ok": len(boots), "n_runs": int(len(clean))}


def phi_and_slopes(runs):
    clean = runs.dropna(subset=["frac_health1"]).copy()
    adj = s4.flow_adjust_runs(clean)
    adj_map = {(r.patient, str(r.date), r.visit): r.frac_adj for r in adj.itertuples()}
    neg = tot = 0
    phis, phis_adj = [], []
    for (patient, date, visit), g in clean.groupby(["patient", "date", "visit"]):
        if len(g) < 3: continue
        rho, _ = stats.spearmanr(g.flow_ul_s, g.frac_health1)
        tot += 1; neg += int(rho < 0)
        for series, acc in ((g.frac_health1, phis),):
            bv = (series.mean() * (1 - series.mean()) / g.n_kept).mean()
            if bv > 0 and len(g) > 1: acc.append(float(series.var(ddof=1) / bv))
        ga = adj[(adj.patient == patient) & (adj.date.astype(str) == str(date)) & (adj.visit == visit)]
        bv = (ga.frac_adj.mean() * (1 - ga.frac_adj.mean()) / ga.n_kept).mean()
        if bv > 0 and len(ga) > 1: phis_adj.append(float(ga.frac_adj.var(ddof=1) / bv))
    return {"negative": neg, "total": tot,
            "median_phi_before": float(np.median(phis)) if phis else None,
            "median_phi_after": float(np.median(phis_adj)) if phis_adj else None}


def solidity_section():
    solids = []
    if DEV_DIR.exists():
        for patient in ("P1", "P2", "P4"):
            for pkl in sorted((DEV_DIR / patient).glob("*Offline__M10_results.p")):
                with open(pkl, "rb") as fh:
                    obj = RestrictedUnpickler(fh, encoding="latin1").load()
                for cell_contours in obj["Contours"]:
                    if not cell_contours: continue
                    v = frame_feats(cell_contours[len(cell_contours) // 2])
                    if v: solids.append(float(v[1]))
    if not solids:
        return {"status": "data/dev absent", "n_cells": 0}
    s = np.array(solids)
    return {"status": "ok", "definition": "shoelace area / convex-hull area, mid frame, all dev cells",
            "n_cells": int(len(s)), "median": float(np.median(s)), "min": float(s.min()),
            "max": float(s.max()), "n_ge_0.999": int((s >= 0.999).sum())}


def main():
    dev_runs = pd.read_csv(TABLES / "per_run.csv")
    sealed_runs = pd.read_csv(TABLES / "per_run_holdout.csv")
    dev_vis = pd.read_csv(TABLES / "per_visit.csv")
    sealed_vis = pd.read_csv(TABLES / "per_visit_holdout.csv")
    dev_dec = pd.read_csv(TABLES / "visit_pairs_decisions_v3.csv")
    sealed_dec = pd.read_csv(TABLES / "sealed_results.csv")
    rng = np.random.default_rng(SEED_BOOT)
    naive = naive_section(dev_vis, dev_dec, sealed_vis, sealed_dec)
    slopes = {"dev": slope_section(dev_runs, rng), "sealed": slope_section(sealed_runs, rng)}
    wv_dev, wv_sealed = phi_and_slopes(dev_runs), phi_and_slopes(sealed_runs)
    wv_all = {"negative": wv_dev["negative"] + wv_sealed["negative"],
              "total": wv_dev["total"] + wv_sealed["total"]}
    rcv_all = pd.concat([dev_dec.RCV95, sealed_dec.RCV95])
    p1 = {}
    for visit in ("6w", "8w", "10w"):
        g = dev_runs[(dev_runs.patient == "P1") & (dev_runs.visit == visit)]
        p1[visit] = {"runs": int(len(g)), "kept_cells": int(g.n_kept.sum()),
                     "median_flow_ul_s": float(g.flow_ul_s.median())}
    p3v = sealed_vis[sealed_vis.patient == "P3"]
    out = {
        "naive_binomial_vs_frozen": naive,
        "pooled_log_flow_slope": slopes,
        "within_visit_negative_slope": {"dev": wv_dev, "sealed": wv_sealed, "all": wv_all},
        "rcv95": {"median": float(rcv_all.median()),
                  "iqr": [float(rcv_all.quantile(0.25)), float(rcv_all.quantile(0.75))],
                  "n_pairs": int(len(rcv_all))},
        "author_contour_solidity": solidity_section(),
        "P1_visits": p1,
        "P3_visit_series": {"visits": [{"visit": r.visit, "runs": int(r.runs), "n_total": int(r.n_total),
                                        "n_kept": int(r.n_kept), "skip_rate": float(r.skip_rate)}
                                       for r in p3v.itertuples()],
                            "pooled_skip_rate": float(1 - p3v.n_kept.sum() / p3v.n_total.sum())},
    }
    observed = {"naive_alarms": naive["alarms"], "naive_confirmed": naive["confirmed"],
                "naive_ruled_out": naive["ruled_out"], "naive_refused": naive["refused"],
                "naive_missed": naive["changes_naive_missed"],
                "slope_dev": round(slopes["dev"]["slope"], 4), "slope_sealed": round(slopes["sealed"]["slope"], 4),
                "within_visit_negative": f"{wv_all['negative']} of {wv_all['total']}",
                "rcv95_median": round(out["rcv95"]["median"], 4),
                "author_solidity_sample": (f"all {out['author_contour_solidity'].get('median')} over "
                                           f"{out['author_contour_solidity'].get('n_cells')} cells"
                                           if out["author_contour_solidity"].get("status") == "ok" else "data absent")}
    out["audit_expectations"] = {"expected": AUDIT, "observed": observed,
                                 "match": {k: AUDIT[k] == observed[k] for k in AUDIT}}
    dest = TABLES / "headline_numbers.json"
    dest.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=1))
    print("audit match:", out["audit_expectations"]["match"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
