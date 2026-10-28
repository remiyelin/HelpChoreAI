#!/usr/bin/env python3
"""Step 2: canonical per-run / per-visit tables + flow & noise analysis (dev P1,P2,P4).
Primary: health==1 fraction among shape!=0. Secondary: deformed fraction shapes{1,2,3,5,7} among shape!=0. QC: skip rate.
Run: uv run --with numpy,pandas,scipy python src/step2_analysis.py
"""
import io, pickle, re, sys
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parent.parent
DEV = ROOT / "data" / "dev"
OUT = ROOT / "data" / "tables"
OUT.mkdir(parents=True, exist_ok=True)
DEFORMED = {1, 2, 3, 5, 7}
NAME = re.compile(r"^(P\d)__(\d{8})_P\d\(([^)]+)\)__Results__results_M(\d+)_([\d.]+)\.txt$")

def parse_run(path: Path) -> dict:
    m = NAME.match(path.name)
    if not m:
        raise ValueError(f"unparsed filename {path.name}")
    patient, date, visit, run, flow = m.groups()
    shapes, health = [], []
    for line in path.read_text(errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        p = line.split()
        shapes.append(int(float(p[1]))); health.append(int(float(p[3])))
    s = np.array(shapes); h = np.array(health)
    kept = s != 0
    n, k = int(kept.sum()), int(len(s))
    return {"patient": patient, "date": date, "visit": visit, "run": int(run), "flow_ul_s": float(flow),
            "n_total": k, "n_kept": n, "n_skip": k - n, "skip_rate": (k - n) / k if k else np.nan,
            "n_health1": int((h[kept] == 1).sum()), "frac_health1": float((h[kept] == 1).mean()) if n else np.nan,
            "n_deformed": int(np.isin(s[kept], list(DEFORMED)).sum()),
            "frac_deformed": float(np.isin(s[kept], list(DEFORMED)).mean()) if n else np.nan,
            "mean_velocity_kept": float(np.nan) }

def main():
    rows = []
    for patient in ["P1", "P2", "P4"]:
        for f in sorted((DEV / patient).glob("*Results__results*.txt")):
            rows.append(parse_run(f))
    runs = pd.DataFrame(rows).sort_values(["patient", "date", "run"])
    runs.to_csv(OUT / "per_run.csv", index=False)
    visit = runs.groupby(["patient", "date", "visit"], as_index=False).agg(
        runs=("run", "count"), n_total=("n_total", "sum"), n_kept=("n_kept", "sum"),
        n_health1=("n_health1", "sum"), n_deformed=("n_deformed", "sum"), skip_rate=("skip_rate", "mean"),
        flow_min=("flow_ul_s", "min"), flow_max=("flow_ul_s", "max"))
    visit["frac_health1"] = visit.n_health1 / visit.n_kept
    visit["frac_deformed"] = visit.n_deformed / visit.n_kept
    visit.to_csv(OUT / "per_visit.csv", index=False)
    print(visit.to_string(index=False))
    # Overdispersion: within patient-visit, observed run variance vs mean binomial variance
    print("\nOVERDISPERSION (var_observed / var_binomial), run-level:")
    for (patient, date), g in runs.groupby(["patient", "date"]):
        if len(g) < 3: continue
        for col in ["frac_health1", "frac_deformed"]:
            gg = g.dropna(subset=[col])
            p = gg[col]; n = gg.n_kept
            binom_var = (p.mean() * (1 - p.mean()) / n).mean()
            phi = p.var(ddof=1) / binom_var if binom_var > 0 else np.nan
            print(f" {patient} {date} {col}: runs={len(g)} mean={p.mean():.3f} phi={phi:.2f}")
    # Flow effect: run-level correlation per patient (Spearman), NaN-safe
    print("\nFLOW CORRELATIONS (Spearman run-level, NaN runs excluded):")
    for patient, g in runs.groupby("patient"):
        for col in ["frac_health1", "frac_deformed", "skip_rate"]:
            gg = g.dropna(subset=[col])
            r, p = stats.spearmanr(gg.flow_ul_s, gg[col])
            print(f" {patient} flow vs {col}: rho={r:+.3f} p={p:.2g} n={len(gg)}")
    print("\nFLOW TERTILES (pooled dev runs, median fraction):")
    runs["flow_tertile"] = pd.qcut(runs.flow_ul_s, 3, labels=["low", "mid", "high"])
    print(runs.groupby(["patient", "flow_tertile"], observed=True)[["frac_health1", "frac_deformed", "skip_rate", "n_kept"]].median().round(3).to_string())
    print("\nRUN SIZE QC: runs with n_kept<30:", int((runs.n_kept < 30).sum()), "of", len(runs), "| all-skipped runs:", int((runs.n_kept == 0).sum()))
    # Hand-check target print for independent verification
    target = DEV / "P1" / "P1__20170627_P1(0w)__Results__results_M10_0.016.txt"
    r = parse_run(target)
    print("\nHANDCHECK", target.name, r)

class RestrictedUnpickler(pickle.Unpickler):
    """Numpy-only restricted unpickler for authors' Python-2 .p track files. Never raw pickle.load."""
    ALLOWED = {("numpy", "ndarray"), ("numpy.core.multiarray", "_reconstruct"), ("numpy.core.multiarray", "scalar"),
               ("numpy", "dtype"), ("numpy.dtypes", "Float64DType"), ("numpy.dtypes", "Int64DType"),
               ("builtins", "list"), ("builtins", "dict"), ("builtins", "tuple"), ("builtins", "set"),
               ("__builtin__", "list"), ("__builtin__", "dict"), ("__builtin__", "tuple")}
    def find_class(self, module, name):
        if (module, name) in self.ALLOWED or module.startswith("numpy"):
            return super().find_class(module, name)
        raise pickle.UnpicklingError(f"forbidden class {module}.{name}")

def inspect_pickle():
    p = DEV / "P1" / "P1__20170627_P1(0w)__Offline__M10_results.p"
    if not p.exists():
        print("PICKLE sample missing"); return
    try:
        with open(p, "rb") as fh:
            obj = RestrictedUnpickler(fh, encoding="latin1").load()
        print("\nPICKLE", p.name, type(obj), list(obj.keys()) if isinstance(obj, dict) else "")
        if isinstance(obj, dict):
            for k, v in obj.items():
                try: print(f"  {k}: len={len(v)} first_type={type(v[0]).__name__ if len(v) else '-'}")
                except Exception as e: print(f"  {k}: {type(v)} ({e})")
    except Exception as e:
        print("\nPICKLE restricted-load failed (expected risk, Python2 format):", type(e).__name__, e)

if __name__ == "__main__":
    main(); inspect_pickle()
