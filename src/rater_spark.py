#!/usr/bin/env python3
"""Structured muse-spark-1.3 second-rater protocol (replaces the deleted keyword heuristic).

Sample: 80 queue cells (40 author health=1, 40 health=0, spread over P1/P2/P4, seed 42).
Input per cell: quarter/middle/three-quarter track frames as separate image parts
(upscaled 4x nearest-neighbour); frames not extracted locally are skipped and the
sent count is recorded. 20 cells are rated a second time (repeat=1) for intra-rater
agreement. Every call is cached in data/api_cache/ (repeat index in the key);
--max-new-calls aborts before exceeding the budget. Author labels are NEVER sent.
Run: uv run python src/rater_spark.py [--max-new-calls 100]
Outputs: data/tables/rater_spark.csv, docs/RATERS.md, docs/media/rater_example_*.png
"""
import argparse, json, sys
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.metrics import cohen_kappa_score
sys.path.insert(0, str(Path(__file__).parent))
import meta_api, server
from step3b_pixel_model import decode_gray_png

ROOT = Path(__file__).resolve().parent.parent
TABLES, DOCS = ROOT / "data" / "tables", ROOT / "docs"


def stratified_sample(n_per_class=40):
    q = pd.read_csv(TABLES / "adjudication_queue.csv")
    picks = []
    for health in (0, 1):
        sub = q[q.health == health]
        frac = sub.patient.value_counts(normalize=True)
        alloc = {p: max(2, int(round(n_per_class * f))) for p, f in frac.items()}
        while sum(alloc.values()) > n_per_class: alloc[max(alloc, key=alloc.get)] -= 1
        while sum(alloc.values()) < n_per_class: alloc[min(alloc, key=alloc.get)] += 1
        for p, k in alloc.items():
            g = sub[sub.patient == p]
            picks.append(g.sample(n=min(k, len(g)), random_state=42))
    return pd.concat(picks).sort_values(["health", "patient"]).reset_index(drop=True)


