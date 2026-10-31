#!/usr/bin/env python3
"""Cached live multi-model benchmark on real data. Spend guard: every call goes through
data/api_cache/ (repeat runs are free); --max-new-calls aborts before exceeding the cap.

Cells: stratified 30 queue cells across P1/P2/P4 (per patient, both author-health classes,
confidence-spread) -> sam-3.1 IoU vs author contour + muse-spark-1.3 visual check.
Pairs: all 21 visit pairs -> muse-spark-1.3 narrative + Baseten muse-spark-open audit parity
vs the local Checker/auditor verdict on the same signed report.

Run: uv run python src/run_live_benchmark.py [--max-new-calls 110] [--cells 30]
Outputs: data/tables/live_benchmark_cells.csv, live_benchmark_pairs.csv,
data/tables/live_benchmark_summary.json, docs/LIVE_BENCHMARK.md
"""
import argparse, json, sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).parent))
import checker, geometry, meta_api, server
from step3b_pixel_model import decode_gray_png

ROOT = Path(__file__).resolve().parent.parent
TABLES, DOCS = ROOT / "data" / "tables", ROOT / "docs"


def stratified_cells(n_total=30):
    q = pd.read_csv(TABLES / "adjudication_queue.csv")
    targets = json.loads((ROOT / "data" / "frames" / "targets.json").read_text())
    have = {(p, str(d), int(r["cell"])) for p, dd in targets.items() for d, rows in dd.items() for r in rows
            if (ROOT / "data" / "frames" / f"{p}_{d}_M10" / f"frame_{r['frame']}.raw").exists()}
    q = q[[(r.patient, str(r.date), int(r.cell)) in have for r in q.itertuples()]].copy()
    pats = sorted(q.patient.unique())
    per = {p: n_total // len(pats) for p in pats}
    for p in pats[: n_total - per[pats[0]] * len(pats)]: per[p] += 1
    picks = []
    for p in pats:
        sub = q[q.patient == p]
        want = per[p]
        chosen = []
        for health, grp in sub.groupby("health"):
            grp = grp.sort_values("confidence")
            k = max(1, round(want * len(grp) / len(sub)))
            idx = np.linspace(0, len(grp) - 1, min(k, len(grp))).round().astype(int)
            chosen.append(grp.iloc[sorted(set(idx))])
        got = pd.concat(chosen)
        if len(got) > want: got = got.sort_values("confidence").iloc[np.linspace(0, len(got) - 1, want).round().astype(int)]
        picks.append(got)
    return pd.concat(picks).sort_values(["patient", "confidence"]).reset_index(drop=True)


def save_overlays(cells_df, n=3):
    """docs/media/p03_overlay_1..n.png: crop (x4) + author contour (teal) + SAM mask (amber tint)."""
    import struct, zlib
    outdir = DOCS / "media"; outdir.mkdir(parents=True, exist_ok=True)
    saved = []
    ok = cells_df[cells_df.sam_status == "OK"].head(n)
    for k, (_, q) in enumerate(ok.iterrows(), 1):
        got = server.frame_png(q.patient, str(q.date), int(q.cell), crop=True)
        if got is None: continue
        png, info = got
        img = decode_gray_png(png); hh, ww = img.shape
        poly = info.get("contour_crop_fullres") or info["contour_crop"]
        ck = meta_api._key("sam-3.1", [{"img": __import__("hashlib").sha256(png).hexdigest(), "author": poly}], extra="responses-v2")
        entry = json.loads((meta_api.CACHE / f"{ck}.json").read_text())
        sm = (geometry.mask_from_rows(entry["mask_rows"], hh, ww) if entry.get("mask_rows")
              else geometry.mask_from_rowspans(entry.get("polygon") or [], hh, ww))
        rgb = np.stack([img, img, img], -1).astype(float)
        rgb[sm] = rgb[sm] * 0.45 + np.array([245.0, 158.0, 11.0]) * 0.55
        for x, y in poly:
            if 0 <= int(y) < hh and 0 <= int(x) < ww: rgb[int(y), int(x)] = [13.0, 200.0, 180.0]
        big = np.repeat(np.repeat(rgb.astype(np.uint8), 4, 0), 4, 1)
        bh, bw = big.shape[:2]
        raw = b"".join(b"\x00" + big[i].tobytes() for i in range(bh))
        def chunk(tag, data):
            c = struct.pack(">I", len(data)) + tag + data
            return c + struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff)
        data = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", bw, bh, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))
        p = outdir / f"p03_overlay_{k}.png"; p.write_bytes(data); saved.append(str(p.relative_to(ROOT)))
    return saved


