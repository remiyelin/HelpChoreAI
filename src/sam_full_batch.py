#!/usr/bin/env python3
"""P-06 full batch (stage 2): raw-setting SAM 3.1 box prompts on all 961 queue cells.
Reuses the pilot cache (tag pilot-v1; the 20 pilot raw cells are hits). Solidity uses
the same-grid hull (Condition 1 in DECISIONS.md) so solidity <= 1 by construction.
Checkpointed CSV every 50 cells; --max-new-calls aborts before exceeding budget
(rerun resumes from cache). Then LOPO: BASE vs BASE+SAM vs SAM-only vs author health.
Run: uv run python src/sam_full_batch.py [--max-new-calls 941]
Outputs: data/tables/sam_shape_features.csv, data/tables/sam_shape_summary.json
"""
import argparse, json, sys
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import balanced_accuracy_score, cohen_kappa_score
sys.path.insert(0, str(Path(__file__).parent))
import geometry, meta_api, server
from sam_pilot import box_prompt, pick_mask, shape_stats
from step3b_pixel_model import decode_gray_png

ROOT = Path(__file__).resolve().parent.parent
TABLES = ROOT / "data" / "tables"
SAM_FEATS = ["sam_area", "sam_perimeter", "sam_solidity", "sam_defects_gt1px", "sam_roughness", "sam_confidence", "sam_iou_author"]
BASE_FEATS = ["area_mean", "area_std", "circ_mean", "circ_std", "axis_ratio", "n_frames"]


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--max-new-calls", type=int, default=941)
    args = ap.parse_args()
    q = pd.read_csv(TABLES / "adjudication_queue.csv")
    out_path = TABLES / "sam_shape_features.csv"
    done = {}
    if out_path.exists():
        prev = pd.read_csv(out_path)
        done = {(r.patient, str(r.date), int(r.cell)): r._asdict() for r in prev.itertuples()}
    rows, new_calls = [], 0
    for i, q_ in enumerate(q.itertuples()):
        key = (q_.patient, str(q_.date), int(q_.cell))
        if key in done:
            rows.append(done[key]); continue
        got = server.frame_png(q_.patient, str(q_.date), int(q_.cell), crop=True)
        if got is None:
            rows.append({"patient": q_.patient, "date": str(q_.date), "visit": q_.visit, "cell": int(q_.cell),
                         "author_health": int(q_.health), "sam_status": "NO_FRAME"}); continue
        png, info = got
        img = decode_gray_png(png); h, w = img.shape
        poly = info.get("contour_crop_fullres") or info["contour_crop"]
        r = meta_api.sam_prompt_mask(png, box_prompt(poly, w, h, 1), repeat=0, tag="pilot-v1")
        if r.get("_cache") == "miss":
            new_calls += 1
            if new_calls > args.max_new_calls:
                pd.DataFrame(rows).to_csv(out_path, index=False)
                raise SystemExit(f"BUDGET: >{args.max_new_calls} new calls; checkpoint saved, rerun to resume")
        base = {"patient": q_.patient, "date": str(q_.date), "visit": q_.visit, "cell": int(q_.cell),
                "author_health": int(q_.health), "sam_status": r.get("status"), "sam_cache": r.get("_cache")}
        if r.get("status") == "OK":
            mask, conf = pick_mask(r["masks"], poly, w, h)
            author = geometry.fill_contour(poly, h, w)
            base.update({"sam_confidence": conf, "sam_iou_author": round(geometry.iou(mask, author), 3),
                         **{f"sam_{k}": v for k, v in shape_stats(mask).items() if k != "area"},
                         "sam_area": geometry.area(mask)})
            base["sam_area_ratio"] = round(base["sam_area"] / max(geometry.area(author), 1), 3)
        else:
            base["sam_detail"] = (r.get("detail") or "")[:160]
        rows.append(base)
        if (i + 1) % 50 == 0:
            pd.DataFrame(rows).to_csv(out_path, index=False)
            print(f"{i + 1}/{len(q)} cells, new calls so far {new_calls}, last: {base['sam_status']}", flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(out_path, index=False)
    assert df.loc[df.sam_status == "OK", "sam_solidity"].max() <= 1.0, "solidity > 1: Condition 1 violated"
    # LOPO on the SAM-OK subset (same cells for all three models)
    feats = pd.read_csv(TABLES / "cell_pixel_features.csv")
    base_map = {(r.patient, str(r.date), int(r.cell)): r for r in feats.itertuples()}
    d = df[df.sam_status == "OK"].copy()
    for f in BASE_FEATS:
        d[f] = [getattr(base_map[(r.patient, str(r.date), int(r.cell))], f) for r in d.itertuples()]
    d = d.rename(columns={"author_health": "health"}).dropna(subset=BASE_FEATS + SAM_FEATS + ["health"])
    print(f"LOPO subset: {len(d)} SAM-OK cells of {len(df)} queue cells; statuses: {df.sam_status.value_counts().to_dict()}")
    rng = np.random.default_rng(42)
    summary = {"n_queue": int(len(df)), "n_sam_ok": int(len(d)), "new_calls": int(new_calls), "models": {}}
    for name, cols in [("BASE (hull features)", BASE_FEATS), ("SAM ONLY", SAM_FEATS), ("BASE+SAM", BASE_FEATS + SAM_FEATS)]:
        oof = {}
        for test_p in sorted(d.patient.unique()):
            tr, te = d[d.patient != test_p], d[d.patient == test_p]
            clf = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000, class_weight="balanced"))
            clf.fit(tr[cols], tr.health)
            oof[test_p] = (te.health.to_numpy(), clf.predict(te[cols]))
        kaps, per = [], {}
        for p in sorted(oof):
            y, pr = oof[p]; s = server.kappa_ac1(y, pr); kaps.append(s["kappa"])
            per[p] = {"kappa": s["kappa"], "ac1": s["ac1"], "pabak": round(2 * s["agreement"] - 1, 3),
                      "bal_acc": round(float(balanced_accuracy_score(y, pr)), 3), "n": int(len(y))}
        boots = []
        for _ in range(1000):
            bk = []
            for p in sorted(oof):
                y, pr = oof[p]; idx = rng.integers(0, len(y), len(y))
                if len(np.unique(y[idx])) < 2 or len(np.unique(pr[idx])) < 2: continue
                bk.append(cohen_kappa_score(y[idx], pr[idx]))
            if len(bk) == len(oof): boots.append(float(np.mean(bk)))
        lo, hi = np.percentile(boots, [2.5, 97.5])
        summary["models"][name] = {"per_patient": per, "mean_kappa": round(float(np.mean(kaps)), 3),
                                   "kappa_ci95": [round(float(lo), 3), round(float(hi), 3)]}
        print(f"{name}: mean kappa={np.mean(kaps):.3f} CI=[{lo:.3f},{hi:.3f}] per-patient={per}")
    (TABLES / "sam_shape_summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(f"NEW SAM CALLS (full batch): {new_calls}")


if __name__ == "__main__":
    main()