def cell_frame_pngs(patient, date, cell):
    """(png_list_upscaled, track_len): quarter/mid/three-quarter crops for frames extracted locally."""
    obj = server.load_pickle(patient, date)
    if obj is None or cell >= len(obj["Frames"]): return [], 0
    frames = np.asarray(obj["Frames"][cell]); track = len(frames)
    idxs = sorted({track // 4, track // 2, (3 * track) // 4})
    out = []
    for idx in idxs:
        frame_no = int(frames[idx]); pos_x = float(np.asarray(obj["pos_x"][cell])[idx])
        fdir = ROOT / "data" / "frames" / f"{patient}_{date}_M10"
        raw_path, meta_path = fdir / f"frame_{frame_no}.raw", fdir / f"frame_{frame_no}.json"
        if not raw_path.exists(): continue
        meta = json.loads(meta_path.read_text()); w, h = int(meta["width"]), int(meta["height"])
        img = np.frombuffer(raw_path.read_bytes(), dtype=np.uint8)
        if img.size < w * h: continue
        img = img[:w * h].reshape(h, w)[::-1]
        x0 = int(max(0, min(w - 200, pos_x - 100)))
        crop = img[:, x0:x0 + 200]
        big = np.repeat(np.repeat(crop, 4, 0), 4, 1)
        out.append(server.png_gray(big))
    return out, track


def cat_stats(y_true, y_pred):
    """Binary kappa/AC1/PABAK via server formulas on the rated (yes/no) subset."""
    s = server.kappa_ac1(list(y_true), list(y_pred))
    return s["kappa"], s["ac1"], round(2 * s["agreement"] - 1, 3)


def boot_ci(y_true, y_pred, b=1000, seed=42):
    rng = np.random.default_rng(seed); y_true, y_pred = np.asarray(y_true), np.asarray(y_pred)
    ks, acs = [], []
    for _ in range(b):
        idx = rng.integers(0, len(y_true), len(y_true))
        if len(np.unique(y_true[idx])) < 2 or len(np.unique(y_pred[idx])) < 2: continue
        k, a, _ = cat_stats(y_true[idx], y_pred[idx]); ks.append(k); acs.append(a)
    return (round(float(np.percentile(ks, 2.5)), 3), round(float(np.percentile(ks, 97.5)), 3)), \
           (round(float(np.percentile(acs, 2.5)), 3), round(float(np.percentile(acs, 97.5)), 3))


def save_examples(df, n=6):
    import struct, zlib
    outdir = DOCS / "media"; outdir.mkdir(parents=True, exist_ok=True)
    ok = df[(df.repeat == 0) & (df.status == "OK")].copy()
    ok["npts"] = ok.spicule_points.apply(lambda s: len(json.loads(s)) if s else 0)
    chosen = pd.concat([ok[ok.spiculated == "yes"].sort_values("npts", ascending=False).head(4),
                        ok[ok.spiculated == "no"].head(1), ok[ok.spiculated == "cannot_tell"].head(1)]).head(n)
    saved = []
    for k, (_, r) in enumerate(chosen.iterrows(), 1):
        got = server.frame_png(r.patient, str(r.date), int(r.cell), crop=True)
        if got is None: continue
        png, info = got
        img = decode_gray_png(png); hh, ww = img.shape
        rgb = np.repeat(np.repeat(np.stack([img, img, img], -1).astype(float), 4, 0), 4, 1)
        for pt in json.loads(r.spicule_points or "[]"):
            if int(pt["frame"]) != max(1, (r.n_frames_sent + 1) // 2): continue  # mid sent frame ~ centre part
            cx, cy = int(pt["x"] / 1000 * ww * 4), int(pt["y"] / 1000 * hh * 4)
            for d in range(-6, 7):
                if 0 <= cy + d < rgb.shape[0] and 0 <= cx + d < rgb.shape[1]: rgb[cy + d, cx + d] = [220, 38, 38]
                if 0 <= cy + d < rgb.shape[0] and 0 <= cx - d < rgb.shape[1]: rgb[cy + d, cx - d] = [220, 38, 38]
        big = rgb.astype(np.uint8); bh, bw = big.shape[:2]
        raw = b"".join(b"\x00" + big[i].tobytes() for i in range(bh))
        def chunk(tag, data):
            c = struct.pack(">I", len(data)) + tag + data
            return c + struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff)
        data = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", bw, bh, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))
        p = outdir / f"rater_example_{k}.png"; p.write_bytes(data)
        saved.append(f"docs/media/rater_example_{k}.png ({r.patient} cell {int(r.cell)}: {r.spiculated}, author {int(r.author_health)})")
    return saved


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--max-new-calls", type=int, default=100)
    args = ap.parse_args()
    sample = stratified_sample()
    print(f"sample: {len(sample)} cells " + str(sample.groupby(['health', 'patient']).size().to_dict()))
    new_calls = [0]
    rows = []
    def run(q, repeat):
        pngs, track = cell_frame_pngs(q.patient, str(q.date), int(q.cell))
        if not pngs:
            return {"patient": q.patient, "date": str(q.date), "visit": q.visit, "cell": int(q.cell),
                    "author_health": int(q.health), "repeat": repeat, "status": "NO_FRAMES",
                    "n_frames_sent": 0, "track_frames": track}
        r = meta_api.spark_rater(pngs, repeat=repeat)
        if r.get("_cache") == "miss" and r.get("status") == "OK": new_calls[0] += 1
        if new_calls[0] > args.max_new_calls: raise SystemExit(f"BUDGET: >{args.max_new_calls} new calls; rerun to resume from cache")
        base = {"patient": q.patient, "date": str(q.date), "visit": q.visit, "cell": int(q.cell),
                "author_health": int(q.health), "repeat": repeat, "status": r.get("status"),
                "cache": r.get("_cache"), "n_frames_sent": len(pngs), "track_frames": track}
        if r.get("status") == "OK":
            rt = r["rater"]
            base.update({"spiculated": rt["spiculated"], "confidence": rt["confidence"],
                         "spicule_points": json.dumps(rt["spicule_points"]), "image_quality": rt["image_quality"],
                         "reason": rt["reason"]})
        else:
            base.update({"detail": (r.get("detail") or "")[:200]})
        print(f" r{repeat} {q.patient}/{q.date}/c{int(q.cell)} h={int(q.health)}: {base['status']} "
              f"{base.get('spiculated', '')} frames={len(pngs)} ({base['cache']})")
        return base
    for q in sample.itertuples():
        rows.append(run(q, 0))
    reps = sample.head(20)  # sorted by health/patient: 10 per class
    for q in reps.itertuples():
        rows.append(run(q, 1))
    df = pd.DataFrame(rows)
    df.to_csv(TABLES / "rater_spark.csv", index=False)
    first = df[df.repeat == 0]
    ok = first[first.status == "OK"]
    rated = ok[ok.spiculated.isin(["yes", "no"])]
    y = rated.author_health.to_numpy(); pr = (rated.spiculated == "yes").astype(int).to_numpy()
    tp = int(((y == 1) & (pr == 1)).sum()); fn = int(((y == 1) & (pr == 0)).sum())
    fp = int(((y == 0) & (pr == 1)).sum()); tn = int(((y == 0) & (pr == 0)).sum())
    kap, ac1, pabak = cat_stats(y, pr)
    (klo, khi), (alo, ahi) = boot_ci(y, pr)
    ct_share = round(float((ok.spiculated == "cannot_tell").mean()), 3) if len(ok) else None
    pts_med = {h: (float(np.median([len(json.loads(s)) for s in g.spicule_points])) if len(g) else None)
               for h, g in ok.groupby("author_health")}
    r0 = ok.set_index(["patient", "date", "cell"]).spiculated
    rep_ok = df[(df.repeat == 1) & (df.status == "OK")]
    pairs = [(r0.get((r.patient, str(r.date), int(r.cell))), r.spiculated) for r in rep_ok.itertuples()]
    pairs = [(a, b) for a, b in pairs if a is not None]
    both_rated = [(a, b) for a, b in pairs if a in ("yes", "no") and b in ("yes", "no")]
    intra = {}
    if both_rated:
        ik, ia, _ = cat_stats([1 if a == "yes" else 0 for a, _ in both_rated], [1 if b == "yes" else 0 for _, b in both_rated])
        intra = {"n_pairs": len(pairs), "n_both_rated": len(both_rated),
                 "raw_agreement_3way": round(float(np.mean([a == b for a, b in pairs])), 3),
                 "kappa": ik, "ac1": ia}
    summary = {"n_sample": int(len(first)), "n_ok": int(len(ok)), "cannot_tell_share": ct_share,
               "confusion": {"tp": tp, "fn": fn, "fp": fp, "tn": tn}, "kappa": kap, "kappa_ci95": [klo, khi],
               "ac1": ac1, "ac1_ci95": [alo, ahi], "pabak": pabak, "intra_rater": intra,
               "median_spicule_points_by_author": {str(k): v for k, v in pts_med.items()},
               "new_api_calls": int(new_calls[0])}
    examples = save_examples(df)
    summary["examples"] = examples
    (TABLES / "rater_spark_summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    ex = {}
    for label, sub in [("correct", rated.assign(pred=pr)[lambda d: d.author_health == d.pred]),
                       ("wrong", rated.assign(pred=pr)[lambda d: d.author_health != d.pred]),
                       ("cannot_tell", ok[ok.spiculated == "cannot_tell"])]:
        if len(sub): ex[label] = {"spiculated": sub.iloc[0].spiculated, "author_health": int(sub.iloc[0].author_health),
                                  "confidence": float(sub.iloc[0].confidence),
                                  "spicule_points": json.loads(sub.iloc[0].spicule_points or "[]"),
                                  "image_quality": sub.iloc[0].image_quality, "reason": sub.iloc[0].reason}
    lines = ["# Structured Second Rater — muse-spark-1.3", "",
             "Protocol replaces the deleted free-text keyword heuristic (it scored negations as affirmations). "
             "Author labels are never included in the prompt. `cannot_tell` is a separate category, never mapped to a label.", "",
             "## Prompt (exact)", "", "```", meta_api.RATER_PROMPT, "```", "",
             "## Enforced JSON schema", "", "```json", json.dumps(meta_api.RATER_SCHEMA, indent=1), "```", "",
             "Model: muse-spark-1.3, reasoning_effort=low, response_format json_schema (strict), up to 3 track frames "
             "per cell as separate image parts, each upscaled 4x nearest-neighbour. Sample: 80 queue cells "
             "(40 author health=1, 40 health=0 across P1/P2/P4, seed 42); 20 rated twice (repeat index in cache key).", "",
             f"## Results (first rating, n_ok={summary['n_ok']}/{summary['n_sample']})", "",
             f"Confusion vs author (rows author, cols rater; cannot_tell excluded): TP={tp} FN={fn} FP={fp} TN={tn}.", "",
             f"Cohen kappa {kap} (95% CI {klo}–{khi}); Gwet AC1 {ac1} (95% CI {alo}–{ahi}); PABAK {pabak}; "
             f"cannot_tell share {ct_share}.", "",
             f"Median spicule points by author health: {summary['median_spicule_points_by_author']}.", "",
             f"Intra-rater (20 repeats): {intra}.", "",
             "## Example responses", "", "```json", json.dumps(ex, indent=1), "```", "",
             f"Example crops with drawn spicule points: {examples}. Detail: data/tables/rater_spark.csv. "
             f"New API calls this run: {summary['new_api_calls']} (all cached; reruns free)."]
    (DOCS / "RATERS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