def spicule_flag(text: str):
    # DELETED as a scoring method: the keyword heuristic scored negations ("no distinct
    # spicules") as affirmations — all 16 "present" hits were denials. Structured
    # second-rater protocol lives in src/rater_spark.py (docs/RATERS.md). Kept only as
    # a tombstone; never use free-text keywords as a label.
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cells", type=int, default=30)
    ap.add_argument("--max-new-calls", type=int, default=110)
    ap.add_argument("--dry-run", action="store_true", help="list selection + cache status, make no calls")
    args = ap.parse_args()
    cells = stratified_cells(args.cells)
    print(f"stratified cells: {len(cells)} " + str(cells.groupby(['patient', 'health']).size().to_dict()))
    new_calls = [0]
    def spend_guard(kind):
        new_calls[0] += 1
        if new_calls[0] > args.max_new_calls:
            raise SystemExit(f"SPEND GUARD: exceeded --max-new-calls={args.max_new_calls} at {kind}; rerun to resume from cache")
    cell_rows = []
    for q in cells.itertuples():
        got = server.frame_png(q.patient, str(q.date), int(q.cell), crop=True)
        if got is None:
            cell_rows.append({"patient": q.patient, "date": str(q.date), "visit": q.visit, "cell": int(q.cell),
                              "author_health": int(q.health), "pred": int(q.pred), "sam_status": "NO_FRAME"})
            continue
        png, info = got
        poly = info.get("contour_crop_fullres") or info.get("contour_crop")
        if args.dry_run:
            print(" would call SAM+Spark:", q.patient, q.date, q.cell); continue
        before = len(list(meta_api.CACHE.glob("*.json"))) if meta_api.CACHE.exists() else 0
        sam = meta_api.sam_segment(png, author_poly=poly, wh=(200, 40))
        if sam.get("_cache") == "miss": spend_guard("sam")
        spark = meta_api.spark_visual_check(png)
        if spark.get("_cache") == "miss": spend_guard("spark-visual")
        flag = None  # free-text keyword scoring deleted (invalid); see src/rater_spark.py
        # IoU + area ratio from geometry.py, recomputed here from the cached mask (never the stored number).
        iou_g, ratio_g = sam.get("iou_vs_author"), None
        if sam.get("status") == "OK" and poly:
            hh, ww = decode_gray_png(png).shape
            sm = (geometry.mask_from_rows(sam["mask_rows"], hh, ww) if sam.get("mask_rows")
                  else geometry.mask_from_rowspans(sam.get("polygon") or [], hh, ww))
            am = geometry.fill_contour(poly, hh, ww)
            iou_g = round(geometry.iou(sm, am), 3)
            ratio_g = round(geometry.area(sm) / geometry.area(am), 3) if geometry.area(am) else None
        cell_rows.append({"patient": q.patient, "date": str(q.date), "visit": q.visit, "cell": int(q.cell),
                          "author_health": int(q.health), "pred": int(q.pred), "confidence": float(q.confidence),
                          "sam_status": sam.get("status"), "sam_detail": (sam.get("detail") or "")[:200], "sam_iou": iou_g,
                          "sam_area_ratio": ratio_g,
                          "sam_mode": sam.get("prompt_mode"), "sam_cache": sam.get("_cache"),
                          "spark_status": spark.get("status"), "spark_cache": spark.get("_cache"),
                          "spark_text": (spark.get("text") or spark.get("detail") or "")[:280]})
        print(f" cell {q.patient}/{q.date}/c{q.cell}: SAM {sam.get('status')} IoU={sam.get('iou_vs_author')} ({sam.get('_cache')}) "
              f"Spark {spark.get('status')} ({spark.get('_cache')})")
    pair_rows = []
    dec = pd.read_csv(TABLES / "visit_pairs_decisions_v3.csv")
    for r in dec.to_dict("records"):
        env = checker.sign_payload(checker.build_payload(r["patient"], r["from"], r["to"]))
        payload = env["payload"]
        if args.dry_run:
            print(" would call Spark+Baseten:", payload["patient"], payload["from_visit"], payload["to_visit"]); continue
        spark = meta_api.spark_narrative(payload)
        if spark.get("_cache") == "miss": spend_guard("spark-narrative")
        narrative, nsrc = "Flow standardized change assessed against the combined noise band.", "template"
        if spark.get("status") == "OK" and spark.get("text") and not any(c.isdigit() for c in spark["text"]):
            narrative, nsrc = spark["text"].strip(), "muse-spark-1.3"
        report = checker.render_report(env, narrative)
        ok, errs = checker.verify_envelope(env)
        aok, aerrs = checker.audit_report(report, env)
        ow = meta_api.baseten_audit(report, payload)
        if ow.get("_cache") == "miss" and ow.get("status") != "BLOCKED": spend_guard("baseten")
        local_verdict = "PASS" if (ok and aok) else "BLOCK"
        ow_verdict = ow.get("status")
        pair_rows.append({"patient": payload["patient"], "from": payload["from_visit"], "to": payload["to_visit"],
                          "decision": payload["decision"], "checker_verified": bool(ok), "local_audit": local_verdict,
                          "narrative_source": nsrc, "spark_cache": spark.get("_cache"),
                          "open_weight_status": ow_verdict, "open_weight_model": ow.get("model"),
                          "open_weight_cache": ow.get("_cache"), "parity": (ow_verdict == local_verdict),
                          "open_weight_detail": (ow.get("detail") or "")[:200]})
        print(f" pair {payload['patient']} {payload['from_visit']}->{payload['to_visit']}: local={local_verdict} open={ow_verdict} parity={ow_verdict == local_verdict}")
    if args.dry_run:
        print("DRY RUN: no calls made"); return
    cdf, pdf = pd.DataFrame(cell_rows), pd.DataFrame(pair_rows)
    cdf.to_csv(TABLES / "live_benchmark_cells.csv", index=False)
    pdf.to_csv(TABLES / "live_benchmark_pairs.csv", index=False)
    ious = cdf.loc[cdf.sam_status == "OK", "sam_iou"].dropna()
    summary = {"cells_n": int(len(cdf)), "sam_ok": int((cdf.sam_status == "OK").sum()),
               "sam_iou_mean": round(float(ious.mean()), 3) if len(ious) else None,
               "sam_iou_median": round(float(ious.median()), 3) if len(ious) else None,
               "sam_iou_min": round(float(ious.min()), 3) if len(ious) else None,
               "sam_iou_max": round(float(ious.max()), 3) if len(ious) else None,
               "sam_iou_ge80_frac": round(float((ious >= 0.8).mean()), 3) if len(ious) else None,
               "spark_ok": int((cdf.spark_status == "OK").sum()),
               "sam_area_ratio_median": round(float(cdf.loc[cdf.sam_status == "OK", "sam_area_ratio"].median()), 3) if len(cdf) and "sam_area_ratio" in cdf else None,
               "pairs_n": int(len(pdf)), "parity_n": int(pdf.parity.sum()) if len(pdf) else 0,
               "new_api_calls": int(new_calls[0]),
               "models": {"sam": "sam-3.1", "cloud": "muse-spark-1.3", "open_weight": "meta-models/muse-spark-open (Baseten)"}}
    summary["overlays"] = save_overlays(cdf)
    (TABLES / "live_benchmark_summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    lines = ["# Live Multi-Model Benchmark (cached, real data)", "",
             f"Cells: {summary['cells_n']} stratified queue cells across P1/P2/P4 with real frames. "
             f"SAM 3.1 OK {summary['sam_ok']}/{summary['cells_n']}; IoU vs author contour mean {summary['sam_iou_mean']}, "
             f"median {summary['sam_iou_median']}, range {summary['sam_iou_min']}-{summary['sam_iou_max']}, "
             f"fraction >= 0.80: {summary['sam_iou_ge80_frac']}. Median SAM/author mask-area ratio: {summary['sam_area_ratio_median']}. "
             "Note: the author contour is a convex hull that can include MOG2 shadow pixels, so IoU < 1 even for a perfect mask; "
             "cached masks predate the PromptBox half-open (+1 px) fix, which applies to future calls only.", "",
             f"Muse Spark 1.3 visual check OK {summary['spark_ok']}/{summary['cells_n']} (free-text descriptions retained "
             "in the CSV only; keyword scoring of them was invalid and has been removed — structured second-rater "
             "results: docs/RATERS.md).", "",
             f"Visit pairs: {summary['pairs_n']}. Cloud narrative (muse-spark-1.3, digit-free enforced) + Checker/local audit vs "
             f"Baseten open-weight audit parity: {summary['parity_n']}/{summary['pairs_n']}.", "",
             f"New (uncached) API calls this run: {summary['new_api_calls']}. All calls cached in data/api_cache/; reruns are free. "
             "Failures, if any, are recorded as BLOCKED in the CSVs — never replaced with fabricated passes.", "",
             "Detail: data/tables/live_benchmark_cells.csv, data/tables/live_benchmark_pairs.csv. "
             "Reproduce: `uv run python src/run_live_benchmark.py` (cache hits make it $0)."]
    (DOCS / "LIVE_BENCHMARK.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=1))
    print("wrote docs/LIVE_BENCHMARK.md")


if __name__ == "__main__":
    main()
