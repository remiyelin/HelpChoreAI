#!/usr/bin/env python3
"""Run the HelpChoreAI decision rule on any lab's run table. No model call, no network, no key.

  uv run python tools/audit_table.py examples/synthetic_other_lab.csv

One row per run. Required columns:
  subject      a code, never a name
  visit        a label, for example 8w
  visit_order  a number that puts the visits of a subject in order
  run          run id inside the visit
  marked       items the marker was found in
  rated        items that could be read
  total        items seen, readable or not
  disturbance  a positive number that may disturb the measurement, such as flow or waiting time.
               Put 1 in every row if nothing was recorded; then no correction is made.

The statistics are the functions frozen at git tag eval-v1 (src/step4b_model.py), called unchanged.
Research use only. Not medical advice. It says whether a change is bigger than the wobble of this
measurement. It says nothing about why, or about a patient.
"""
import argparse, hashlib, json, math, re, sys, warnings
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats as _sstats
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import step4b_model as frozen

COLUMNS = ["subject", "visit", "visit_order", "run", "marked", "rated", "total", "disturbance"]
WORDS = {"exceeds_RCV": "bigger than normal wobble", "within_RCV": "inside normal wobble", "indeterminate_QC": "no decision: recording not good enough"}


class TableError(ValueError):
    """The table cannot be audited; the message says how to fix it."""


def load(path) -> pd.DataFrame:
    df = pd.read_csv(path)
    missing = [c for c in COLUMNS if c not in df.columns]
    if missing: raise TableError(f"missing columns: {', '.join(missing)}")
    df = df[COLUMNS].copy()
    if df[COLUMNS].isna().any().any(): raise TableError("empty cells in the table; every row needs every column")
    for c in ("marked", "rated", "total", "disturbance", "visit_order"):
        if not pd.api.types.is_numeric_dtype(df[c]): raise TableError(f"column {c} must hold numbers")
    if (df.disturbance <= 0).any(): raise TableError("disturbance must be above 0; put 1 in every row if nothing was recorded")
    if ((df.marked < 0) | (df.marked > df.rated) | (df.rated > df.total)).any():
        raise TableError("each row needs 0 <= marked <= rated <= total")
    if not df.subject.astype(str).map(lambda s: bool(re.fullmatch(r"[A-Za-z0-9_-]{1,32}", s))).all():
        raise TableError("subject must be a short code with letters, digits, - or _; never a name")
    if df.duplicated(["subject", "visit", "run"]).any(): raise TableError("the same subject, visit and run appears twice")
    if df.groupby("subject").visit.nunique().max() < 2: raise TableError("no subject has two visits, so there is nothing to compare")
    return df


def audit(df, reference=None, max_unreadable=0.25, min_rated=500, unreadable_rule="pooled"):
    """Decisions for every consecutive visit pair. unreadable_rule: pooled counts every item;
    frozen is the mean over runs with readable items, as used for the pre-registered results."""
    ref = float(reference) if reference else float(df.disturbance.median())
    d = df.assign(patient=df.subject.astype(str), n_kept=df.rated.astype(int), n_total=df.total.astype(int))
    d["flow_ul_s"] = df.disturbance * frozen.REF_FLOW / ref  # puts the reference at the frozen REF_FLOW, slope unchanged
    all_rows = d.copy()
    runs = d[d.n_kept > 0].copy()
    runs["frac_health1"] = runs.marked / runs.n_kept
    runs["skip_rate"] = 1 - runs.n_kept / runs.n_total
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # a constant disturbance makes the second fit singular; it is then not used
        model, subjects, corrected, (aic0, aic1) = frozen.fit_glm(runs)
    runs = frozen.standardise(runs, model, subjects, corrected)
    rng = np.random.default_rng(frozen.SEED)
    visits = []
    for (s, order, visit), g in runs.groupby(["patient", "visit_order", "visit"]):
        boots = []
        f, n = g.frac_adj.values, g.n_kept.values
        for _ in range(frozen.B):
            idx = rng.integers(0, len(g), len(g))
            boots.append(float(np.average(f[idx], weights=n[idx])))
        every = all_rows[(all_rows.patient == s) & (all_rows.visit_order == order) & (all_rows.visit == visit)]
        visits.append({"subject": s, "visit_order": order, "visit": visit, "raw": float(g.marked.sum() / g.n_kept.sum()),
                       "adj": float(np.average(f, weights=n)), "var": float(np.var(boots, ddof=1)), "rated": int(g.n_kept.sum()), "runs": int(len(g)),
                       "unreadable": float(g.skip_rate.mean()) if unreadable_rule == "frozen" else float(1 - every.n_kept.sum() / every.n_total.sum())})
    visits = pd.DataFrame(visits).sort_values(["subject", "visit_order"])
    pairs = []
    for s, g in visits.groupby("subject"):
        g = g.reset_index(drop=True)
        for i in range(len(g) - 1):
            a, b = g.iloc[i], g.iloc[i + 1]
            band = float(_sstats.t.ppf(0.975, max(a.runs + b.runs - 2, 1))) * math.sqrt(a["var"] + b["var"])
            raw, adj = b.raw - a.raw, b.adj - a.adj
            pool = (a.raw * a.rated + b.raw * b.rated) / (a.rated + b.rated)
            naive = 1.96 * math.sqrt(pool * (1 - pool) * (1 / a.rated + 1 / b.rated))
            blocked = a.unreadable > max_unreadable or b.unreadable > max_unreadable or a.rated < min_rated or b.rated < min_rated
            d_ = "indeterminate_QC" if blocked else ("exceeds_RCV" if abs(adj) > band else "within_RCV")
            pairs.append({"subject": s, "from": a.visit, "to": b.visit, "normal_change": round(raw, 4), "normal_band": round(naive, 4),
                          "normal_says": "alarm" if abs(raw) > naive else "quiet", "corrected_change": round(adj, 4), "wobble": round(band, 4),
                          "unreadable_from": round(float(a.unreadable), 4), "unreadable_to": round(float(b.unreadable), 4),
                          "decision": d_, "meaning": WORDS[d_]})
    pairs = pd.DataFrame(pairs)
    info = {"subjects": int(visits.subject.nunique()), "visits": int(len(visits)), "runs": int(len(runs)), "pairs": int(len(pairs)),
            "reference": ref, "corrected": bool(corrected), "slope": round(float(model.params[-1]), 4) if corrected else None,
            "aic": [round(aic0, 1), round(aic1, 1)], "median_wobble": round(float(pairs.wobble.median()), 4), "median_runs": float(visits.runs.median()),
            "unreadable_rule": unreadable_rule}
    return pairs, visits, info


