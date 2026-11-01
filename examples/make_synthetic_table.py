#!/usr/bin/env python3
"""Writes examples/synthetic_other_lab.csv: SYNTHETIC data with a known answer. No patient, no real lab.

A made-up stain test on two made-up subjects. The disturbance is how long the sample waited, in minutes.
Longer waits lower the reading, the way faster flow does in the real data. Three things are planted:
  S1, visit 2 to 3: a real rise of 12 points that stays.
  S2, visit 2 to 3: no real change, but the samples waited three times longer, so the reading drops.
  S2, visit 4: a bad recording, with 40% of the items unreadable.
Run: uv run python examples/make_synthetic_table.py
"""
from pathlib import Path
import numpy as np
import pandas as pd

rng = np.random.default_rng(20261101)
SLOPE, RUNS, ITEMS = -0.32, 14, 130


def logit(p):
    return np.log(p / (1 - p))


rows = []
for subject, base in (("S1", 0.30), ("S2", 0.42)):
    for v in range(1, 6):
        p = base + (0.12 if subject == "S1" and v >= 3 else 0.0)
        wait = 10.0 * (3 if subject == "S2" and v == 3 else 1)
        bad = subject == "S2" and v == 4
        for run in range(1, RUNS + 1):
            w = wait * rng.uniform(0.5, 1.5)
            total = int(rng.normal(ITEMS, 8))
            rated = int(total * (rng.uniform(0.55, 0.65) if bad else rng.uniform(0.9, 0.98)))
            eta = logit(p) + SLOPE * np.log(w / 10) + rng.normal(0, 0.12)  # run-to-run wobble
            rows.append({"subject": subject, "visit": f"visit{v}", "visit_order": v, "run": run, "marked": int(rng.binomial(rated, 1 / (1 + np.exp(-eta)))),
                         "rated": rated, "total": total, "disturbance": round(w, 2)})
out = Path(__file__).parent / "synthetic_other_lab.csv"
pd.DataFrame(rows).to_csv(out, index=False, lineterminator="\n")
print(f"wrote {out.name}: {len(rows)} runs, synthetic")
