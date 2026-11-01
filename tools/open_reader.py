#!/usr/bin/env python3
"""Muse Spark Open reads every kept cell of a visit, and its visit share is audited against the human one.
Question, measures and verdict rule are frozen in docs/OPEN_READER.md.
Run: uv run python tools/open_reader.py pilot | dev | analyse  [--max-usd 8] [--workers 6]
Human labels are never sent. Every call is cached, so a repeat costs nothing.
"""
import argparse, json, os, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
os.environ.setdefault("OPEN_REASONING_EFFORT", "low")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import numpy as np
import pandas as pd
from scipy import stats
import meta_api, rater_spark, server

T = ROOT / "data" / "tables"
CELLS = T / "open_reader_cells.csv"
PROTOCOL = 7  # repeat index that keeps this protocol's cache entries apart from earlier runs
PRICE_IN, PRICE_OUT = 1.25 / 1e6, 4.25 / 1e6


def kept():
    f = pd.read_csv(T / "cell_features_M10.csv", dtype={"date": str})
    return f[f.shape_code != 0].reset_index(drop=True)


def frame(r):
    pngs, _ = rater_spark.cell_frame_pngs(r.patient, r.date, int(r.cell))
    return pngs[len(pngs) // 2] if pngs else None


def read_one(r, png):
    out = meta_api.baseten_rater([png], repeat=PROTOCOL)
    rt = out.get("rater") or {}
    u = out.get("usage") or {}
    return {"patient": r.patient, "date": r.date, "visit": r.visit, "cell": int(r.cell), "human": int(r.health), "status": out.get("status"),
            "spiculated": rt.get("spiculated"), "confidence": rt.get("confidence"), "image_quality": rt.get("image_quality"),
            "prompt_tokens": u.get("prompt_tokens", 0), "completion_tokens": u.get("completion_tokens", 0), "cache": out.get("_cache"), "detail": (out.get("detail") or "")[:120]}


def cost(rows):
    return sum(r["prompt_tokens"] * PRICE_IN + r["completion_tokens"] * PRICE_OUT for r in rows if r["cache"] == "miss")


def read(cells, max_usd, workers):
    rows, t0 = [], time.time()
    work = [(r, frame(r)) for r in cells.itertuples()]
    missing = [r for r, p in work if p is None]
    work = [(r, p) for r, p in work if p is not None]
    print(f"cells to read {len(work)}, no frame {len(missing)}", flush=True)
    with ThreadPoolExecutor(workers) as ex:
        pending = iter(work); live = set(); stop = False
        while True:
            while not stop and len(live) < workers:
                n = next(pending, None)
                if n is None: break
                live.add(ex.submit(read_one, *n))
            if not live: break
            done = next(as_completed(live)); live.remove(done)
            rows.append(done.result())
            if len(rows) % 100 == 0:
                print(f"{len(rows)} read, ${cost(rows):.3f}, {time.time() - t0:.0f}s, blocked {sum(r['status'] != 'OK' for r in rows)}", flush=True)
            if cost(rows) >= max_usd:
                stop = True; print(f"STOP: cost cap ${max_usd} reached", flush=True)
    print(f"done {len(rows)}: ${cost(rows):.3f}, {time.time() - t0:.0f}s", flush=True)
    return pd.DataFrame(rows)


def merge_save(df):
    if CELLS.exists():
        old = pd.read_csv(CELLS, dtype={"date": str})
        df = pd.concat([old, df]).drop_duplicates(["patient", "date", "cell"], keep="last")
    df.sort_values(["patient", "date", "cell"]).to_csv(CELLS, index=False)
    return df


def report_pilot(df):
    ok = df[df.status == "OK"]
    miss = df[df.cache == "miss"]
    print("status:", df.status.value_counts().to_dict(), "| answers:", ok.spiculated.value_counts().to_dict(), "| quality:", ok.image_quality.value_counts().to_dict())
    if len(miss):
        per = cost(miss.to_dict("records")) / len(miss)
        print(f"per call: ${per:.5f}, tokens in {miss.prompt_tokens.mean():.0f}, out {miss.completion_tokens.mean():.0f}. All 1,944 cells: about ${per * 1944:.2f}")


def analyse():
    df = pd.read_csv(CELLS, dtype={"date": str})
    ok = df[(df.status == "OK")]
    rated = ok[ok.spiculated.isin(["yes", "no"])]
    y, p = rated.human.to_numpy(), (rated.spiculated == "yes").astype(int).to_numpy()
    cell = server.kappa_ac1(list(y), list(p))
    g = rated.groupby(["patient", "date", "visit"], sort=True)
    v = pd.DataFrame({"human": g.human.mean(), "ai": g.spiculated.apply(lambda s: float((s == "yes").mean())), "cells": g.size()}).reset_index()
    tot = ok.groupby(["patient", "date", "visit"], sort=True)
    v = v.merge(pd.DataFrame({"cannot_tell": tot.spiculated.apply(lambda s: float((s == "cannot_tell").mean())),
                              "poor": tot.image_quality.apply(lambda s: float((s == "poor").mean()))}).reset_index())
    pv = pd.read_csv(T / "per_visit_adjusted_v3.csv", dtype={"date": str})[["patient", "date", "skip_rate"]]
    v = v.merge(pv, how="left")
    v["week"] = v.visit.str.rstrip("w").astype(int)
    v = v.sort_values(["patient", "week"]).reset_index(drop=True)
    c = v.assign(h=v.human - v.groupby("patient").human.transform("mean"), a=v.ai - v.groupby("patient").ai.transform("mean"))
    rho_within = float(stats.spearmanr(c.a, c.h).statistic)
    rng = np.random.default_rng(20261101); boots = []
    for _ in range(2000):
        i = rng.integers(0, len(c), len(c))
        if c.a.iloc[i].nunique() > 2: boots.append(float(stats.spearmanr(c.a.iloc[i], c.h.iloc[i]).statistic))
    # leave one patient out calibration
    pred = np.zeros(len(v))
    for pt in v.patient.unique():
        tr, te = v[v.patient != pt], v[v.patient == pt]
        b, a = np.polyfit(tr.ai, tr.human, 1)
        pred[te.index] = a + b * te.ai
    v["ai_calibrated"] = pred
    mae = float(np.abs(v.ai_calibrated - v.human).mean())
    mae_raw = float(np.abs(v.ai - v.human).mean())
    moves = same = 0
    for _pt, g2 in v.groupby("patient"):
        g2 = g2.reset_index(drop=True)
        for i in range(len(g2) - 1):
            dh, da = g2.human[i + 1] - g2.human[i], g2.ai[i + 1] - g2.ai[i]
            if abs(dh) >= .05:
                moves += 1; same += np.sign(dh) == np.sign(da)
    q = v.dropna(subset=["skip_rate"])
    rho_q = float(stats.spearmanr(q.poor, q.skip_rate).statistic)
    usable = bool(rho_within >= .5 and mae <= 8 / 100)
    s = {"cells_read": int(len(ok)), "cells_rated": int(len(rated)), "cannot_tell_share": round(float((ok.spiculated == "cannot_tell").mean()), 3),
         "said_spiky_share": round(float(p.mean()), 3), "human_spiky_share": round(float(y.mean()), 3), "cell_agreement": cell["agreement"], "cell_ac1": cell["ac1"],
         "visits": int(len(v)), "within_patient_spearman": round(rho_within, 3), "within_patient_spearman_ci95": [round(float(x), 3) for x in np.percentile(boots, [2.5, 97.5])],
         "calibrated_mae_points": round(mae * 100, 2), "raw_mae_points": round(mae_raw * 100, 2), "direction_same": int(same), "direction_pairs": int(moves),
         "quality_vs_unreadable_spearman": round(rho_q, 3), "verdict": "usable as triage reader" if usable else "not usable as a reader",
         "new_call_cost_usd": round(cost(df.to_dict("records")), 3)}
    v.to_csv(T / "open_reader_visits.csv", index=False)
    (T / "open_reader_summary.json").write_text(json.dumps(s, indent=1), encoding="utf-8")
    print(json.dumps(s, indent=1))
    print(v[["patient", "visit", "cells", "human", "ai", "ai_calibrated", "cannot_tell", "poor", "skip_rate"]].round(3).to_string(index=False))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["pilot", "dev", "analyse"])
    ap.add_argument("--max-usd", type=float, default=8.0)
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    if a.step == "analyse": return analyse()
    cells = kept()
    if a.step == "pilot":
        cells = cells.sample(n=40, random_state=20261101)
        df = read(cells, min(a.max_usd, 1.0), min(a.workers, 4))
        merge_save(df); report_pilot(df)
    else:
        df = read(cells, a.max_usd, a.workers)
        merge_save(df); report_pilot(df); analyse()


if __name__ == "__main__":
    main()