def runs_needed(info, target):
    """Band shrinks with the square root of the runs. An estimate, not a promise."""
    return math.ceil(info["median_runs"] * (info["median_wobble"] / target) ** 2)


def main():
    ap = argparse.ArgumentParser(description="Audit a run table with the frozen HelpChoreAI rule.")
    ap.add_argument("table")
    ap.add_argument("--reference", type=float, help="disturbance value to correct to; default the median")
    ap.add_argument("--max-unreadable", type=float, default=0.25)
    ap.add_argument("--min-rated", type=int, default=500)
    ap.add_argument("--target", type=float, default=5, help="smallest change you want to call, in points")
    ap.add_argument("--out", help="folder for decisions.csv and summary.json")
    a = ap.parse_args()
    try:
        df = load(a.table)
    except (TableError, OSError) as e:
        sys.exit(f"Cannot read this table: {e}")
    pairs, _visits, info = audit(df, a.reference, a.max_unreadable, a.min_rated)
    info["input_sha256"] = hashlib.sha256(Path(a.table).read_bytes()).hexdigest()
    info["runs_for_target"] = runs_needed(info, a.target / 100)
    print(f"{info['subjects']} subjects, {info['visits']} visits, {info['runs']} runs, {info['pairs']} visit pairs")
    print(f"Input SHA-256: {info['input_sha256']}")
    print(f"Disturbance: slope {info['slope']}, corrected to {info['reference']:g}" if info["corrected"] else "Disturbance: no clear effect, no correction made")
    print()
    for r in pairs.itertuples():
        print(f"{r.subject} {r.__getattribute__('_2')} to {r.to}: normal {r.normal_change * 100:+.1f} ({r.normal_says}), "
              f"corrected {r.corrected_change * 100:+.1f}, wobble +/-{r.wobble * 100:.1f}: {r.meaning}")
    alarms = pairs[pairs.normal_says == "alarm"]
    print(f"\nNormal reading: {len(alarms)} alarms. Confirmed {(alarms.decision == 'exceeds_RCV').sum()}, ruled out {(alarms.decision == 'within_RCV').sum()}, "
          f"no decision {(alarms.decision == 'indeterminate_QC').sum()}. Missed by the normal reading: {((pairs.normal_says == 'quiet') & (pairs.decision == 'exceeds_RCV')).sum()}.")
    print(f"Smallest change this protocol can call: about {info['median_wobble'] * 100:.1f} points. Estimated runs per visit for {a.target:g} points: {info['runs_for_target']}.")
    print("Research use only. Not medical advice.")
    if a.out:
        o = Path(a.out); o.mkdir(parents=True, exist_ok=True)
        pairs.to_csv(o / "decisions.csv", index=False)
        (o / "summary.json").write_text(json.dumps(info, indent=1), encoding="utf-8")
        print(f"Wrote {o / 'decisions.csv'} and {o / 'summary.json'}")


if __name__ == "__main__":
    main()
