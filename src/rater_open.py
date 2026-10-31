#!/usr/bin/env python3
"""P-09: open-weight second rater (meta-models/muse-spark-open via Baseten) on the P-05 sample.

Same 80 stratified cells, same upscaled frames, RATER_PROMPT and RATER_SCHEMA as rater_spark.py.
Author labels are NEVER sent. Budget: <=80 first calls + <=10 retries; reruns resume from cache.
Run: uv run python src/rater_open.py [--limit N]
Outputs: data/tables/rater_open.csv (+ printed metrics vs author and vs muse-spark-1.3).
"""
import argparse, json, sys, time
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).parent))
import meta_api
from rater_spark import stratified_sample, cell_frame_pngs, cat_stats, boot_ci

ROOT = Path(__file__).resolve().parent.parent
TABLES = ROOT / "data" / "tables"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=80)
    ap.add_argument("--max-new-calls", type=int, default=90)  # 80 first calls + at most 10 retries
    args = ap.parse_args()
    sample = stratified_sample().head(args.limit)
    print(f"sample: {len(sample)} cells " + str(sample.groupby(['health', 'patient']).size().to_dict()), flush=True)
    counters = {"new_calls": 0, "retries": 0}
    rows = []
    for q in sample.itertuples():
        pngs, track = cell_frame_pngs(q.patient, str(q.date), int(q.cell))
        base = {"patient": q.patient, "date": str(q.date), "visit": q.visit, "cell": int(q.cell),
                "author_health": int(q.health), "repeat": 0, "model": "meta-models/muse-spark-open",
                "n_frames_sent": len(pngs), "track_frames": track}
        if not pngs:
            rows.append(base | {"status": "NO_FRAMES"})
            print(f" {q.patient}/{q.date}/c{int(q.cell)} h={int(q.health)}: NO_FRAMES", flush=True)
            continue
        r = meta_api.baseten_rater(pngs, repeat=0)
        counters["new_calls"] += int(r.get("_new_calls", 0))
        counters["retries"] += max(0, int(r.get("_new_calls", 0)) - 1) if r.get("_cache") == "miss" else 0
        if counters["new_calls"] > args.max_new_calls:
            raise SystemExit(f"BUDGET: >{args.max_new_calls} new calls; rerun to resume from cache")
        base.update({"status": r.get("status"), "cache": r.get("_cache")})
        if r.get("status") == "OK":
            rt = r["rater"]
            base.update({"spiculated": rt["spiculated"], "confidence": rt["confidence"],
                         "spicule_points": json.dumps(rt["spicule_points"]),
                         "image_quality": rt["image_quality"], "reason": rt["reason"]})
        else:
            base.update({"spiculated": None, "detail": (r.get("detail") or "")[:200]})
        print(f" {q.patient}/{q.date}/c{int(q.cell)} h={int(q.health)}: {base['status']} "
              f"{base.get('spiculated') or ''} frames={len(pngs)} ({base['cache']}) new={counters['new_calls']}", flush=True)
        rows.append(base)
        if r.get("_cache") == "miss": time.sleep(0.5)
    df = pd.DataFrame(rows)
    df.to_csv(TABLES / "rater_open.csv", index=False)
    ok = df[df.status == "OK"]
    rated = ok[ok.spiculated.isin(["yes", "no"])]
    y = rated.author_health.to_numpy(); pr = (rated.spiculated == "yes").astype(int).to_numpy()
    kap, ac1, pabak = cat_stats(y, pr)
    (klo, khi), (alo, ahi) = boot_ci(y, pr) if len(rated) >= 5 else ((None, None), (None, None))
    metrics = {"n_sample": int(len(df)), "n_ok": int(len(ok)),
               "confusion": {"tp": int(((y == 1) & (pr == 1)).sum()), "fn": int(((y == 1) & (pr == 0)).sum()),
                             "fp": int(((y == 0) & (pr == 1)).sum()), "tn": int(((y == 0) & (pr == 0)).sum())},
               "kappa": kap, "kappa_ci95": [klo, khi], "ac1": ac1, "ac1_ci95": [alo, ahi], "pabak": pabak,
               "cannot_tell_share": round(float((ok.spiculated == "cannot_tell").mean()), 3) if len(ok) else None,
               "new_api_calls": counters["new_calls"], "retries": counters["retries"]}
    # Head-to-head vs cloud muse-spark-1.3 (rater_spark.csv, repeat=0)
    cloud = pd.read_csv(TABLES / "rater_spark.csv", dtype={"date": str})
    cloud = cloud[cloud.repeat == 0].set_index(["patient", "date", "cell"]).spiculated
    pairs = [(cloud.get((r.patient, str(r.date), int(r.cell))), r.spiculated)
             for r in ok.itertuples() if cloud.get((r.patient, str(r.date), int(r.cell))) is not None]
    both = [(a, b) for a, b in pairs if a in ("yes", "no") and b in ("yes", "no")]
    h2h = {"n_pairs": len(pairs), "n_both_rated": len(both),
           "raw_agreement_3way": round(float(np.mean([a == b for a, b in pairs])), 3) if pairs else None}
    if both:
        hk, ha, hp = cat_stats([1 if a == "yes" else 0 for a, _ in both],
                               [1 if b == "yes" else 0 for _, b in both])
        h2h.update({"kappa": hk, "ac1": ha, "pabak": hp})
    metrics["head_to_head_vs_spark13"] = h2h
    print(json.dumps(metrics, indent=1), flush=True)


if __name__ == "__main__":
    main()
